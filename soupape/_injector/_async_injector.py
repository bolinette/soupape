import asyncio
import inspect
from collections.abc import AsyncGenerator, Callable, Coroutine, Generator, Iterable, Sequence
from contextlib import AsyncExitStack, asynccontextmanager, contextmanager
from types import TracebackType
from typing import Any, Self, overload, override

from peritype import FWrap, TWrap, wrap_type

from soupape._collection import ServiceCollection
from soupape._injector._base import BaseInjector, injector_w
from soupape._instances import InstancePoolStack, PendingBuild
from soupape._resolvers import DependencyTreeNode
from soupape._traits import FallbackResolver
from soupape._types import InjectionScope, Injector
from soupape._utils import CircularGuard, CircularGuardKey
from soupape.errors import CircularDependencyError


class AsyncInjector(BaseInjector, Injector):
    def __init__(
        self,
        services: ServiceCollection,
        instance_pool: InstancePoolStack | None = None,
        *,
        parent: Self | None = None,
    ) -> None:
        super().__init__(services, instance_pool, parent=parent)
        self._exit_stack = AsyncExitStack()
        self._awaiting: dict[asyncio.Task[Any], PendingBuild] = {}
        self._set_injector_in_services()

    @property
    @override
    def is_async(self) -> bool:
        return True

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self._exit_stack.__aexit__(exc_type, exc_value, traceback)

    def _set_injector_in_services(self) -> None:
        self._instance_pool.set_instance(injector_w, self)
        self._instance_pool.set_instance(async_injector_w, self)

    def _enter_generator[T](
        self,
        node: DependencyTreeNode[..., Any],
        generator: Generator[T, Any, Any],
    ) -> T:
        owner = self._get_generator_owner(node)
        return owner._exit_stack.enter_context(_enter_generator(generator))

    async def _enter_async_generator[T](
        self,
        node: DependencyTreeNode[..., Any],
        generator: AsyncGenerator[T, Any],
    ) -> T:
        owner = self._get_generator_owner(node)
        return await owner._exit_stack.enter_async_context(_enter_async_generator(generator))

    async def _resolve_service[T](self, node: DependencyTreeNode[..., T]) -> T:
        key = self._get_storage_key(node)
        if key is None:
            return await self._build_service(node)
        if self._has_instance(key):
            return self._instance_pool.get_instance(key)
        if (pending := self._instance_pool.get_pending(key)) is not None:
            return await self._await_pending(node, pending)
        return await self._claim_and_build(node, key)

    async def _claim_and_build[T](self, node: DependencyTreeNode[..., T], key: TWrap[Any]) -> T:
        task = asyncio.current_task()
        assert task is not None
        pending = PendingBuild(
            future=asyncio.get_running_loop().create_future(),
            owner=task,
            trace=node.trace,
        )
        to_root = node.scope is InjectionScope.SINGLETON
        self._instance_pool.set_pending(key, pending, root=to_root)
        try:
            resolved = await self._build_service(node)
        except asyncio.CancelledError:
            pending.future.cancel()
            raise
        except BaseException as exc:
            pending.future.set_exception(exc)
            pending.future.exception()
            raise
        else:
            pending.future.set_result(resolved)
            return resolved
        finally:
            self._instance_pool.remove_pending(key, root=to_root)

    def _get_wait_chain(self, pending: PendingBuild) -> list[PendingBuild]:
        chain = [pending]
        seen = {pending.owner}
        while (next_pending := self._root._awaiting.get(chain[-1].owner)) is not None:
            if next_pending.owner in seen:
                break
            chain.append(next_pending)
            seen.add(next_pending.owner)
        return chain

    async def _await_pending(self, node: DependencyTreeNode[..., Any], pending: PendingBuild) -> Any:
        task = asyncio.current_task()
        assert task is not None
        chain = self._get_wait_chain(pending)
        if any(step.owner is task for step in chain):
            trace: list[CircularGuardKey] = [*node.trace]
            for step in chain:
                trace.extend(step.trace)
            raise CircularDependencyError(trace)
        self._root._awaiting[task] = pending
        try:
            return await pending.future
        finally:
            del self._root._awaiting[task]

    async def _build_service[T](
        self,
        node: DependencyTreeNode[..., T],
        positional_args: list[Any] | None = None,
        named_args: dict[str, Any] | None = None,
    ) -> T:
        resolved_args: list[Any] = list(positional_args or [])
        resolved_args.extend([await self._resolve_service(arg) for arg in node.args])

        resolved_kwargs: dict[str, Any] = dict(named_args or {})
        for kwarg_name, kwarg in node.kwargs.items():
            resolved_kwargs[kwarg_name] = await self._resolve_service(kwarg)

        resolver = node.resolver.get_resolution_func(self._get_context(node))
        resolved = resolver(*resolved_args, **resolved_kwargs)

        if inspect.isgenerator(resolved):
            resolved = self._enter_generator(node, resolved)
        elif inspect.isasyncgen(resolved):
            resolved = await self._enter_async_generator(node, resolved)
        if inspect.iscoroutine(resolved):
            resolved = await resolved

        self._set_instance(node, resolved)
        return resolved  # pyright: ignore[reportReturnType]

    @override
    async def require[T](
        self,
        interface: type[T] | TWrap[T],
        *,
        fallbacks: Iterable[FallbackResolver] | None = None,
    ) -> T:
        return await self._require_within(interface, CircularGuard(), () if fallbacks is None else (*fallbacks,))

    @override
    async def _require[T](
        self,
        interface: TWrap[T],
        circular_guard: CircularGuard,
        fallbacks: Sequence[FallbackResolver],
    ) -> T:
        resolver = self._get_service_resolver(interface, fallbacks)
        node = self._build_dependency_tree(
            resolver,
            fallbacks,
            required=interface,
            origin=interface,
            caller_context=None,
            parent=None,
            singleton_owner=None,
            circular_guard=circular_guard.copy(),
        )
        return await self._resolve_service(node)

    @overload
    async def call[**P, T](
        self,
        callable: FWrap[P, Coroutine[Any, Any, T]],
        *,
        positional_args: list[Any] | None = None,
        named_args: dict[str, Any] | None = None,
        fallbacks: Iterable[FallbackResolver] | None = None,
    ) -> T: ...
    @overload
    async def call[**P, T](
        self,
        callable: FWrap[P, T],
        *,
        positional_args: list[Any] | None = None,
        named_args: dict[str, Any] | None = None,
        fallbacks: Iterable[FallbackResolver] | None = None,
    ) -> T: ...
    @overload
    async def call[**P, T](
        self,
        callable: Callable[P, Coroutine[Any, Any, T]],
        *,
        positional_args: list[Any] | None = None,
        named_args: dict[str, Any] | None = None,
        fallbacks: Iterable[FallbackResolver] | None = None,
    ) -> T: ...
    @overload
    async def call[**P, T](
        self,
        callable: Callable[P, T],
        *,
        positional_args: list[Any] | None = None,
        named_args: dict[str, Any] | None = None,
        fallbacks: Iterable[FallbackResolver] | None = None,
    ) -> T: ...
    @override
    async def call(
        self,
        callable: Callable[..., Any] | FWrap[..., Any],
        *,
        positional_args: list[Any] | None = None,
        named_args: dict[str, Any] | None = None,
        fallbacks: Iterable[FallbackResolver] | None = None,
    ) -> Any:
        return await self._call_within(
            callable,
            positional_args or [],
            named_args or {},
            None,
            CircularGuard(),
            () if fallbacks is None else (*fallbacks,),
        )

    @override
    async def _call(
        self,
        fwrap: FWrap[..., Any],
        positional_args: list[Any],
        named_args: dict[str, Any],
        origin: TWrap[Any] | None,
        circular_guard: CircularGuard,
        fallbacks: Sequence[FallbackResolver],
    ) -> Any:
        resolver = self._get_function_resolver(fwrap)
        node = self._build_dependency_tree(
            resolver,
            fallbacks,
            required=None,
            origin=origin,
            caller_context=None,
            parent=None,
            singleton_owner=None,
            circular_guard=circular_guard.copy(),
            positional_args=positional_args,
            named_args=named_args,
        )
        return await self._build_service(node, positional_args, named_args)

    @override
    def get_scoped_injector(self) -> "AsyncInjector":
        return AsyncInjector(self._services, self._instance_pool.stack(), parent=self)


async_injector_w = wrap_type(AsyncInjector)


def _identity[T](generator: Generator[T, Any, Any]) -> Generator[T, Any, Any]:
    return generator


def _async_identity[T](generator: AsyncGenerator[T, Any]) -> AsyncGenerator[T, Any]:
    return generator


_enter_generator = contextmanager(_identity)
_enter_async_generator = asynccontextmanager(_async_identity)

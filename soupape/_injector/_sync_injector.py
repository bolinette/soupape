import inspect
from collections.abc import Callable, Generator, Iterable, Sequence
from contextlib import ExitStack, contextmanager
from types import TracebackType
from typing import Any, Self, overload, override

from peritype import FWrap, TWrap, wrap_type

from soupape._collection import ServiceCollection
from soupape._injector._base import BaseInjector, injector_w
from soupape._instances import InstancePoolStack
from soupape._resolvers import DependencyTreeNode
from soupape._traits import FallbackResolver
from soupape._types import Injector
from soupape._utils import CircularGuard
from soupape.errors import AsyncInSyncInjectorError


class SyncInjector(BaseInjector, Injector):
    def __init__(
        self,
        services: ServiceCollection,
        instance_pool: InstancePoolStack | None = None,
        *,
        parent: Self | None = None,
    ) -> None:
        super().__init__(services, instance_pool, parent=parent)
        self._exit_stack = ExitStack()
        self._set_injector_in_services()

    @property
    @override
    def is_async(self) -> bool:
        return False

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._exit_stack.__exit__(exc_type, exc_value, traceback)

    def _set_injector_in_services(self) -> None:
        self._instance_pool.set_instance(injector_w, self)
        self._instance_pool.set_instance(sync_injector_w, self)

    def _enter_generator[T](
        self,
        node: DependencyTreeNode[..., Any],
        generator: Generator[T, Any, Any],
    ) -> T:
        owner = self._get_generator_owner(node)
        return owner._exit_stack.enter_context(_enter_generator(generator))

    def _resolve_service[T](
        self,
        node: DependencyTreeNode[..., T],
    ) -> T:
        key = self._get_storage_key(node)
        if key is not None and self._has_instance(key):
            return self._instance_pool.get_instance(key)
        return self._build_service(node)

    def _build_service[T](
        self,
        node: DependencyTreeNode[..., T],
        positional_args: list[Any] | None = None,
        named_args: dict[str, Any] | None = None,
    ) -> T:
        resolved_args: list[Any] = list(positional_args or [])
        for arg in node.args:
            resolved_args.append(self._resolve_service(arg))

        resolved_kwargs: dict[str, Any] = dict(named_args or {})
        for kwarg_name, kwarg in node.kwargs.items():
            resolved_kwargs[kwarg_name] = self._resolve_service(kwarg)

        resolver = node.resolver.get_resolution_func(self._get_context(node))
        resolved = resolver(*resolved_args, **resolved_kwargs)

        if inspect.isgenerator(resolved):
            resolved = self._enter_generator(node, resolved)
        elif inspect.isasyncgen(resolved):
            raise AsyncInSyncInjectorError(resolved)
        if inspect.iscoroutine(resolved):
            raise AsyncInSyncInjectorError(resolved)

        self._set_instance(node, resolved)
        return resolved  # type: ignore

    @override
    def require[T](
        self,
        interface: type[T] | TWrap[T],
        *,
        fallbacks: Iterable[FallbackResolver] | None = None,
    ) -> T:
        return self._require_within(interface, CircularGuard(), () if fallbacks is None else (*fallbacks,))

    @override
    def _require[T](
        self,
        interface: TWrap[T],
        circular_guard: CircularGuard,
        fallbacks: Sequence[FallbackResolver],
    ) -> T:
        resolver = self._get_service_resolver(interface, fallbacks)
        node = self._build_dependency_tree(
            resolver,
            required=interface,
            origin=interface,
            caller_context=None,
            parent=None,
            singleton_owner=None,
            circular_guard=circular_guard.copy(),
            fallbacks=fallbacks,
        )
        return self._resolve_service(node)

    @overload
    def call[**P, T](
        self,
        callable: FWrap[P, T],
        *,
        positional_args: list[Any] | None = None,
        named_args: dict[str, Any] | None = None,
        fallbacks: Iterable[FallbackResolver] | None = None,
    ) -> T: ...
    @overload
    def call[**P, T](
        self,
        callable: Callable[P, T],
        *,
        positional_args: list[Any] | None = None,
        named_args: dict[str, Any] | None = None,
        fallbacks: Iterable[FallbackResolver] | None = None,
    ) -> T: ...
    @override
    def call(
        self,
        callable: Callable[..., Any] | FWrap[..., Any],
        *,
        positional_args: list[Any] | None = None,
        named_args: dict[str, Any] | None = None,
        fallbacks: Iterable[FallbackResolver] | None = None,
    ) -> Any:
        return self._call_within(
            callable,
            positional_args or [],
            named_args or {},
            None,
            CircularGuard(),
            () if fallbacks is None else (*fallbacks,),
        )

    @override
    def _call(
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
        return self._build_service(node, positional_args, named_args)

    @override
    def get_scoped_injector(self) -> "SyncInjector":
        return SyncInjector(self._services, self._instance_pool.stack(), parent=self)


sync_injector_w = wrap_type(SyncInjector)


def _identity[T](generator: Generator[T, Any, Any]) -> Generator[T, Any, Any]:
    return generator


_enter_generator = contextmanager(_identity)

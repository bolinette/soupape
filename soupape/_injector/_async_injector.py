import inspect
from collections.abc import AsyncGenerator, Callable, Coroutine
from typing import Any, Self, Unpack, cast, overload

from peritype import FWrap, TWrap, wrap_func, wrap_type

from soupape._collection import ServiceCollection
from soupape._injector import BaseInjector
from soupape._instances import InstancePoolStack
from soupape._resolvers import DependencyTreeNode, FunctionResolver
from soupape._types import (
    InjectionContext,
    InjectionScope,
    Injector,
    InjectorCallArgs,
)
from soupape._utils import CircularGuard


class AsyncInjector(BaseInjector, Injector):
    def __init__(self, services: ServiceCollection, instance_pool: InstancePoolStack | None = None) -> None:
        super().__init__(services, instance_pool)
        self._async_generators_to_close: list[AsyncGenerator[Any]] = []
        self._set_injector_in_services()

    @property
    def is_async(self) -> bool:
        return True

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: Any,
    ) -> None:
        for gen in self._generators_to_close:
            try:
                next(gen)
            except StopIteration:
                pass
        for agen in self._async_generators_to_close:
            try:
                await anext(agen)
            except StopAsyncIteration:
                pass

    def _set_injector_in_services(self) -> None:
        self._instance_pool.set_instance(injector_w, self)
        self._instance_pool.set_instance(async_injector_w, self)

    async def _resolve_service[T](
        self,
        context: InjectionContext,
        dep_node: DependencyTreeNode[..., T],
    ) -> T:
        context.circular_guard.enter(dep_node.resolver.get_instance_function())

        resolved_args: list[Any] = []
        if context.positional_args is not None:
            for arg in context.positional_args:
                resolved_args.append(arg)
        for arg in dep_node.args:
            resolved_arg = await self._resolve_service(context.new_required(dep_node.scope, arg.required), arg)
            resolved_args.append(resolved_arg)

        resolved_kwargs: dict[str, Any] = {}
        for kwarg_name, kwarg in dep_node.kwargs.items():
            resolved_kwarg = await self._resolve_service(context.new_required(dep_node.scope, kwarg.required), kwarg)
            resolved_kwargs[kwarg_name] = resolved_kwarg

        resolver = dep_node.resolver.get_resolve_func(context)
        resolved = resolver(*resolved_args, **resolved_kwargs)

        if inspect.isgenerator(resolved):
            self._generators_to_close.append(resolved)
            resolved = next(resolved)
        elif inspect.isasyncgen(resolved):
            self._async_generators_to_close.append(resolved)
            resolved = await anext(resolved)
        if inspect.iscoroutine(resolved):
            resolved = await resolved

        if dep_node.registered is not None:
            self._set_instance(context, dep_node.registered, resolved)

        return resolved  # type: ignore

    async def require[T](self, interface: type[T] | TWrap[T]) -> T:
        if not isinstance(interface, TWrap):
            twrap = wrap_type(interface)
        else:
            twrap = interface
        return await self._require(twrap, CircularGuard())

    async def _require[T](self, interface: TWrap[T], circular_guard: CircularGuard) -> T:
        resolver = self._get_service_resolver(interface)
        context = self._get_injection_context(
            interface,
            resolver.scope,
            circular_guard,
            required=interface,
        )
        dep_node = self._build_dependency_tree(context.copy(), resolver)
        resolved = await self._resolve_service(context.copy(), dep_node)
        return resolved

    @overload
    async def call[**P, T](
        self,
        callable: FWrap[P, Coroutine[Any, Any, T]],
        **kwargs: Unpack[InjectorCallArgs],
    ) -> T: ...
    @overload
    async def call[**P, T](
        self,
        callable: FWrap[P, T],
        **kwargs: Unpack[InjectorCallArgs],
    ) -> T: ...
    @overload
    async def call[**P, T](
        self,
        callable: Callable[P, Coroutine[Any, Any, T]],
        **kwargs: Unpack[InjectorCallArgs],
    ) -> T: ...
    @overload
    async def call[**P, T](
        self,
        callable: Callable[P, T],
        **kwargs: Unpack[InjectorCallArgs],
    ) -> T: ...
    async def call(
        self,
        callable: Callable[..., Any] | FWrap[..., Any],
        **kwargs: Unpack[InjectorCallArgs],
    ) -> Any:
        if not isinstance(callable, FWrap):
            fwrap = wrap_func(callable)
        else:
            fwrap = cast(FWrap[..., Any], callable)

        context = self._get_injection_context(
            kwargs.get("origin"),
            InjectionScope.IMMEDIATE,
            circular_guard=kwargs.get("circular_guard"),
            positional_args=kwargs.get("positional_args"),
        )
        resolver = FunctionResolver(InjectionScope.IMMEDIATE, fwrap)
        dep_node = self._build_dependency_tree(context.copy(), resolver)
        return await self._resolve_service(context.copy(), dep_node)

    def get_scoped_injector(self) -> "AsyncInjector":
        return AsyncInjector(self._services, self._instance_pool.stack())


async_injector_w = wrap_type(AsyncInjector)
injector_w = wrap_type(Injector)

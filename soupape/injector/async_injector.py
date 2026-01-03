import asyncio
import inspect
from collections.abc import AsyncGenerator, Callable, Coroutine
from typing import Any, Self, Unpack, cast, overload

from peritype import FWrap, TWrap, wrap_func, wrap_type

from soupape.collection import ServiceCollection
from soupape.injector import BaseInjector
from soupape.instances import InstancePoolStack
from soupape.types import InjectionScope, Injector, InjectorCallArgs, ResolverCallArgs, ResolverMetadata


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
        injector_w = wrap_type(AsyncInjector)
        if not self._services.is_registered(injector_w):

            def resolver() -> "AsyncInjector":
                return self

            self._services.add_singleton(resolver)
        self._instance_pool.set_instance(injector_w, self)

    async def _resolve_service[T](
        self,
        resolver_args: ResolverCallArgs[..., T],
        *,
        injector_args: InjectorCallArgs | None = None,
    ) -> T:
        if resolver_args.interface is not None and self._has_instance(resolver_args.interface):
            return self._get_instance(resolver_args.interface)

        resolved_args: list[Any] = []
        if injector_args is not None and "positional_args" in injector_args:
            for arg in injector_args["positional_args"]:
                resolved_args.append(arg)
        for arg in resolver_args.args:
            resolved_arg = await self._resolve_service(arg)
            resolved_args.append(resolved_arg)

        resolved_kwargs: dict[str, Any] = {}
        for kwarg_name, kwarg in resolver_args.kwargs.items():
            resolved_kwarg = await self._resolve_service(kwarg)
            resolved_kwargs[kwarg_name] = resolved_kwarg

        resolver = self._get_resolver_from_call_args(resolver_args)
        resolved = resolver(*resolved_args, **resolved_kwargs)

        if inspect.isgenerator(resolved):
            self._generators_to_close.append(resolved)
            resolved = next(resolved)
        elif inspect.isasyncgen(resolved):
            self._async_generators_to_close.append(resolved)
            resolved = await anext(resolved)
        if inspect.iscoroutine(resolved):
            resolved = await resolved

        if resolver_args.interface is not None:
            self._set_instance(resolver_args.scope, resolver_args.interface, resolved)

        return resolved  # type: ignore

    async def require[T](self, interface: type[T] | TWrap[T]) -> T:
        if not isinstance(interface, TWrap):
            twrap = wrap_type(interface)
        else:
            twrap = interface
        return await self._require(twrap)

    async def _require[T](self, interface: TWrap[T]) -> T:
        metadata = self._get_service_metadata(interface)
        resolver_args = self._build_resolve_tree(metadata)
        resolved = await self._resolve_service(resolver_args)
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

        async def resolver(*args: Any, **kwds: Any) -> Any:
            resolved = fwrap.func(*args, **kwds)
            if asyncio.iscoroutine(resolved):
                return await resolved
            return resolved

        resolver_args = self._build_resolve_tree(
            ResolverMetadata(
                scope=InjectionScope.IMMEDIATE,
                signature=fwrap.signature,
                fwrap=fwrap,
                resolver=resolver,
            ),
            injector_args=kwargs,
        )
        return await self._resolve_service(resolver_args, injector_args=kwargs)

    def get_scoped_injector(self) -> "AsyncInjector":
        return AsyncInjector(self._services, self._instance_pool.stack())

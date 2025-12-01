import asyncio
from collections.abc import Callable, Coroutine
from typing import Any, cast, overload

from peritype import FWrap, TWrap, wrap_func, wrap_type

from soupape.collection import ServiceCollection
from soupape.injector import BaseInjector
from soupape.instances import InstancePoolStack
from soupape.types import InjectionScope, ResolverCallArgs, ResolverMetadata


class Injector(BaseInjector):
    def __init__(self, services: ServiceCollection, instance_pool: InstancePoolStack | None = None) -> None:
        super().__init__(services, instance_pool)

    async def _resolve_service[T](self, call_args: ResolverCallArgs[..., T]) -> T:
        if call_args.interface is not None and self._has_instance(call_args.interface):
            return self._get_instance(call_args.interface)

        resolved_args: list[Any] = []
        for arg in call_args.args:
            resolved_arg = await self._resolve_service(arg)
            resolved_args.append(resolved_arg)

        resolved_kwargs: dict[str, Any] = {}
        for kwarg_name, kwarg in call_args.kwargs.items():
            resolved_kwarg = await self._resolve_service(kwarg)
            resolved_kwargs[kwarg_name] = resolved_kwarg

        if asyncio.iscoroutinefunction(call_args.resolver):
            result = await call_args.resolver(*resolved_args, **resolved_kwargs)
        else:
            result = cast(T, call_args.resolver(*resolved_args, **resolved_kwargs))
        if call_args.interface is not None:
            self._set_instance(call_args.scope, call_args.interface, result)
        return result

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
    async def call[**P, T](self, callable: FWrap[P, Coroutine[Any, Any, T]]) -> T: ...
    @overload
    async def call[**P, T](self, callable: FWrap[P, T]) -> T: ...
    @overload
    async def call[**P, T](self, callable: Callable[P, Coroutine[Any, Any, T]]) -> T: ...
    @overload
    async def call[**P, T](self, callable: Callable[P, T]) -> T: ...
    async def call(self, callable: Callable[..., Any] | FWrap[..., Any]) -> Any:
        if not isinstance(callable, FWrap):
            fwrap = wrap_func(callable)
        else:
            fwrap = cast(FWrap[..., Any], callable)

        async def resolver(*args: Any, **kwds: Any) -> Any:
            if asyncio.iscoroutinefunction(fwrap.func):
                return await fwrap.func(*args, **kwds)
            else:
                return fwrap.func(*args, **kwds)

        resolver_args = self._build_resolve_tree(
            ResolverMetadata(
                scope=InjectionScope.IMMEDIATE,
                signature=fwrap.signature,
                fwrap=fwrap,
                resolver=resolver,
            )
        )
        return await self._resolve_service(resolver_args)

    def get_scoped_injector(self) -> "Injector":
        return Injector(self._services, self._instance_pool.stack())

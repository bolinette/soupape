import inspect
from collections.abc import Awaitable, Iterable
from typing import Any, override

from peritype import FWrap, TWrap

from soupape.resolvers import ServiceResolver
from soupape.resolvers.utils import dict_str_any_w, list_any_w
from soupape.types import InjectionContext, InjectionScope, Injector, ResolveFunction


class ListResolverContainer(ServiceResolver[[], list[Any]]):
    @property
    @override
    def name(self) -> str:
        return str(list_any_w)

    @property
    @override
    def scope(self) -> InjectionScope:
        return InjectionScope.IMMEDIATE

    @property
    @override
    def required(self) -> TWrap[list[Any]]:
        return list_any_w

    @property
    @override
    def registered(self) -> None:
        return None

    @override
    def get_resolve_hints(self, **kwargs: Any) -> dict[str, TWrap[Any]]:
        return {}

    @override
    def get_instance_function(self) -> FWrap[[], list[Any]]:
        return self._empty_resolver_w

    @override
    def get_resolve_signature(self) -> inspect.Signature:
        return self._empty_resolver_w.signature

    @override
    def get_resolve_func(self, context: InjectionContext) -> ResolveFunction[..., list[Any]]:
        assert context.required is not None
        return _ListResolver(context.injector, context.required.generic_params[0])  # pyright: ignore[reportReturnType]


class _ListResolver:
    def __init__(self, injector: Injector, tw: TWrap[list[Any]]) -> None:
        self._injector = injector
        self._type = tw

    async def _continue_async(
        self,
        services: list[Any],
        service: Awaitable[Any],
        registered_types: Iterable[TWrap[Any]],
    ) -> list[Any]:
        services.append(await service)
        for twrap in registered_types:
            if self._type.match(twrap, match_mode="sub"):
                service = self._injector.require(twrap)
                if inspect.iscoroutine(service):
                    services.append(await service)
        return services

    def __call__(self) -> list[Any] | Awaitable[list[Any]]:
        services: list[Any] = []
        registered_types = self._injector.services.registered_types
        for twrap in self._injector.services.registered_types:
            if self._type.match(twrap, match_mode="sub"):
                service = self._injector.require(twrap)
                if inspect.iscoroutine(service):
                    return self._continue_async(services, service, registered_types)
                services.append(service)
        return services


class DictResolverContainer(ServiceResolver[[], dict[str, Any]]):
    @property
    @override
    def name(self) -> str:
        return str(dict_str_any_w)

    @property
    @override
    def scope(self) -> InjectionScope:
        return InjectionScope.IMMEDIATE

    @property
    @override
    def required(self) -> TWrap[dict[str, Any]]:
        return dict_str_any_w

    @property
    @override
    def registered(self) -> None:
        return None

    @override
    def get_resolve_hints(self, **kwargs: Any) -> dict[str, TWrap[Any]]:
        return {}

    @override
    def get_instance_function(self) -> FWrap[[], dict[str, Any]]:
        return self._empty_resolver_w

    @override
    def get_resolve_signature(self) -> inspect.Signature:
        return self._empty_resolver_w.signature

    @override
    def get_resolve_func(self, context: InjectionContext) -> ResolveFunction[..., dict[str, Any]]:
        assert context.required is not None
        return _DictResolver(context.injector, context.required.generic_params[1])  # pyright: ignore[reportReturnType]


class _DictResolver:
    def __init__(self, injector: Injector, tw: TWrap[list[Any]]) -> None:
        self._injector = injector
        self._type = tw

    async def _continue_async(
        self,
        services: dict[str, Any],
        service_twrap: TWrap[Any],
        service: Awaitable[Any],
        registered_types: Iterable[TWrap[Any]],
    ) -> dict[str, Any]:
        services[str(service_twrap)] = await service
        for twrap in registered_types:
            if self._type.match(twrap, match_mode="sub"):
                service = self._injector.require(twrap)
                if inspect.iscoroutine(service):
                    services[str(twrap)] = await service
        return services

    def __call__(self) -> dict[str, Any] | Awaitable[dict[str, Any]]:
        services: dict[str, Any] = {}
        registered_types = self._injector.services.registered_types
        for twrap in self._injector.services.registered_types:
            if self._type.match(twrap, match_mode="sub"):
                service = self._injector.require(twrap)
                if inspect.iscoroutine(service):
                    return self._continue_async(services, twrap, service, registered_types)
                services[str(twrap)] = service
        return services

import inspect
from collections.abc import Awaitable
from typing import Any, override

from peritype import FWrap, TWrap

from soupape._resolvers import ServiceResolver
from soupape._resolvers._utils import dict_str_any_w, list_any_w
from soupape._types import InjectionScope, ResolutionContext, ResolutionFunction


class ListResolver(ServiceResolver[[], list[Any]]):
    @property
    @override
    def scope(self) -> InjectionScope:
        return InjectionScope.IMMEDIATE

    @property
    @override
    def required(self) -> TWrap[list[Any]]:
        return list_any_w

    @override
    def get_resolution_hints(self, context: ResolutionContext) -> dict[str, TWrap[Any]]:
        return {}

    @override
    def get_instance_function(self) -> FWrap[[], list[Any]]:
        return self._empty_resolver_w

    @override
    def get_resolution_signature(self) -> inspect.Signature:
        return self._empty_resolver_w.signature

    @override
    def get_resolution_func(self, context: ResolutionContext) -> ResolutionFunction[..., list[Any]]:
        assert context.required is not None
        return _ListResolveFunc(context, context.required.generic_params[0])


class _ListResolveFunc:
    def __init__(self, context: ResolutionContext, tw: TWrap[Any]) -> None:
        self._context = context
        self._type = tw

    def _get_matching_types(self) -> list[TWrap[Any]]:
        return [
            twrap
            for twrap in self._context.injector.services.registered_types
            if self._type.match(twrap, match_mode="sub")
        ]

    async def _continue_async(
        self,
        services: list[Any],
        service: Awaitable[Any],
        remaining_types: list[TWrap[Any]],
    ) -> list[Any]:
        services.append(await service)
        for twrap in remaining_types:
            service = self._context.require(twrap)
            if inspect.iscoroutine(service):
                service = await service
            services.append(service)
        return services

    def __call__(self) -> list[Any] | Awaitable[list[Any]]:
        services: list[Any] = []
        matching_types = self._get_matching_types()
        for index, twrap in enumerate(matching_types):
            service = self._context.require(twrap)
            if inspect.iscoroutine(service):
                return self._continue_async(services, service, matching_types[index + 1 :])
            services.append(service)
        return services


class DictResolver(ServiceResolver[[], dict[str, Any]]):
    @property
    @override
    def scope(self) -> InjectionScope:
        return InjectionScope.IMMEDIATE

    @property
    @override
    def required(self) -> TWrap[dict[str, Any]]:
        return dict_str_any_w

    @override
    def get_resolution_hints(self, context: ResolutionContext) -> dict[str, TWrap[Any]]:
        return {}

    @override
    def get_instance_function(self) -> FWrap[[], dict[str, Any]]:
        return self._empty_resolver_w

    @override
    def get_resolution_signature(self) -> inspect.Signature:
        return self._empty_resolver_w.signature

    @override
    def get_resolution_func(self, context: ResolutionContext) -> ResolutionFunction[..., dict[str, Any]]:
        assert context.required is not None
        return _DictResolveFunc(context, context.required.generic_params[1])


class _DictResolveFunc:
    def __init__(self, context: ResolutionContext, tw: TWrap[Any]) -> None:
        self._context = context
        self._type = tw

    def _get_matching_types(self) -> list[TWrap[Any]]:
        return [
            twrap
            for twrap in self._context.injector.services.registered_types
            if self._type.match(twrap, match_mode="sub")
        ]

    async def _continue_async(
        self,
        services: dict[str, Any],
        service_twrap: TWrap[Any],
        service: Awaitable[Any],
        remaining_types: list[TWrap[Any]],
    ) -> dict[str, Any]:
        services[str(service_twrap)] = await service
        for twrap in remaining_types:
            service = self._context.require(twrap)
            if inspect.iscoroutine(service):
                service = await service
            services[str(twrap)] = service
        return services

    def __call__(self) -> dict[str, Any] | Awaitable[dict[str, Any]]:
        services: dict[str, Any] = {}
        matching_types = self._get_matching_types()
        for index, twrap in enumerate(matching_types):
            service = self._context.require(twrap)
            if inspect.iscoroutine(service):
                return self._continue_async(services, twrap, service, matching_types[index + 1 :])
            services[str(twrap)] = service
        return services

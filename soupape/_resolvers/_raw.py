import inspect
from typing import Any, override

from peritype import FWrap, TWrap

from soupape._resolvers import ServiceResolver
from soupape._resolvers._utils import type_any_w, type_any_w_w
from soupape._types import InjectionContext, InjectionScope, ResolveFunction


class RawTypeResolver(ServiceResolver[[], type[Any]]):
    @property
    @override
    def name(self) -> str:
        return str(type_any_w)

    @property
    @override
    def scope(self) -> InjectionScope:
        return InjectionScope.IMMEDIATE

    @property
    @override
    def required(self) -> TWrap[type[Any]]:
        return type_any_w

    @property
    @override
    def registered(self) -> None:
        return None

    @override
    def get_resolve_hints(self, context: InjectionContext) -> dict[str, TWrap[Any]]:
        return {}

    @override
    def get_instance_function(self) -> FWrap[[], type[Any]]:
        return self._empty_resolver_w

    @override
    def get_resolve_signature(self) -> inspect.Signature:
        return self._empty_resolver_w.signature

    @override
    def get_resolve_func(self, context: InjectionContext) -> ResolveFunction[..., type[Any]]:
        assert context.required is not None
        return _RawTypeResolveFunc(context.required)


class _RawTypeResolveFunc[T]:
    def __init__(self, tw: TWrap[T]) -> None:
        self._type = tw

    def __call__(self) -> type[T]:
        return self._type.generic_params[0].inner_type


class WrappedTypeResolver(ServiceResolver[[], TWrap[Any]]):
    @property
    @override
    def name(self) -> str:
        return str(type_any_w_w)

    @property
    @override
    def scope(self) -> InjectionScope:
        return InjectionScope.IMMEDIATE

    @property
    @override
    def required(self) -> TWrap[TWrap[Any]]:
        return type_any_w_w

    @property
    @override
    def registered(self) -> None:
        return None

    @override
    def get_resolve_hints(self, context: InjectionContext) -> dict[str, TWrap[Any]]:
        return {}

    @override
    def get_instance_function(self) -> FWrap[[], TWrap[Any]]:
        return self._empty_resolver_w

    @override
    def get_resolve_signature(self) -> inspect.Signature:
        return self._empty_resolver_w.signature

    @override
    def get_resolve_func(self, context: InjectionContext) -> ResolveFunction[..., TWrap[Any]]:
        assert context.required is not None
        return _WrappedTypeResolveFunc(context.required)


class _WrappedTypeResolveFunc[T]:
    def __init__(self, tw: TWrap[T]) -> None:
        self._tw = tw

    def __call__(self) -> TWrap[T]:
        return self._tw.generic_params[0]

import inspect
from typing import Any, override

from peritype import TWrap

from soupape.resolvers import ServiceResolver
from soupape.resolvers.utils import empty_func_w, type_any_w, type_any_w_w
from soupape.types import InjectionContext, InjectionScope, ResolveFunction


class RawTypeResolverContainer(ServiceResolver[[], type[Any]]):
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
    def get_resolve_hints(self, **kwargs: Any) -> dict[str, TWrap[Any]]:
        return {}

    @override
    def get_resolve_signature(self) -> inspect.Signature:
        return empty_func_w.signature

    @override
    def get_resolve_func(self, context: InjectionContext) -> ResolveFunction[..., type[Any]]:
        assert context.required is not None
        return _RawTypeResolver(context.required)


class _RawTypeResolver[T]:
    def __init__(self, tw: TWrap[T]) -> None:
        self._type = tw

    def __call__(self) -> type[T]:
        return self._type.generic_params[0].inner_type


class WrappedTypeResolverContainer(ServiceResolver[[], TWrap[Any]]):
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
    def get_resolve_hints(self, **kwargs: Any) -> dict[str, TWrap[Any]]:
        return {}

    @override
    def get_resolve_signature(self) -> inspect.Signature:
        return empty_func_w.signature

    @override
    def get_resolve_func(self, context: InjectionContext) -> ResolveFunction[..., TWrap[Any]]:
        assert context.required is not None
        return _WrappedTypeResolver(context.required)


class _WrappedTypeResolver[T]:
    def __init__(self, tw: TWrap[T]) -> None:
        self._tw = tw

    def __call__(self) -> TWrap[T]:
        return self._tw.generic_params[0]

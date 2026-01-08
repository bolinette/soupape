from typing import Any

from peritype import TWrap

from soupape.types import InjectionContext, ServiceResolver


class RawTypeResolverFactory:
    def __with_context__(self, context: InjectionContext) -> ServiceResolver[..., Any]:
        if context.required is None:
            raise ValueError("RawTypeResolverFactory requires a 'required' type in the context.")
        return _RawTypeResolver(context.required)

    def __call__(self) -> Any:
        raise NotImplementedError()


class _RawTypeResolver[T]:
    def __init__(self, tw: TWrap[T]) -> None:
        self._type = tw

    def __call__(self) -> type[T]:
        return self._type.generic_params[0].inner_type


class WrappedTypeResolverFactory:
    def __with_context__(self, context: InjectionContext) -> ServiceResolver[..., Any]:
        if context.required is None:
            raise ValueError("WrappedTypeResolverFactory requires a 'required' type in the context.")
        return _WrappedTypeResolver(context.required)

    def __call__(self) -> Any:
        raise NotImplementedError()


class _WrappedTypeResolver[T]:
    def __init__(self, tw: TWrap[T]) -> None:
        self._tw = tw

    def __call__(self) -> TWrap[T]:
        return self._tw.generic_params[0]

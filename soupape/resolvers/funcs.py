import inspect
from typing import Any, override

from peritype import FWrap, TWrap

from soupape.resolvers import ServiceResolver
from soupape.types import InjectionContext, InjectionScope, ResolveFunction


class FunctionResolverContainer[**P, T](ServiceResolver[P, T]):
    def __init__(
        self,
        scope: InjectionScope,
        func: FWrap[P, T],
        *,
        required: TWrap[T] | None = None,
        registered: TWrap[Any] | None = None,
    ) -> None:
        self._scope = scope
        self._func = func
        self._required = required
        self._registered = registered

    @property
    @override
    def name(self) -> str:
        return str(self._func)

    @property
    @override
    def scope(self) -> InjectionScope:
        return self._scope

    @property
    @override
    def required(self) -> TWrap[T] | None:
        return self._required

    @property
    @override
    def registered(self) -> TWrap[Any] | None:
        return self._registered

    @override
    def get_resolve_hints(self, *, belongs_to: TWrap[Any] | None = None) -> dict[str, TWrap[Any]]:
        return self._func.get_signature_hints(belongs_to=belongs_to)

    @override
    def get_resolve_signature(self) -> inspect.Signature:
        return self._func.signature

    @override
    def get_resolve_func(self, context: InjectionContext) -> ResolveFunction[P, T]:
        return _FunctionResolver[P, T](self._func)


class _FunctionResolver[**P, T]:
    def __init__(self, func: FWrap[P, T]) -> None:
        self._func = func

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> T:
        return self._func(*args, **kwargs)

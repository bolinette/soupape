import inspect
from typing import Any, override

from peritype import FWrap, TWrap

from soupape._resolvers import ServiceResolver
from soupape._types import InjectionContext, InjectionScope, ResolveFunction


class FunctionResolver[**P, T](ServiceResolver[P, T]):
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
    def get_resolve_hints(self, context: InjectionContext) -> dict[str, TWrap[Any]]:
        if not self._func.is_defined and context.required is not None:
            func = self._func.specialize_from_return(context.required)
        else:
            func = self._func
        return func.get_signature_hints(belongs_to=context.origin)

    @override
    def get_instance_function(self) -> FWrap[P, T]:
        return self._func

    @override
    def get_resolve_signature(self) -> inspect.Signature:
        return self._func.signature

    @override
    def get_resolve_func(self, context: InjectionContext) -> ResolveFunction[P, T]:
        return _FunctionResolveFunc[P, T](self._func)


class _FunctionResolveFunc[**P, T]:
    def __init__(self, func: FWrap[P, T]) -> None:
        self._func = func

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> T:
        return self._func(*args, **kwargs)

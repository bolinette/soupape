import inspect
from typing import Any, override

from peritype import FWrap, TWrap, wrap_type

from soupape._resolvers import ServiceResolver
from soupape._types import InjectionContext, InjectionScope, ResolveFunction

_injection_ctx_w = wrap_type(InjectionContext)


class InjectionContextResolver(ServiceResolver[[], InjectionContext]):
    @property
    @override
    def scope(self) -> InjectionScope:
        return InjectionScope.SCOPED

    @property
    @override
    def required(self) -> TWrap[InjectionContext]:
        return _injection_ctx_w

    @override
    def get_resolve_hints(self, context: InjectionContext) -> dict[str, TWrap[Any]]:
        return {}

    @override
    def get_instance_function(self) -> FWrap[[], InjectionContext]:
        return self._empty_resolver_w

    @override
    def get_resolve_signature(self) -> inspect.Signature:
        return self._empty_resolver_w.signature

    @override
    def get_resolve_func(self, context: InjectionContext) -> ResolveFunction[..., InjectionContext]:
        assert context.required is not None
        return _InjectionContextResolveFunc(context)


class _InjectionContextResolveFunc:
    def __init__(self, ctx: InjectionContext) -> None:
        self._ctx = ctx

    def __call__(self) -> InjectionContext:
        return self._ctx

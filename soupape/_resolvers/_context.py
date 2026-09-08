import inspect
from typing import Any, override

from peritype import FWrap, TWrap, wrap_type

from soupape._resolvers import ServiceResolver
from soupape._types import CallerContext, InjectionContext, InjectionScope, ResolutionContext, ResolutionFunction
from soupape.errors import CallerContextNotAvailableError

_resolution_ctx_w = wrap_type(ResolutionContext)
_caller_ctx_w = wrap_type(CallerContext)


def _get_service_frame(context: ResolutionContext) -> ResolutionContext:
    if isinstance(context, InjectionContext):
        return context.parent_frame()
    return context.copy()


class ResolutionContextResolver(ServiceResolver[[], ResolutionContext]):
    @property
    @override
    def scope(self) -> InjectionScope:
        return InjectionScope.IMMEDIATE

    @property
    @override
    def required(self) -> TWrap[ResolutionContext]:
        return _resolution_ctx_w

    @override
    def get_resolution_hints(self, context: ResolutionContext) -> dict[str, TWrap[Any]]:
        return {}

    @override
    def get_instance_function(self) -> FWrap[[], ResolutionContext]:
        return self._empty_resolver_w

    @override
    def get_resolution_signature(self) -> inspect.Signature:
        return self._empty_resolver_w.signature

    @override
    def get_resolution_func(self, context: ResolutionContext) -> ResolutionFunction[..., ResolutionContext]:
        snapshot = _get_service_frame(context)
        return lambda: snapshot


class CallerContextResolver(ServiceResolver[[], CallerContext]):
    @property
    @override
    def scope(self) -> InjectionScope:
        return InjectionScope.IMMEDIATE

    @property
    @override
    def required(self) -> TWrap[CallerContext]:
        return _caller_ctx_w

    @override
    def get_resolution_hints(self, context: ResolutionContext) -> dict[str, TWrap[Any]]:
        return {}

    @override
    def get_instance_function(self) -> FWrap[[], CallerContext]:
        return self._empty_resolver_w

    @override
    def get_resolution_signature(self) -> inspect.Signature:
        return self._empty_resolver_w.signature

    @override
    def get_resolution_func(self, context: ResolutionContext) -> ResolutionFunction[..., CallerContext]:
        frame = _get_service_frame(context)
        caller_context = frame.caller_context
        if caller_context is None:
            raise CallerContextNotAvailableError(str(frame.required))
        return lambda: caller_context

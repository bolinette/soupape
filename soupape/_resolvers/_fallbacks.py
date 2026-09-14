import inspect
from collections.abc import Mapping, Sequence
from typing import Any, override

from peritype import FWrap, TWrap, wrap_func

from soupape._resolvers import ServiceResolver
from soupape._traits import FallbackResolver
from soupape._types import InjectionScope, ResolutionContext, ResolutionFunction
from soupape.errors import ServiceNotFoundError


class FallbackRunnerResolver(ServiceResolver[..., Any]):
    def __init__(
        self,
        fallbacks: Sequence[FallbackResolver],
        fallthrough: ServiceResolver[..., Any] | None = None,
    ) -> None:
        self.fallbacks = fallbacks
        self.fallthrough = fallthrough
        self._selected: FWrap[..., Any] | None = None

    @property
    @override
    def name(self) -> str:
        if self._selected is not None:
            return str(self._selected)
        if self.fallthrough is not None:
            return self.fallthrough.name
        return type(self).__name__

    @property
    @override
    def scope(self) -> InjectionScope:
        return InjectionScope.IMMEDIATE

    def _select(self, context: ResolutionContext) -> FWrap[..., Any] | None:
        for fallback in self.fallbacks:
            if fallback.supports(context):
                return wrap_func(fallback.resolve)
        return None

    @override
    def get_resolution_hints(self, context: ResolutionContext) -> Mapping[str, TWrap[Any] | ServiceResolver[..., Any]]:
        self._selected = self._select(context)
        if self._selected is not None:
            return self._selected.get_signature_hints(belongs_to=context.origin)
        if self.fallthrough is not None:
            return self.fallthrough.get_resolution_hints(context)
        return {}

    @override
    def get_instance_function(self) -> FWrap[..., Any]:
        if self._selected is not None:
            return self._selected
        if self.fallthrough is not None:
            return self.fallthrough.get_instance_function()
        return self._empty_resolver_w

    @override
    def get_resolution_signature(self) -> inspect.Signature:
        if self._selected is not None:
            return self._selected.signature
        if self.fallthrough is not None:
            return self.fallthrough.get_resolution_signature()
        return self._empty_resolver_w.signature

    @override
    def get_resolution_func(self, context: ResolutionContext) -> ResolutionFunction[..., Any]:
        if self._selected is not None:
            return self._selected
        if self.fallthrough is not None:
            return self.fallthrough.get_resolution_func(context)
        raise ServiceNotFoundError(str(context.required))

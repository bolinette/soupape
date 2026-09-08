from typing import Any, Protocol, runtime_checkable

from peritype import TWrap, wrap_func

from soupape._resolvers import FunctionResolver
from soupape._types import InjectionScope
from soupape._utils import ResolverCache


@runtime_checkable
class AnnotatedResolutionFunction(Protocol):
    def __resolve__(self, *args: Any, **kwargs: Any) -> Any: ...


def _find_annotated_resolution_function(hint: TWrap[Any]) -> AnnotatedResolutionFunction | None:
    for anno in hint.annotations:
        if isinstance(anno, AnnotatedResolutionFunction):
            return anno
    return None


def get_annotated_resolver(
    hint: TWrap[Any], scope: InjectionScope, cache: ResolverCache
) -> FunctionResolver[..., Any] | None:
    if hint in cache.annotated_markers:
        anno = cache.annotated_markers[hint]
    else:
        anno = cache.annotated_markers[hint] = _find_annotated_resolution_function(hint)
    if anno is None:
        return None
    return FunctionResolver(scope, wrap_func(anno.__resolve__))

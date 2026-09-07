from typing import Any, Protocol, runtime_checkable

from peritype import TWrap, wrap_func

from soupape._resolvers import FunctionResolver
from soupape._types import InjectionScope


@runtime_checkable
class AnnotatedResolutionFunction(Protocol):
    def __resolve__(self, *args: Any, **kwargs: Any) -> Any: ...


def get_annotated_resolver(hint: TWrap[Any], scope: InjectionScope) -> FunctionResolver[..., Any] | None:
    for anno in hint.annotations:
        if isinstance(anno, AnnotatedResolutionFunction):
            return FunctionResolver(scope, wrap_func(anno.__resolve__))

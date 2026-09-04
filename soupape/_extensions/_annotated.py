from collections.abc import Callable
from typing import Any, Concatenate, Protocol, runtime_checkable

from peritype import TWrap, wrap_func

from soupape._resolvers import FunctionResolver
from soupape._types import InjectionScope


@runtime_checkable
class AnnotatedResolveFunction(Protocol):
    def __resolve__(self, *args: Any, **kwargs: Any) -> Any: ...


def get_annotated_resolver(hint: TWrap[Any], scope: InjectionScope) -> FunctionResolver[..., Any] | None:
    for anno in hint.annotations:
        if isinstance(anno, AnnotatedResolveFunction):
            return FunctionResolver(scope, wrap_func(anno.__resolve__))


def make_annotated_resolver[T](cls: type[T], resolve_func: Callable[Concatenate[T, ...], Any]) -> None:
    cls.__resolve__ = resolve_func  # pyright: ignore[reportAttributeAccessIssue]

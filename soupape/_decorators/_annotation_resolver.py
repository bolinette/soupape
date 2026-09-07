from collections.abc import Callable
from typing import Any, Concatenate, overload


def _set_resolution_function[T](cls: type[T], resolve_func: Callable[Concatenate[T, ...], Any]) -> None:
    cls.__resolve__ = resolve_func  # pyright: ignore[reportAttributeAccessIssue]


@overload
def annotation_resolver[T, **P, R](
    cls: type[T], resolve_func: Callable[Concatenate[T, P], R], /
) -> Callable[Concatenate[T, P], R]: ...
@overload
def annotation_resolver[T](
    cls: type[T], /
) -> Callable[[Callable[Concatenate[T, ...], Any]], Callable[Concatenate[T, ...], Any]]: ...
def annotation_resolver(*args: Any) -> Any:
    match args:
        case (cls, resolve_func):
            _set_resolution_function(cls, resolve_func)
            return resolve_func
        case (cls,):

            def inner(resolve_func: Callable[Concatenate[Any, ...], Any]) -> Callable[Concatenate[Any, ...], Any]:
                _set_resolution_function(cls, resolve_func)
                return resolve_func

            return inner
        case _:
            raise TypeError(f"Unknown parameters {args}")

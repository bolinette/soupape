from collections.abc import Awaitable, Callable
from typing import Any, overload

from soupape.utils import meta


class PostInitMetadata:
    KEY = "post_init"


@overload
def post_init[**P](func: Callable[P, Awaitable[None]]) -> Callable[P, Awaitable[None]]: ...
@overload
def post_init[**P](func: Callable[P, None]) -> Callable[P, None]: ...
def post_init(func: Callable[..., Any]) -> Callable[..., Any]:
    meta.set(func, PostInitMetadata.KEY, PostInitMetadata())
    return func

from collections.abc import Callable
from typing import Any, overload

from peritype import FWrap, TWrap

from soupape._resolvers import ServiceResolver
from soupape._utils import get_meta_on_fwrap, get_meta_on_twrap, meta


class InjectionCustomResolver:
    KEY = "__soupape_resolver__"

    def __init__(self, resolver: ServiceResolver[..., Any]) -> None:
        self.resolver = resolver


def _set_resolver(resolvable: Callable[..., Any], resolver: ServiceResolver[..., Any]) -> None:
    meta.set(resolvable, InjectionCustomResolver.KEY, resolver)


def get_custom_resolver(interface: TWrap[Any] | FWrap[..., Any]) -> ServiceResolver[..., Any] | None:
    if isinstance(interface, FWrap):
        return get_meta_on_fwrap(interface, InjectionCustomResolver.KEY, ServiceResolver[..., Any], None)
    return get_meta_on_twrap(interface, InjectionCustomResolver.KEY, ServiceResolver[..., Any], None)


@overload
def resolver[T](res: ServiceResolver[..., Any], /) -> Callable[[T], T]: ...
@overload
def resolver[T](resolvable: T, resolver: ServiceResolver[..., Any], /) -> T: ...
def resolver(*args: Any) -> Any:
    match args:
        case (resolvable, resolver):
            _set_resolver(resolvable, resolver)
        case (resolver,):

            def inner(resolvable: Any) -> Any:
                meta.set(resolvable, InjectionCustomResolver.KEY, resolver)
                return resolvable

            return inner
        case _:
            raise TypeError()

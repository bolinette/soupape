import itertools
from collections.abc import Callable, Iterable
from typing import Any, TypeGuard, get_origin

from hafersack import Hafersack
from peritype import FWrap, TWrap

from soupape.errors import CircularDependencyError


class CircularGuard:
    def __init__(self) -> None:
        self._order: list[Callable[..., Any]] = []
        self._set: set[Callable[..., Any]] = set()

    def enter(self, fwrap: FWrap[..., Any]) -> None:
        func = fwrap.func
        if func in self._set:
            raise CircularDependencyError([*self._order, func])
        self._order.append(func)
        self._set.add(func)

    def copy(self) -> "CircularGuard":
        new_guard = CircularGuard()
        new_guard._order = self._order.copy()
        new_guard._set = self._set.copy()
        return new_guard


def is_type_like(obj: Any) -> TypeGuard[type[Any]]:
    return isinstance(obj, type) or get_origin(obj) is not None


def add_type_to_type_globals(receiving: type[Any], received: type[Any]) -> None:
    """
    Adds `received` inside `receiving`'s globals, making sure no :py:class:`NameError` is raised.

    This is useful when using classes defined in a local scope.
    """
    receiving.__init__.__globals__[received.__name__] = received  # type: ignore


def get_meta_on_twrap[T](
    interface: TWrap[Any],
    key: str,
    hint: type[T],
    default: T | None,
) -> T | None:
    if meta.has(interface.origin, key):
        return meta.get(interface.origin, key)
    if (interface_origin := get_origin(interface.origin)) is not None and meta.has(interface_origin, key):
        return meta.get(interface_origin, key)
    return default


def get_meta_on_fwrap[**P, T](
    func: FWrap[P, T],
    key: str,
    hint: type[T],
    default: T | None,
) -> T | None:
    if meta.has(func.func, key):
        return meta.get(func.func, key)
    if (func_origin := get_origin(func.func)) is not None and meta.has(func_origin, key):
        return meta.get(func_origin, key)
    return default


def accumulate_meta_on_twrap[T](interface: TWrap[Any], key: str, factory: Callable[[], Iterable[T]]) -> Iterable[T]:
    meta_list = factory()
    if meta.has(interface.origin, key):
        deps_meta: Iterable[T] = meta.get(interface.origin, key)
        meta_list = itertools.chain(meta_list, deps_meta)
    if (interface_origin := get_origin(interface.origin)) is not None and meta.has(interface_origin, key):
        deps_meta: Iterable[T] = meta.get(interface_origin, key)
        meta_list = itertools.chain(meta_list, deps_meta)
    return meta_list


meta = Hafersack("__soupape__")

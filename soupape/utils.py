from collections.abc import Callable
from typing import Any, TypeGuard, get_origin

from hafersack import Hafersack
from peritype import FWrap

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


meta = Hafersack("soupape")

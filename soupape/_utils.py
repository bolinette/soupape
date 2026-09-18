from collections.abc import Callable
from typing import TYPE_CHECKING, Any, ClassVar, Self, TypeGuard, get_origin, override

from hafersack import Hafersack
from peritype import FWrap, TWrap

from soupape.errors import CircularDependencyError

if TYPE_CHECKING:
    from soupape._resolvers import ServiceResolver
    from soupape._traits import AnnotatedResolutionFunction

type CircularGuardKey = Callable[..., Any] | TWrap[Any]


class Absent:
    __slots__ = ()
    _instance: "ClassVar[Absent | None]" = None

    def __new__(cls) -> Self:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance  # pyright: ignore[reportReturnType]

    @override
    def __repr__(self) -> str:
        return "ABSENT"

    def __bool__(self) -> bool:
        return False


class ResolverCache:
    def __init__(self) -> None:
        self.custom_resolvers: dict[TWrap[Any] | FWrap[..., Any], ServiceResolver[..., Any] | None] = {}
        self.annotated_markers: dict[TWrap[Any], AnnotatedResolutionFunction | None] = {}


class CircularGuard:
    def __init__(self) -> None:
        self._order: list[CircularGuardKey] = []
        self._set: set[CircularGuardKey] = set()

    def enter(self, fwrap: FWrap[..., Any]) -> None:
        self._enter(fwrap.func)

    def enter_type(self, twrap: TWrap[Any]) -> None:
        self._enter(twrap)

    def _enter(self, key: CircularGuardKey) -> None:
        if key in self._set:
            raise CircularDependencyError([*self._order, key])
        self._order.append(key)
        self._set.add(key)

    @property
    def trace(self) -> tuple[CircularGuardKey, ...]:
        return tuple(self._order)

    @classmethod
    def from_trace(cls, trace: tuple[CircularGuardKey, ...]) -> "CircularGuard":
        guard = cls()
        guard._order = list(trace)
        guard._set = set(trace)
        return guard

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
    receiving.__init__.__globals__[received.__name__] = received  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]


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
    return default


meta = Hafersack("__soupape__")

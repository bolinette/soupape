from collections.abc import AsyncGenerator, AsyncIterable, Awaitable, Callable, Coroutine, Generator, Iterable
from dataclasses import dataclass
from enum import Enum, auto, unique
from types import TracebackType
from typing import TYPE_CHECKING, Any, NotRequired, Protocol, TypedDict, Unpack, runtime_checkable

from peritype import FWrap, TWrap

from soupape._instances import InstancePoolStack
from soupape._utils import CircularGuard

if TYPE_CHECKING:
    from soupape import ServiceCollection

type ResolveFunction[**P, T] = (
    Callable[P, T]
    | Callable[P, Generator[T]]
    | Callable[P, Iterable[T]]
    | Callable[P, AsyncGenerator[T]]
    | Callable[P, AsyncIterable[T]]
    | Callable[P, Coroutine[Any, Any, T]]
    | Callable[P, Awaitable[T]]
)


class InjectorCallArgs(TypedDict):
    positional_args: NotRequired[list[Any]]
    origin: NotRequired[TWrap[Any] | None]
    circular_guard: NotRequired[CircularGuard]


class Injector(Protocol):
    @property
    def is_async(self) -> bool: ...

    @property
    def instances(self) -> InstancePoolStack: ...

    @property
    def services(self) -> "ServiceCollection": ...

    def require[T](self, interface: type[T] | TWrap[T]) -> T | Awaitable[T]: ...

    def call[T](
        self,
        callable: Callable[..., T] | FWrap[..., T],
        **kwargs: Unpack[InjectorCallArgs],
    ) -> T | Awaitable[T]: ...

    def get_scoped_injector(self) -> "Injector": ...


@unique
class InjectionScope(Enum):
    SINGLETON = auto()
    SCOPED = auto()
    TRANSIENT = auto()
    IMMEDIATE = auto()


@dataclass(kw_only=True)
class InjectionContext:
    injector: Injector
    origin: TWrap[Any] | None
    scope: "InjectionScope"
    circular_guard: CircularGuard
    required: TWrap[Any] | None
    positional_args: list[Any] | None = None

    def new_required(
        self,
        scope: "InjectionScope",
        required: TWrap[Any] | None,
    ) -> "InjectionContext":
        return InjectionContext(
            injector=self.injector,
            origin=self.origin,
            scope=scope,
            circular_guard=self.circular_guard.copy(),
            required=required,
            positional_args=None,
        )

    def copy(
        self,
    ) -> "InjectionContext":
        return InjectionContext(
            injector=self.injector,
            origin=self.origin,
            scope=self.scope,
            circular_guard=self.circular_guard.copy(),
            required=self.required,
            positional_args=self.positional_args,
        )


@runtime_checkable
class SyncContextManager(Protocol):
    def __enter__(self) -> "SyncContextManager": ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...


@runtime_checkable
class AsyncContextManager(Protocol):
    async def __aenter__(self) -> "AsyncContextManager": ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

from collections.abc import AsyncGenerator, AsyncIterable, Awaitable, Callable, Coroutine, Generator, Iterable
from dataclasses import dataclass
from enum import Enum, auto, unique
from types import TracebackType
from typing import Any, NotRequired, Protocol, TypedDict, Unpack, runtime_checkable

from peritype import FWrap, TWrap

from soupape.instances import InstancePoolStack

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


class Injector(Protocol):
    @property
    def is_async(self) -> bool: ...

    @property
    def instances(self) -> InstancePoolStack: ...

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


@dataclass
class InjectionContext:
    injector: Injector
    origin: TWrap[Any] | None
    scope: "InjectionScope"
    required: TWrap[Any] | None
    positional_args: list[Any] | None = None

    def copy(
        self,
        scope: "InjectionScope",
        required: TWrap[Any] | None = None,
        positional_args: list[Any] | None = None,
    ) -> "InjectionContext":
        return InjectionContext(
            injector=self.injector,
            origin=self.origin,
            scope=scope,
            required=required,
            positional_args=positional_args,
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

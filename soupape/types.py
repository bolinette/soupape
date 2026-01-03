import inspect
from collections.abc import AsyncGenerator, AsyncIterable, Awaitable, Callable, Coroutine, Generator, Iterable
from dataclasses import dataclass
from enum import Enum, auto, unique
from types import TracebackType
from typing import Any, NotRequired, Protocol, TypedDict, Unpack, runtime_checkable

from peritype import FWrap, TWrap

type ServiceResolver[**P, T] = (
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


class Injector(Protocol):
    @property
    def is_async(self) -> bool: ...

    def require[T](self, interface: type[T] | TWrap[T]) -> T | Awaitable[T]: ...

    def call[T](
        self,
        callable: Callable[..., T] | FWrap[..., T],
        **kwargs: Unpack[InjectorCallArgs],
    ) -> T | Awaitable[T]: ...

    def get_scoped_injector(self) -> "Injector": ...


@runtime_checkable
class ServiceResolverFactory(Protocol):
    def with_injector(self, injector: Injector) -> "ServiceResolver[..., Any]": ...


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


@unique
class InjectionScope(Enum):
    SINGLETON = auto()
    SCOPED = auto()
    TRANSIENT = auto()
    IMMEDIATE = auto()


@dataclass
class ResolverMetadata[**P, T]:
    scope: InjectionScope
    signature: inspect.Signature
    fwrap: FWrap[P, T]
    resolver: ServiceResolver[P, T]


@dataclass
class TypeResolverMetadata[**P, T](ResolverMetadata[P, T]):
    interface: TWrap[T]
    implementation: TWrap[Any]


@dataclass
class ResolverCallArgs[**P, T]:
    scope: InjectionScope
    args: "list[ResolverCallArgs[..., Any]]"
    kwargs: "dict[str, ResolverCallArgs[..., Any]]"
    resolver: ServiceResolver[P, T]
    interface: TWrap[T] | None

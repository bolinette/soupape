import inspect
from collections.abc import Awaitable, Callable, Coroutine
from dataclasses import dataclass
from enum import Enum, auto, unique
from typing import Any, NotRequired, Protocol, TypedDict, Unpack

from peritype import FWrap, TWrap

type ServiceResolver[**P, T] = Callable[P, T] | Callable[P, Coroutine[Any, Any, T]]


class InjectorCallArgs(TypedDict):
    positional_args: NotRequired[list[Any]]


class Injector(Protocol):
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

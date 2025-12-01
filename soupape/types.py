import inspect
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from enum import Enum, auto, unique
from typing import Any

from peritype import FWrap, TWrap

type ServiceResolver[**P, T] = Callable[P, T] | Callable[P, Coroutine[Any, Any, T]]


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

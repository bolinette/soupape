import inspect
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from peritype import TWrap

from soupape.types import InjectionContext, InjectionScope, ResolveFunction


class ServiceResolver[**P, T](ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def scope(self) -> InjectionScope: ...

    @property
    @abstractmethod
    def required(self) -> TWrap[T] | None: ...

    @property
    @abstractmethod
    def registered(self) -> TWrap[Any] | None: ...

    @abstractmethod
    def get_resolve_hints(self, *, belongs_to: TWrap[Any] | None = None) -> dict[str, TWrap[Any]]: ...

    @abstractmethod
    def get_resolve_signature(self) -> inspect.Signature: ...

    @abstractmethod
    def get_resolve_func(self, context: InjectionContext) -> ResolveFunction[P, T]: ...


@dataclass(kw_only=True)
class DependencyTreeNode[**P, T]:
    scope: InjectionScope
    args: "list[DependencyTreeNode[..., Any]]"
    kwargs: "dict[str, DependencyTreeNode[..., Any]]"
    resolver: ServiceResolver[P, T]
    required: TWrap[T] | None
    registered: TWrap[Any] | None

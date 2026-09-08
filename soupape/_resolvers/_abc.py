import inspect
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from peritype import FWrap, TWrap, wrap_func

from soupape._types import CallerContext, InjectionScope, ResolutionContext, ResolutionFunction
from soupape._utils import CircularGuardKey


class ServiceResolver[**P, T](ABC):
    @staticmethod  # noqa: B027
    def _empty_resolver() -> T: ...

    _empty_resolver_w = wrap_func(_empty_resolver)

    @property
    def name(self) -> str:
        return type(self).__name__

    @property
    @abstractmethod
    def scope(self) -> InjectionScope: ...

    @property
    def required(self) -> TWrap[T] | None:
        return None

    @property
    def registered(self) -> TWrap[Any] | None:
        return None

    @abstractmethod
    def get_resolution_hints(
        self, context: ResolutionContext
    ) -> "Mapping[str, TWrap[Any] | ServiceResolver[..., Any]]": ...

    @abstractmethod
    def get_instance_function(self) -> FWrap[P, T]: ...

    @abstractmethod
    def get_resolution_signature(self) -> inspect.Signature: ...

    @abstractmethod
    def get_resolution_func(self, context: ResolutionContext) -> ResolutionFunction[P, T]: ...


@dataclass(kw_only=True, frozen=True, slots=True)
class DependencyTreeNode[**P, T]:
    scope: InjectionScope
    args: "list[DependencyTreeNode[..., Any]]"
    kwargs: "dict[str, DependencyTreeNode[..., Any]]"
    resolver: ServiceResolver[P, T]
    required: TWrap[T] | None
    registered: TWrap[Any] | None
    origin: TWrap[Any] | None
    caller_context: CallerContext | None
    singleton_owner: ServiceResolver[..., Any] | None
    trace: tuple[CircularGuardKey, ...]
    parent: "DependencyTreeNode[..., Any] | None"

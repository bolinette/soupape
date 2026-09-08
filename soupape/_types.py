from collections.abc import AsyncGenerator, AsyncIterable, Awaitable, Callable, Coroutine, Generator, Iterable
from dataclasses import dataclass
from enum import Enum, auto, unique
from types import TracebackType
from typing import TYPE_CHECKING, Any, Never, Protocol, override, runtime_checkable

from peritype import FWrap, TWrap

from soupape._instances import InstancePoolStack
from soupape._utils import CircularGuard

if TYPE_CHECKING:
    from soupape import ServiceCollection
    from soupape._resolvers import DependencyTreeNode

type ResolutionFunction[**P, T] = Callable[
    P,
    T
    | Generator[T, Never, Any]
    | Iterable[T]
    | AsyncGenerator[T, Never]
    | AsyncIterable[T]
    | Coroutine[Any, Any, T]
    | Awaitable[T],
]


class Injector(Protocol):
    @property
    def is_async(self) -> bool: ...

    @property
    def instances(self) -> InstancePoolStack: ...

    @property
    def services(self) -> "ServiceCollection": ...

    def get_scoped_injector(self) -> "Injector": ...


class ResolvingInjector(Injector, Protocol):
    def require[T](self, interface: type[T] | TWrap[T]) -> T | Awaitable[T]: ...

    def call[T](
        self,
        callable: Callable[..., T] | FWrap[..., T],
        *,
        positional_args: list[Any] | None = None,
        named_args: dict[str, Any] | None = None,
    ) -> T | Awaitable[T]: ...


type RequireWithin = Callable[[type[Any] | TWrap[Any], CircularGuard], Any]
type CallWithin = Callable[
    [Callable[..., Any] | FWrap[..., Any], list[Any], dict[str, Any], TWrap[Any] | None, CircularGuard], Any
]


@unique
class InjectionScope(Enum):
    SINGLETON = auto()
    SCOPED = auto()
    TRANSIENT = auto()
    IMMEDIATE = auto()


@dataclass(kw_only=True, frozen=True, slots=True)
class CallerContext:
    caller: FWrap[..., Any]
    param_name: str


@dataclass(kw_only=True, frozen=True, slots=True)
class ResolutionContext:
    injector: ResolvingInjector
    origin: TWrap[Any] | None
    scope: "InjectionScope"
    required: TWrap[Any] | None
    caller_context: CallerContext | None = None

    def copy(self) -> "ResolutionContext":
        return ResolutionContext(
            injector=self.injector,
            origin=self.origin,
            scope=self.scope,
            required=self.required,
            caller_context=self.caller_context,
        )

    def require[T](self, interface: type[T] | TWrap[T]) -> T | Awaitable[T]:
        return self.injector.require(interface)

    def call[T](
        self,
        callable: Callable[..., T] | FWrap[..., T],
        positional_args: list[Any] | None = None,
        named_args: dict[str, Any] | None = None,
    ) -> T | Awaitable[T]:
        return self.injector.call(callable, positional_args=positional_args, named_args=named_args)


@dataclass(kw_only=True, frozen=True, slots=True)
class InjectionContext(ResolutionContext):
    node: "DependencyTreeNode[..., Any]"
    require_within: RequireWithin
    call_within: CallWithin

    @override
    def require[T](self, interface: type[T] | TWrap[T]) -> T | Awaitable[T]:
        return self.require_within(interface, CircularGuard.from_trace(self.node.trace))

    @override
    def call[T](
        self,
        callable: Callable[..., T] | FWrap[..., T],
        positional_args: list[Any] | None = None,
        named_args: dict[str, Any] | None = None,
    ) -> T | Awaitable[T]:
        return self.call_within(
            callable, positional_args or [], named_args or {}, self.origin, CircularGuard.from_trace(self.node.trace)
        )

    def parent_frame(self) -> ResolutionContext:
        parent = self.node.parent
        if parent is None:
            return self.copy()
        return ResolutionContext(
            injector=self.injector,
            origin=parent.origin,
            scope=parent.scope,
            required=parent.required,
            caller_context=parent.caller_context,
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

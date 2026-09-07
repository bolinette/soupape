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
    from soupape._resolvers import ServiceResolver

type ResolutionFunction[**P, T] = (
    Callable[P, T]
    | Callable[P, Generator[T, Never, Any]]
    | Callable[P, Iterable[T]]
    | Callable[P, AsyncGenerator[T, Never]]
    | Callable[P, AsyncIterable[T]]
    | Callable[P, Coroutine[Any, Any, T]]
    | Callable[P, Awaitable[T]]
)


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
    circular_guard: CircularGuard
    require_within: RequireWithin
    call_within: CallWithin
    positional_args: list[Any] | None = None
    named_args: dict[str, Any] | None = None
    singleton_owner: "ServiceResolver[..., Any] | None" = None
    parent: "InjectionContext | None" = None

    @override
    def require[T](self, interface: type[T] | TWrap[T]) -> T | Awaitable[T]:
        return self.require_within(interface, self.circular_guard.copy())

    @override
    def call[T](
        self,
        callable: Callable[..., T] | FWrap[..., T],
        positional_args: list[Any] | None = None,
        named_args: dict[str, Any] | None = None,
    ) -> T | Awaitable[T]:
        return self.call_within(
            callable, positional_args or [], named_args or {}, self.origin, self.circular_guard.copy()
        )

    def new_required(
        self,
        scope: "InjectionScope",
        required: TWrap[Any] | None,
        caller_context: CallerContext | None = None,
    ) -> "InjectionContext":
        return InjectionContext(
            injector=self.injector,
            origin=required if required is not None else self.origin,
            scope=scope,
            circular_guard=self.circular_guard.copy(),
            required=required,
            positional_args=None,
            named_args=None,
            caller_context=caller_context,
            require_within=self.require_within,
            call_within=self.call_within,
            singleton_owner=self.singleton_owner,
            parent=self,
        )

    def with_singleton_owner(self, owner: "ServiceResolver[..., Any]") -> "InjectionContext":
        return InjectionContext(
            injector=self.injector,
            origin=self.origin,
            scope=self.scope,
            circular_guard=self.circular_guard,
            required=self.required,
            positional_args=self.positional_args,
            named_args=self.named_args,
            caller_context=self.caller_context,
            require_within=self.require_within,
            call_within=self.call_within,
            singleton_owner=owner,
            parent=self.parent,
        )

    def fork(self) -> "InjectionContext":
        return InjectionContext(
            injector=self.injector,
            origin=self.origin,
            scope=self.scope,
            circular_guard=self.circular_guard.copy(),
            required=self.required,
            positional_args=self.positional_args,
            named_args=self.named_args,
            caller_context=self.caller_context,
            require_within=self.require_within,
            call_within=self.call_within,
            singleton_owner=self.singleton_owner,
            parent=self.parent,
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

import inspect
from collections.abc import AsyncIterable, Awaitable, Callable, Sequence
from typing import Any

from peritype import TWrap


class SoupapeError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message


class ServiceNotFoundError(SoupapeError):
    def __init__(self, interface: str) -> None:
        super().__init__(
            "soupape.service.not_found",
            f"Service for interface '{interface}' not found.",
        )


class MissingTypeHintError(SoupapeError):
    def __init__(self, parameter: str, fwrap: str) -> None:
        super().__init__(
            "soupape.type_hint.missing",
            f"Missing type hint for parameter '{parameter}' of '{fwrap}'.",
        )


class ScopedServiceNotAvailableError(SoupapeError):
    def __init__(self, interface: str) -> None:
        super().__init__(
            "soupape.scoped_service.not_available",
            f"Scoped service for interface '{interface}' is not available in the root scope.",
        )


class CaptiveDependencyError(SoupapeError):
    def __init__(self, singleton: str, dependency: str) -> None:
        super().__init__(
            "soupape.dependency.captive",
            f"Singleton service '{singleton}' cannot depend on scoped service '{dependency}'.",
        )
        self.singleton = singleton
        self.dependency = dependency


class AsyncInSyncInjectorError(SoupapeError):
    def __init__(self, coro: Awaitable[Any] | AsyncIterable[Any]) -> None:
        super().__init__(
            "soupape.injector.async_in_sync",
            "Cannot call asynchronous resolver in synchronous injector.",
        )
        if inspect.iscoroutine(coro):
            coro.close()


class AsyncContextManagerInSyncInjectorError(SoupapeError):
    def __init__(self, service: str) -> None:
        super().__init__(
            "soupape.injector.async_context_manager_in_sync",
            f"Service '{service}' is an async context manager and cannot be entered by the synchronous injector.",
        )
        self.service = service


class CircularDependencyError(SoupapeError):
    def __init__(self, trace: Sequence[Callable[..., Any] | TWrap[Any]]) -> None:
        super().__init__(
            "soupape.dependency.circular",
            "Injection cycle detected.\n" + "\n ↳ ".join(f"{i + 1}. {step}" for i, step in enumerate(trace)),
        )
        self.trace = trace


class IncompatibleInterfaceError(SoupapeError):
    def __init__(self, interface: str, implementation: str) -> None:
        super().__init__(
            "soupape.interface.incompatible",
            f"Interface {interface} is not compatible with type {implementation}",
        )
        self.interface = interface
        self.implementation = implementation


class MissingInterfaceError(SoupapeError):
    def __init__(self, resolver: str) -> None:
        super().__init__(
            "soupape.interface.missing",
            f"Interface missing for resolver '{resolver}': no return type hint or required type.",
        )
        self.resolver = resolver


class ServiceAlreadyRegisteredError(SoupapeError):
    def __init__(self, interface: str) -> None:
        super().__init__(
            "soupape.service.already_registered",
            f"Service for interface '{interface}' is already registered.",
        )
        self.interface = interface


class InvalidResolverReturnHintError(SoupapeError):
    def __init__(self, resolver: str, accepted: Sequence[str]) -> None:
        hints = " or ".join([", ".join(accepted[:-1]), accepted[-1]])
        super().__init__(
            "soupape.resolver.invalid_return_hint",
            f"Resolver '{resolver}' must have a return type hint of {hints}.",
        )
        self.resolver = resolver
        self.accepted = tuple(accepted)


class UnknownInjectionScopeError(SoupapeError):
    def __init__(self, scope: object) -> None:
        super().__init__(
            "soupape.scope.unknown",
            f"Unknown injection scope: {scope}.",
        )
        self.scope = scope


class UnresolvedAnyTypeError(SoupapeError):
    def __init__(self, interface: str) -> None:
        super().__init__(
            "soupape.type.unresolved_any",
            f"Cannot store an instance for type '{interface}': it still contains Any.",
        )
        self.interface = interface

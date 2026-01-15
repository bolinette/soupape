from collections.abc import AsyncIterable, Awaitable, Callable, Sequence
from typing import Any


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


class AsyncInSyncInjectorError(SoupapeError):
    def __init__(self, coro: Awaitable[Any] | AsyncIterable[Any]) -> None:
        super().__init__(
            "soupape.injector.async_in_sync",
            "Cannot call asynchronous resolver in synchronous injector.",
        )
        self._coro = coro

    async def close(self) -> None:
        if isinstance(self._coro, Awaitable):
            await self._coro


class CircularDependencyError(SoupapeError):
    def __init__(self, trace: Sequence[Callable[..., Any]]) -> None:
        super().__init__(
            "soupape.dependency.circular",
            "Injection cycle detected.\n" + "\n ↳ ".join(f"{i + 1}. {func}" for i, func in enumerate(trace)),
        )
        self.trace = trace

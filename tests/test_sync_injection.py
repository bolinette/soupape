"""Behaviour only `SyncInjector` can exhibit.

Injection paths shared with `AsyncInjector` live in `test_base_injection.py`; this file
covers what happens when an asynchronous construct reaches an injector that cannot await
it. Each of those raises `AsyncInSyncInjectorError`, which closes the coroutine the injector
refused to run, except for an async-only context-manager service, which raises
`AsyncContextManagerInSyncInjectorError` before it is entered.
"""

import asyncio
import warnings
from collections.abc import AsyncGenerator
from types import TracebackType

import pytest

from soupape import ServiceCollection, SyncInjector, post_init
from soupape.errors import AsyncContextManagerInSyncInjectorError, AsyncInSyncInjectorError


class TestSyncInjectorRequirements:
    def test_require_sync_injector(self) -> None:
        """A service can depend on `SyncInjector` by its concrete type."""

        class Service:
            def __init__(self, injector: SyncInjector) -> None:
                self.injector = injector

        services = ServiceCollection()
        services.add_singleton(Service)

        with SyncInjector(services) as injector:
            service = injector.require(Service)
            assert service.injector is injector


class TestFailAsyncInSyncInjector:
    def test_fail_async_resolver(self) -> None:
        """A coroutine resolver cannot be awaited, so requiring the service fails."""
        services = ServiceCollection()

        class AsyncService:
            def __init__(self) -> None: ...

            async def fetch_data(self) -> str: ...

        async def async_service_resolver() -> AsyncService: ...

        services.add_singleton(async_service_resolver)

        with SyncInjector(services) as injector:
            with pytest.raises(AsyncInSyncInjectorError):
                injector.require(AsyncService)

    def test_fail_call_async_function(self) -> None:
        """`call` on a coroutine function fails."""
        services = ServiceCollection()

        class DependencyService:
            def __init__(self) -> None:
                pass

            def get_value(self) -> str: ...

        services.add_singleton(DependencyService)

        with SyncInjector(services) as injector:

            async def test_function(dep_service: DependencyService) -> str: ...

            with pytest.raises(AsyncInSyncInjectorError):
                _ = injector.call(test_function)

    def test_fail_async_post_init(self) -> None:
        """A coroutine `post_init` hook fails while the instance is being built."""
        services = ServiceCollection()

        class TestService:
            def __init__(self) -> None:
                self.initialized = False

            @post_init
            async def initialize(self) -> None:
                await asyncio.sleep(0)
                self.initialized = True

        services.add_singleton(TestService)

        with SyncInjector(services) as injector:
            with pytest.raises(AsyncInSyncInjectorError):
                injector.require(TestService)

    def test_fail_async_yield_resolver(self) -> None:
        """An async generator resolver fails."""
        services = ServiceCollection()

        class Resource:
            def __init__(self) -> None:
                self.active = True

            def close(self) -> None:
                self.active = False

        async def resource_resolver() -> AsyncGenerator[Resource]:
            res = Resource()
            yield res

        services.add_singleton(resource_resolver)

        with SyncInjector(services) as injector:
            with pytest.raises(AsyncInSyncInjectorError):
                injector.require(Resource)

    def test_fail_context_manager_async_resolver(self) -> None:
        """An async generator resolver with teardown fails the same way."""
        services = ServiceCollection()

        class Resource:
            def __init__(self) -> None:
                self.active = True

            def close(self) -> None:
                self.active = False

        async def resource_resolver() -> AsyncGenerator[Resource]:
            res = Resource()
            yield res
            res.close()

        services.add_singleton(resource_resolver)

        with SyncInjector(services) as injector:
            with pytest.raises(AsyncInSyncInjectorError):
                injector.require(Resource)

    def test_refused_coroutine_is_closed_without_warning(self) -> None:
        """The refused coroutine is closed by the error, so nothing is left un-awaited."""
        services = ServiceCollection()

        class AsyncService:
            def __init__(self) -> None: ...

        async def async_service_resolver() -> AsyncService:
            return AsyncService()

        services.add_singleton(async_service_resolver)

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            with SyncInjector(services) as injector, pytest.raises(AsyncInSyncInjectorError):
                injector.require(AsyncService)

        assert not [warning for warning in caught if "never awaited" in str(warning.message)]


class TestAsyncContextManagerServices:
    def test_fail_async_context_manager_service(self) -> None:
        """A service that is only an async context manager cannot be entered, so requiring it fails."""
        services = ServiceCollection()
        events: list[str] = []

        class Resource:
            async def __aenter__(self) -> "Resource":
                events.append("aenter")
                return self

            async def __aexit__(
                self,
                exc_type: type[BaseException],
                exc_value: BaseException | None,
                traceback: TracebackType | None,
            ) -> None:
                events.append("aexit")

            @post_init
            def setup(self) -> None:
                events.append("post_init")

        services.add_singleton(Resource)

        with SyncInjector(services) as injector:
            with pytest.raises(AsyncContextManagerInSyncInjectorError) as exc_info:
                injector.require(Resource)

        assert events == []
        assert exc_info.value.code == "soupape.injector.async_context_manager_in_sync"
        assert exc_info.value.service == Resource.__qualname__
        assert exc_info.value.message == (
            f"Service '{Resource.__qualname__}' is an async context manager "
            "and cannot be entered by the synchronous injector."
        )

    def test_fail_async_context_manager_dependency(self) -> None:
        """The same error is raised when the async context manager is a dependency of the required service."""
        services = ServiceCollection()

        class Resource:
            async def __aenter__(self) -> "Resource":
                return self

            async def __aexit__(
                self,
                exc_type: type[BaseException],
                exc_value: BaseException | None,
                traceback: TracebackType | None,
            ) -> None: ...

        class Service:
            def __init__(self, resource: Resource) -> None:
                self.resource = resource

        services.add_singleton(Resource)
        services.add_singleton(Service)

        with SyncInjector(services) as injector:
            with pytest.raises(AsyncContextManagerInSyncInjectorError):
                injector.require(Service)

    def test_service_with_both_protocols_uses_sync_context_manager(self) -> None:
        """A service implementing both protocols is entered and exited through the sync one."""
        services = ServiceCollection()
        events: list[str] = []

        class Resource:
            def __enter__(self) -> "Resource":
                events.append("enter")
                return self

            def __exit__(
                self,
                exc_type: type[BaseException] | None,
                exc_value: BaseException | None,
                traceback: TracebackType | None,
            ) -> None:
                events.append("exit")

            async def __aenter__(self) -> "Resource":
                events.append("aenter")
                return self

            async def __aexit__(
                self,
                exc_type: type[BaseException] | None,
                exc_value: BaseException | None,
                traceback: TracebackType | None,
            ) -> None:
                events.append("aexit")

        services.add_singleton(Resource)

        with SyncInjector(services) as injector:
            injector.require(Resource)
            assert events == ["enter"]
        assert events == ["enter", "exit"]

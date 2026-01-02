import asyncio

import pytest

from soupape import ServiceCollection, SyncInjector, post_init
from soupape.errors import (
    AsyncInSyncInjectorError,
)


def test_sync_inject() -> None:
    services = ServiceCollection()

    class TestService:
        def __init__(self) -> None:
            pass

        def greet(self) -> str:
            return "Hello from Sync!"

    services.add_singleton(TestService)
    injector = SyncInjector(services)

    service = injector.require(TestService)
    assert service.greet() == "Hello from Sync!"


@pytest.mark.asyncio
async def test_fail_async_call_in_sync_injector() -> None:
    services = ServiceCollection()

    class AsyncService:
        def __init__(self) -> None: ...

        async def fetch_data(self) -> str: ...

    async def async_service_resolver() -> AsyncService: ...

    services.add_singleton(async_service_resolver)
    injector = SyncInjector(services)

    with pytest.raises(AsyncInSyncInjectorError) as exc_info:
        injector.require(AsyncService)

    await exc_info.value.coro


def test_sync_injector_call_sync_function() -> None:
    services = ServiceCollection()

    class DependencyService:
        def __init__(self) -> None:
            pass

        def get_value(self) -> str:
            return "Injected Value in Sync"

    services.add_singleton(DependencyService)
    injector = SyncInjector(services)

    def test_function(dep_service: DependencyService) -> str:
        return dep_service.get_value()

    result = injector.call(test_function)
    assert result == "Injected Value in Sync"


@pytest.mark.asyncio
async def test_fail_call_async_function_in_sync_injector() -> None:
    services = ServiceCollection()

    class DependencyService:
        def __init__(self) -> None:
            pass

        def get_value(self) -> str: ...

    services.add_singleton(DependencyService)
    injector = SyncInjector(services)

    async def test_function(dep_service: DependencyService) -> str: ...

    with pytest.raises(AsyncInSyncInjectorError) as exc_info:
        await injector.call(test_function)

    await exc_info.value.coro


@pytest.mark.asyncio
async def test_sync_inject_service_with_positional_only_parameter() -> None:
    services = ServiceCollection()

    class PositionalService:
        def __init__(self) -> None:
            pass

        def greet(self) -> str:
            return "Hello from Positional!"

    services.add_singleton(PositionalService)

    class ServiceWithPositionalOnly:
        def __init__(self, /, pos_service: PositionalService) -> None:
            self.pos_service = pos_service

        def greet(self) -> str:
            return self.pos_service.greet()

    services.add_singleton(ServiceWithPositionalOnly)

    injector = SyncInjector(services)
    service = injector.require(ServiceWithPositionalOnly)

    assert service.greet() == "Hello from Positional!"


@pytest.mark.asyncio
async def test_sync_inject_service_with_keyword_only_parameter() -> None:
    services = ServiceCollection()

    class KeywordService:
        def __init__(self) -> None:
            pass

        def greet(self) -> str:
            return "Hello from Keyword!"

    services.add_singleton(KeywordService)

    class ServiceWithKeywordOnly:
        def __init__(self, *, key_service: KeywordService) -> None:
            self.key_service = key_service

        def greet(self) -> str:
            return self.key_service.greet()

    services.add_singleton(ServiceWithKeywordOnly)

    injector = SyncInjector(services)
    service = injector.require(ServiceWithKeywordOnly)

    assert service.greet() == "Hello from Keyword!"


@pytest.mark.asyncio
async def test_sync_inject_with_post_init() -> None:
    services = ServiceCollection()

    class TestService:
        def __init__(self) -> None:
            self.initialized = False

        @post_init
        def initialize(self) -> None:
            self.initialized = True

    services.add_singleton(TestService)

    injector = SyncInjector(services)
    service = injector.require(TestService)

    assert service.initialized is True


@pytest.mark.asyncio
async def test_fail_sync_inject_with_async_post_init() -> None:
    services = ServiceCollection()

    class TestService:
        def __init__(self) -> None:
            self.initialized = False

        @post_init
        async def initialize(self) -> None:
            await asyncio.sleep(0)
            self.initialized = True

    services.add_singleton(TestService)

    injector = SyncInjector(services)

    with pytest.raises(AsyncInSyncInjectorError) as exc_info:
        injector.require(TestService)

    await exc_info.value.coro

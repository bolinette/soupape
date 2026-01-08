import asyncio
from collections.abc import AsyncGenerator, Generator
from types import TracebackType

import pytest
from peritype import TWrap, wrap_type

from soupape import Injector, ServiceCollection, SyncInjector, post_init
from soupape.errors import AsyncInSyncInjectorError


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

    await exc_info.value.close()


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

    await exc_info.value.close()


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

    await exc_info.value.close()


@pytest.mark.asyncio
async def test_sync_inject_yield_resolver() -> None:
    services = ServiceCollection()

    class Resource:
        def __init__(self) -> None:
            self.active = True

        def close(self) -> None:
            self.active = False

    def resource_resolver() -> Generator[Resource]:
        res = Resource()
        yield res

    services.add_singleton(resource_resolver)

    injector = SyncInjector(services)
    resource = injector.require(Resource)

    assert resource.active is True


@pytest.mark.asyncio
async def test_fail_sync_inject_async_yield_resolver() -> None:
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

    injector = SyncInjector(services)
    with pytest.raises(AsyncInSyncInjectorError):
        injector.require(Resource)


@pytest.mark.asyncio
async def test_sync_injection_context_manager_sync_resolver() -> None:
    services = ServiceCollection()

    class Resource:
        def __init__(self) -> None:
            self.active = True

        def close(self) -> None:
            self.active = False

    def resource_resolver() -> Generator[Resource]:
        res = Resource()
        yield res
        res.close()

    services.add_singleton(resource_resolver)

    with SyncInjector(services) as injector:
        resource = injector.require(Resource)
        assert resource.active is True
    assert resource.active is False


@pytest.mark.asyncio
async def test_fail_sync_injection_context_manager_async_resolver() -> None:
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


@pytest.mark.asyncio
async def test_sync_injection_context_manager_service() -> None:
    services = ServiceCollection()

    class Resource:
        def __init__(self) -> None:
            self.active = True

        def __enter__(self) -> "Resource":
            return self

        def __exit__(
            self,
            exc_type: type[BaseException],
            exc_value: BaseException | None,
            traceback: TracebackType | None,
        ) -> None:
            self.active = False

    services.add_singleton(Resource)

    with SyncInjector(services) as injector:
        resource = injector.require(Resource)
        assert resource.active is True
    assert resource.active is False


@pytest.mark.asyncio
async def test_sync_injection_async_context_manager_service() -> None:
    services = ServiceCollection()

    class Resource:
        def __init__(self) -> None:
            self.active = True

        async def __aenter__(self) -> "Resource":
            return self

        async def __aexit__(
            self,
            exc_type: type[BaseException],
            exc_value: BaseException | None,
            traceback: TracebackType | None,
        ) -> None:
            self.active = False

    services.add_singleton(Resource)

    with SyncInjector(services) as injector:
        resource = injector.require(Resource)
        assert resource.active is True
    assert resource.active is True


def test_require_injector() -> None:
    class Service:
        def __init__(self, injector: SyncInjector) -> None:
            self.injector = injector

    services = ServiceCollection()
    services.add_singleton(Service)

    with SyncInjector(services) as injector:
        service = injector.require(Service)
        assert service.injector is injector


def test_require_injector_protocol() -> None:
    class Service:
        def __init__(self, injector: Injector) -> None:
            self.injector = injector

    services = ServiceCollection()
    services.add_singleton(Service)

    with SyncInjector(services) as injector:
        service = injector.require(Service)
        assert service.injector is injector


@pytest.mark.asyncio
async def test_require_generic_type() -> None:
    class Service[T]:
        def __init__(self, cls: type[T]) -> None:
            self.cls = cls

    services = ServiceCollection()
    services.add_singleton(Service)

    with SyncInjector(services) as injector:
        service = injector.require(Service[str])
        assert service.cls is str


@pytest.mark.asyncio
async def test_require_generic_twrap() -> None:
    class Service[T]:
        def __init__(self, tw: TWrap[T]) -> None:
            self.tw = tw

    services = ServiceCollection()
    services.add_singleton(Service)

    with SyncInjector(services) as injector:
        service = injector.require(Service[int])
        assert service.tw == wrap_type(int)


@pytest.mark.asyncio
async def test_require_two_generic_twrap() -> None:
    class Service[T, U]:
        def __init__(self, tw1: TWrap[T], tw2: TWrap[U]) -> None:
            self.tw1 = tw1
            self.tw2 = tw2

    services = ServiceCollection()
    services.add_singleton(Service)

    with SyncInjector(services) as injector:
        service = injector.require(Service[int, str])
        assert service.tw1 == wrap_type(int)
        assert service.tw2 == wrap_type(str)


@pytest.mark.asyncio
async def test_require_inherited_generic_twrap() -> None:
    class SuperBaseService[T]:
        @post_init
        def _setup1(self, tw: TWrap[T]) -> None:
            self.tw1 = tw

    class BaseService[T, U](SuperBaseService[U]):
        @post_init
        def _setup2(self, tw: TWrap[T]) -> None:
            self.tw2 = tw

    class Service[T, U, V](BaseService[U, V]):
        def __init__(self, tw: TWrap[T]) -> None:
            self.tw3 = tw

    services = ServiceCollection()
    services.add_singleton(Service)

    with SyncInjector(services) as injector:
        service = injector.require(Service[int, str, float])
        assert service.tw1 == wrap_type(float)
        assert service.tw2 == wrap_type(str)
        assert service.tw3 == wrap_type(int)

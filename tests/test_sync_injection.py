import asyncio
from collections.abc import AsyncGenerator, Generator
from types import TracebackType
from typing import Any

import pytest
from peritype import TWrap, wrap_type

from soupape import Injector, ServiceCollection, SyncInjector, post_init
from soupape.errors import (
    AsyncInSyncInjectorError,
    MissingTypeHintError,
    ScopedServiceNotAvailableError,
    ServiceNotFoundError,
)


def test_sync_inject() -> None:
    services = ServiceCollection()

    class TestService:
        def __init__(self) -> None:
            pass

        def greet(self) -> str:
            return "Hello from Sync!"

    services.add_singleton(TestService)
    with SyncInjector(services) as injector:
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
    with SyncInjector(services) as injector:
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
    with SyncInjector(services) as injector:

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
    with SyncInjector(services) as injector:

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

    with SyncInjector(services) as injector:
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

    with SyncInjector(services) as injector:
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

    with SyncInjector(services) as injector:
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

    with SyncInjector(services) as injector:
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

    with SyncInjector(services) as injector:
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

    with SyncInjector(services) as injector:
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


@pytest.mark.asyncio
async def test_fail_service_not_found() -> None:
    services = ServiceCollection()

    class TestService:
        def __init__(self) -> None:
            pass

        def greet(self) -> str:
            return "Hello, World!"

    with SyncInjector(services) as injector:
        with pytest.raises(ServiceNotFoundError):
            injector.require(TestService)


@pytest.mark.asyncio
async def test_fail_generic_service_not_found() -> None:
    class Service[T]: ...

    services = ServiceCollection()
    services.add_singleton(Service[int])

    with SyncInjector(services) as injector:
        with pytest.raises(ServiceNotFoundError):
            injector.require(Service[str])


@pytest.mark.asyncio
async def test_simple_injection_in_service() -> None:
    services = ServiceCollection()

    class BaseService:
        def __init__(self) -> None:
            pass

        def greet(self) -> str:
            return "Hello, World!"

    class TestService:
        def __init__(self, base_service: BaseService) -> None:
            self.base_service = base_service

        def greet(self) -> str:
            return self.base_service.greet()

    services.add_singleton(BaseService)
    services.add_singleton(TestService)

    with SyncInjector(services) as injector:
        service = injector.require(TestService)

    assert service.greet() == "Hello, World!"


@pytest.mark.asyncio
async def test_inject_with_catch_all_resolver() -> None:
    services = ServiceCollection()

    class Service[T]:
        def __init__(self) -> None:
            pass

    def service_resolver() -> Service[Any]:
        return Service()

    services.add_singleton(service_resolver)

    with SyncInjector(services) as injector:
        service = injector.require(Service[int])

    assert isinstance(service, Service)


@pytest.mark.asyncio
async def test_inject_resolver_with_params() -> None:
    services = ServiceCollection()

    class BaseService:
        def __init__(self) -> None:
            pass

        def greet(self) -> str:
            return "Hello, World!"

    class Service:
        def __init__(self, base_service: BaseService) -> None:
            self.base_service = base_service

        def greet(self) -> str:
            return self.base_service.greet()

    def service_resolver(base: BaseService) -> Service:
        return Service(base)

    services.add_singleton(BaseService)
    services.add_singleton(service_resolver)

    with SyncInjector(services) as injector:
        service = injector.require(Service)

    data = service.greet()
    assert data == "Hello, World!"


@pytest.mark.asyncio
async def test_sync_inject_service_twice() -> None:
    services = ServiceCollection()

    class SyncService:
        def __init__(self) -> None: ...

    services.add_singleton(SyncService)

    with SyncInjector(services) as injector:
        service1 = injector.require(SyncService)
        service2 = injector.require(SyncService)

    assert service1 is service2


@pytest.mark.asyncio
async def test_inject_scoped_twice() -> None:
    services = ServiceCollection()

    class ScopedService:
        def __init__(self) -> None:
            pass

    services.add_scoped(ScopedService)

    with SyncInjector(services) as root:
        injector = root.get_scoped_injector()
        instance1 = injector.require(ScopedService)
        instance2 = injector.require(ScopedService)

    assert instance1 is instance2


@pytest.mark.asyncio
async def test_fail_inject_scoped_in_root_injector() -> None:
    services = ServiceCollection()

    class ScopedService:
        def __init__(self) -> None:
            pass

    services.add_scoped(ScopedService)

    with SyncInjector(services) as injector:
        with pytest.raises(ScopedServiceNotAvailableError) as exc_info:
            injector.require(ScopedService)

    assert exc_info.value.code == "soupape.scoped_service.not_available"
    assert exc_info.value.message == (
        f"Scoped service for interface '{ScopedService.__qualname__}' is not available in the root scope."
    )

    assert exc_info.value.code == "soupape.scoped_service.not_available"
    assert exc_info.value.message == (
        f"Scoped service for interface '{ScopedService.__qualname__}' is not available in the root scope."
    )


@pytest.mark.asyncio
async def test_inject_transient() -> None:
    services = ServiceCollection()

    class TransientService:
        def __init__(self) -> None:
            pass

    services.add_transient(TransientService)

    with SyncInjector(services) as injector:
        instance1 = injector.require(TransientService)
        instance2 = injector.require(TransientService)

    assert instance1 is not instance2


@pytest.mark.asyncio
async def test_inject_scoped_twice_in_different_sessions() -> None:
    services = ServiceCollection()

    class ScopedService:
        def __init__(self) -> None:
            pass

    services.add_scoped(ScopedService)

    with SyncInjector(services) as injector:
        scoped1 = injector.get_scoped_injector()
        scoped2 = injector.get_scoped_injector()
        instance1 = scoped1.require(ScopedService)
        instance2 = scoped2.require(ScopedService)

    assert instance1 is not instance2


@pytest.mark.asyncio
async def test_inject_singleton_in_different_scopes() -> None:
    services = ServiceCollection()

    class SingletonService:
        def __init__(self) -> None:
            pass

    services.add_singleton(SingletonService)

    with SyncInjector(services) as injector:
        scoped1 = injector.get_scoped_injector()
        scoped2 = injector.get_scoped_injector()
        instance1 = scoped1.require(SingletonService)
        instance2 = scoped2.require(SingletonService)

    assert instance1 is instance2


@pytest.mark.asyncio
async def test_fail_inject_unregistered_service() -> None:
    services = ServiceCollection()

    class UnregisteredService:
        def __init__(self) -> None:
            pass

    with SyncInjector(services) as injector:
        with pytest.raises(ServiceNotFoundError):
            injector.require(UnregisteredService)


@pytest.mark.asyncio
async def test_fail_inject_unregistered_service_in_dependency() -> None:
    services = ServiceCollection()

    class UnregisteredService:
        def __init__(self) -> None:
            pass

    class DependentService:
        def __init__(self, unreg_service: UnregisteredService) -> None:
            self.unreg_service = unreg_service

    services.add_singleton(DependentService)

    with SyncInjector(services) as injector:
        with pytest.raises(ServiceNotFoundError):
            injector.require(DependentService)


@pytest.mark.asyncio
async def test_fail_missing_type_hint_in_dependency() -> None:
    services = ServiceCollection()

    class DependencyService:
        def __init__(self) -> None:
            pass

    class ServiceWithoutTypeHint:
        def __init__(self, dep_service) -> None:  # type: ignore
            self.dep_service = dep_service

    services.add_singleton(DependencyService)
    services.add_singleton(ServiceWithoutTypeHint)

    with SyncInjector(services) as injector:
        with pytest.raises(MissingTypeHintError) as exc_info:
            injector.require(ServiceWithoutTypeHint)

    assert exc_info.value.code == "soupape.type_hint.missing"
    assert exc_info.value.message == (
        f"Missing type hint for parameter 'dep_service' of '{ServiceWithoutTypeHint.__qualname__}.__init__'."
    )


@pytest.mark.asyncio
async def test_fail_missing_type_hint_in_function_call() -> None:
    services = ServiceCollection()

    class DependencyService:
        def __init__(self) -> None:
            pass

    services.add_singleton(DependencyService)

    with SyncInjector(services) as injector:

        def function_without_type_hint(dep_service):  # type: ignore
            return dep_service  # type: ignore

        with pytest.raises(MissingTypeHintError) as exc_info:
            injector.call(function_without_type_hint)  # type: ignore

    assert exc_info.value.code == "soupape.type_hint.missing"
    assert exc_info.value.message == (
        f"Missing type hint for parameter 'dep_service' of '{function_without_type_hint.__qualname__}'."
    )


@pytest.mark.asyncio
async def test_inject_with_inherited_post_init() -> None:
    services = ServiceCollection()

    class BaseService:
        def __init__(self) -> None:
            self.numbers: list[int] = []

        @post_init
        def initialize_base(self) -> None:
            self.numbers.append(1)

    class TestService(BaseService):
        def __init__(self) -> None:
            super().__init__()

        @post_init
        def initialize(self) -> None:
            self.numbers.append(2)

    services.add_singleton(TestService)

    with SyncInjector(services) as injector:
        service = injector.require(TestService)

    assert service.numbers == [1, 2]


@pytest.mark.asyncio
async def test_inject_post_init_with_args() -> None:
    class OtherService:
        def get_value(self) -> int:
            return 42

    class TestService:
        def __init__(self) -> None:
            self.initialized = 0

        @post_init
        def initialize(self, other_service: OtherService) -> None:
            self.initialized = other_service.get_value()

    services = ServiceCollection()
    services.add_singleton(OtherService)
    services.add_singleton(TestService)

    with SyncInjector(services) as injector:
        service = injector.require(TestService)

    assert service.initialized == 42


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

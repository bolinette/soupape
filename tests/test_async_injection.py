import asyncio
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator, Generator
from types import TracebackType
from typing import Any, override

import pytest
from peritype import TWrap, wrap_type

from soupape import AsyncInjector, Injector, ServiceCollection, post_init
from soupape._utils import add_type_to_type_globals
from soupape.errors import (
    CircularDependencyError,
    MissingTypeHintError,
    ScopedServiceNotAvailableError,
    ServiceNotFoundError,
)


@pytest.mark.asyncio
async def test_simple_injection() -> None:
    services = ServiceCollection()

    class TestService:
        def __init__(self) -> None:
            pass

        def greet(self) -> str:
            return "Hello, World!"

    services.add_singleton(TestService)

    async with AsyncInjector(services) as injector:
        service = await injector.require(TestService)

    assert service.greet() == "Hello, World!"


@pytest.mark.asyncio
async def test_inject_generic_type() -> None:
    class Service[T]: ...

    services = ServiceCollection()
    services.add_singleton(Service[str])

    async with AsyncInjector(services) as injector:
        service = await injector.require(Service[str])
        assert service is not None
        assert isinstance(service, Service)


@pytest.mark.asyncio
async def test_fail_service_not_found() -> None:
    services = ServiceCollection()

    class TestService:
        def __init__(self) -> None:
            pass

        def greet(self) -> str:
            return "Hello, World!"

    async with AsyncInjector(services) as injector:
        with pytest.raises(ServiceNotFoundError):
            await injector.require(TestService)


@pytest.mark.asyncio
async def test_fail_generic_service_not_found() -> None:
    class Service[T]: ...

    services = ServiceCollection()
    services.add_singleton(Service[int])

    async with AsyncInjector(services) as injector:
        with pytest.raises(ServiceNotFoundError):
            await injector.require(Service[str])


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

    async with AsyncInjector(services) as injector:
        service = await injector.require(TestService)

    assert service.greet() == "Hello, World!"


@pytest.mark.asyncio
async def test_inject_with_async_resolver() -> None:
    services = ServiceCollection()

    class AsyncService:
        def __init__(self) -> None:
            pass

        async def fetch_data(self) -> str:
            return "Async Data"

    async def async_service_resolver() -> AsyncService:
        return AsyncService()

    services.add_singleton(async_service_resolver)

    async with AsyncInjector(services) as injector:
        service = await injector.require(AsyncService)

    data = await service.fetch_data()
    assert data == "Async Data"


@pytest.mark.asyncio
async def test_inject_singleton_with_interface() -> None:
    services = ServiceCollection()

    class BaseService: ...

    class Subservice(BaseService): ...

    services.add_singleton(BaseService, Subservice)
    services.add_singleton(Subservice)

    async with AsyncInjector(services) as injector:
        base_instance = await injector.require(BaseService)
        sub_instance = await injector.require(Subservice)

    assert base_instance is sub_instance


@pytest.mark.asyncio
async def test_inject_with_catch_all_resolver() -> None:
    services = ServiceCollection()

    class AsyncService[T: int | str]:
        def __init__(self, id: int) -> None:
            self.id = id

        async def fetch_data(self) -> str:
            return f"Async Data {self.id}"

    count = {"id": 0}

    async def async_service_resolver[T: int | str](_cls: type[T]) -> AsyncService[T]:
        count["id"] += 1
        return AsyncService[_cls](count["id"])

    services.add_singleton(async_service_resolver)

    async with AsyncInjector(services) as injector:
        service1 = await injector.require(AsyncService[int])
        service2 = await injector.require(AsyncService[str])

    assert service1 is not service2

    data = await service1.fetch_data()
    assert data == "Async Data 1"

    data = await service2.fetch_data()
    assert data == "Async Data 2"


@pytest.mark.asyncio
async def test_inject_with_catch_all_interface() -> None:
    services = ServiceCollection()

    class Service[T]:
        async def fetch_data(self) -> str: ...

    class Service1[T](Service[T]):
        async def fetch_data(self) -> str:
            return "Service1 Data"

    class Service2[T](Service[T]):
        async def fetch_data(self) -> str:
            return "Service2 Data"

    services.add_singleton(Service[Any], Service1)
    services.add_singleton(Service[str], Service2)

    async with AsyncInjector(services) as injector:
        service1 = await injector.require(Service[int])
        service2 = await injector.require(Service[str])

    data1 = await service1.fetch_data()
    data2 = await service2.fetch_data()
    assert data1 == "Service1 Data"
    assert data2 == "Service2 Data"


@pytest.mark.asyncio
async def test_register_partial_catch_all_resolver() -> None:
    services = ServiceCollection()

    class Service[T, U]:
        async def fetch_data(self) -> str: ...

    class Service1[T, U](Service[T, U]):
        async def fetch_data(self) -> str:
            return "Service1 Data"

    class Service2[T, U](Service[T, U]):
        async def fetch_data(self) -> str:
            return "Service2 Data"

    class Service3[T, U](Service[T, U]):
        async def fetch_data(self) -> str:
            return "Service3 Data"

    services.add_singleton(Service[int, Any], Service1)
    services.add_singleton(Service[int, str], Service2)
    services.add_singleton(Service[str, Any], Service3)

    async with AsyncInjector(services) as injector:
        service1 = await injector.require(Service[int, float])
        service2 = await injector.require(Service[int, str])
        service3 = await injector.require(Service[str, float])

    data1 = await service1.fetch_data()
    data2 = await service2.fetch_data()
    data3 = await service3.fetch_data()
    assert data1 == "Service1 Data"
    assert data2 == "Service2 Data"
    assert data3 == "Service3 Data"


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

    async with AsyncInjector(services) as injector:
        service = await injector.require(Service)

    data = service.greet()
    assert data == "Hello, World!"


@pytest.mark.asyncio
async def test_inject_service_twice() -> None:
    services = ServiceCollection()

    class AsyncService:
        def __init__(self) -> None: ...

    services.add_singleton(AsyncService)

    async with AsyncInjector(services) as injector:
        service1 = await injector.require(AsyncService)
        service2 = await injector.require(AsyncService)

    assert service1 is service2


@pytest.mark.asyncio
async def test_inject_with_async_resolver_twice() -> None:
    services = ServiceCollection()

    class AsyncService:
        def __init__(self) -> None: ...

    async def async_service_resolver() -> AsyncService:
        return AsyncService()

    services.add_singleton(async_service_resolver)

    async with AsyncInjector(services) as injector:
        service1 = await injector.require(AsyncService)
        service2 = await injector.require(AsyncService)

    assert service1 is service2


@pytest.mark.asyncio
async def test_inject_with_async_resolver_custom_interface() -> None:
    services = ServiceCollection()

    class BaseService: ...

    class AsyncService(BaseService):
        def __init__(self) -> None: ...

    async def async_service_resolver() -> AsyncService:
        return AsyncService()

    services.add_singleton(async_service_resolver)
    services.add_singleton(BaseService, async_service_resolver)

    async with AsyncInjector(services) as injector:
        service1 = await injector.require(AsyncService)
        service2 = await injector.require(BaseService)

    assert service1 is service2
    assert isinstance(service1, AsyncService)
    assert isinstance(service2, AsyncService)


@pytest.mark.asyncio
async def test_inject_scoped_with_async_resolver() -> None:
    services = ServiceCollection()

    class AsyncService:
        def __init__(self) -> None:
            pass

        async def fetch_data(self) -> str:
            return "Async Data"

    async def async_service_resolver() -> AsyncService:
        return AsyncService()

    services.add_scoped(async_service_resolver)

    async with AsyncInjector(services) as injector:
        scoped = injector.get_scoped_injector()
        service = await scoped.require(AsyncService)

    data = await service.fetch_data()
    assert data == "Async Data"


@pytest.mark.asyncio
async def test_fail_inject_scoped_in_root_injector() -> None:
    services = ServiceCollection()

    class ScopedService:
        def __init__(self) -> None:
            pass

    services.add_scoped(ScopedService)

    async with AsyncInjector(services) as injector:
        with pytest.raises(ScopedServiceNotAvailableError) as exc_info:
            await injector.require(ScopedService)

    assert exc_info.value.code == "soupape.scoped_service.not_available"
    assert exc_info.value.message == (
        f"Scoped service for interface '{ScopedService.__qualname__}' is not available in the root scope."
    )

    assert exc_info.value.code == "soupape.scoped_service.not_available"
    assert exc_info.value.message == (
        f"Scoped service for interface '{ScopedService.__qualname__}' is not available in the root scope."
    )


@pytest.mark.asyncio
async def test_inject_scoped_with_async_resolver_twice() -> None:
    services = ServiceCollection()

    class AsyncService: ...

    async def async_service_resolver() -> AsyncService:
        return AsyncService()

    services.add_scoped(async_service_resolver)

    async with AsyncInjector(services) as injector:
        scoped = injector.get_scoped_injector()
        service1 = await scoped.require(AsyncService)
        service2 = await scoped.require(AsyncService)

    assert service1 is service2


@pytest.mark.asyncio
async def test_inject_transient_with_async_resolver() -> None:
    services = ServiceCollection()

    class AsyncService:
        def __init__(self) -> None:
            pass

        async def fetch_data(self) -> str:
            return "Async Data"

    async def async_service_resolver() -> AsyncService:
        return AsyncService()

    services.add_transient(async_service_resolver)

    async with AsyncInjector(services) as injector:
        scoped = injector.get_scoped_injector()
        service = await scoped.require(AsyncService)

    data = await service.fetch_data()
    assert data == "Async Data"


@pytest.mark.asyncio
async def test_inject_transient_with_async_resolver_twice() -> None:
    services = ServiceCollection()

    class AsyncService: ...

    async def async_service_resolver() -> AsyncService:
        return AsyncService()

    services.add_transient(async_service_resolver)

    async with AsyncInjector(services) as injector:
        scoped = injector.get_scoped_injector()
        service1 = await scoped.require(AsyncService)
        service2 = await scoped.require(AsyncService)

    assert service1 is not service2


@pytest.mark.asyncio
async def test_call_async_function_with_injected_dependencies() -> None:
    services = ServiceCollection()

    class DependencyService:
        def __init__(self) -> None:
            pass

        def get_value(self) -> str:
            return "Injected Value"

    services.add_singleton(DependencyService)

    async with AsyncInjector(services) as injector:

        async def test_function(dep_service: DependencyService) -> str:
            return dep_service.get_value()

        result = await injector.call(test_function)
    assert result == "Injected Value"


@pytest.mark.asyncio
async def test_call_sync_function_with_injected_dependencies() -> None:
    services = ServiceCollection()

    class DependencyService:
        def __init__(self) -> None:
            pass

        def get_value(self) -> str:
            return "Injected Value"

    services.add_singleton(DependencyService)

    async with AsyncInjector(services) as injector:

        def test_function(dep_service: DependencyService) -> str:
            return dep_service.get_value()

        result = await injector.call(test_function)
    assert result == "Injected Value"


@pytest.mark.asyncio
async def test_inject_singleton_twice() -> None:
    services = ServiceCollection()

    class SingletonService:
        def __init__(self) -> None:
            pass

    services.add_singleton(SingletonService)

    async with AsyncInjector(services) as injector:
        instance1 = await injector.require(SingletonService)
        instance2 = await injector.require(SingletonService)

    assert instance1 is instance2


@pytest.mark.asyncio
async def test_inject_scoped_twice() -> None:
    services = ServiceCollection()

    class ScopedService:
        def __init__(self) -> None:
            pass

    services.add_scoped(ScopedService)

    async with AsyncInjector(services) as root:
        injector = root.get_scoped_injector()
        instance1 = await injector.require(ScopedService)
        instance2 = await injector.require(ScopedService)

    assert instance1 is instance2


@pytest.mark.asyncio
async def test_inject_transient() -> None:
    services = ServiceCollection()

    class TransientService:
        def __init__(self) -> None:
            pass

    services.add_transient(TransientService)

    async with AsyncInjector(services) as injector:
        instance1 = await injector.require(TransientService)
        instance2 = await injector.require(TransientService)

    assert instance1 is not instance2


@pytest.mark.asyncio
async def test_inject_scoped_twice_in_different_sessions() -> None:
    services = ServiceCollection()

    class ScopedService:
        def __init__(self) -> None:
            pass

    services.add_scoped(ScopedService)

    async with AsyncInjector(services) as injector:
        scoped1 = injector.get_scoped_injector()
        scoped2 = injector.get_scoped_injector()
        instance1 = await scoped1.require(ScopedService)
        instance2 = await scoped2.require(ScopedService)

    assert instance1 is not instance2


@pytest.mark.asyncio
async def test_inject_singleton_in_different_scopes() -> None:
    services = ServiceCollection()

    class SingletonService:
        def __init__(self) -> None:
            pass

    services.add_singleton(SingletonService)

    async with AsyncInjector(services) as injector:
        scoped1 = injector.get_scoped_injector()
        scoped2 = injector.get_scoped_injector()
        instance1 = await scoped1.require(SingletonService)
        instance2 = await scoped2.require(SingletonService)

    assert instance1 is instance2


@pytest.mark.asyncio
async def test_fail_inject_unregistered_service() -> None:
    services = ServiceCollection()

    class UnregisteredService:
        def __init__(self) -> None:
            pass

    async with AsyncInjector(services) as injector:
        with pytest.raises(ServiceNotFoundError):
            await injector.require(UnregisteredService)


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

    async with AsyncInjector(services) as injector:
        with pytest.raises(ServiceNotFoundError):
            await injector.require(DependentService)


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

    async with AsyncInjector(services) as injector:
        with pytest.raises(MissingTypeHintError) as exc_info:
            await injector.require(ServiceWithoutTypeHint)

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

    async with AsyncInjector(services) as injector:

        def function_without_type_hint(dep_service):  # type: ignore
            return dep_service  # type: ignore

        with pytest.raises(MissingTypeHintError) as exc_info:
            await injector.call(function_without_type_hint)  # type: ignore

    assert exc_info.value.code == "soupape.type_hint.missing"
    assert exc_info.value.message == (
        f"Missing type hint for parameter 'dep_service' of '{function_without_type_hint.__qualname__}'."
    )


@pytest.mark.asyncio
async def test_inject_service_with_positional_only_parameter() -> None:
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

    async with AsyncInjector(services) as injector:
        service = await injector.require(ServiceWithPositionalOnly)

    assert service.greet() == "Hello from Positional!"


@pytest.mark.asyncio
async def test_inject_service_with_keyword_only_parameter() -> None:
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

    async with AsyncInjector(services) as injector:
        service = await injector.require(ServiceWithKeywordOnly)

    assert service.greet() == "Hello from Keyword!"


@pytest.mark.asyncio
async def test_inject_with_post_init() -> None:
    services = ServiceCollection()

    class TestService:
        def __init__(self) -> None:
            self.initialized = False

        @post_init
        def initialize(self) -> None:
            self.initialized = True

    services.add_singleton(TestService)

    async with AsyncInjector(services) as injector:
        service = await injector.require(TestService)

    assert service.initialized is True


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

    async with AsyncInjector(services) as injector:
        service = await injector.require(TestService)

    assert service.numbers == [1, 2]


@pytest.mark.asyncio
async def test_inject_with_async_post_init() -> None:
    services = ServiceCollection()

    class TestService:
        def __init__(self) -> None:
            self.initialized = False

        @post_init
        async def initialize(self) -> None:
            await asyncio.sleep(0)
            self.initialized = True

    services.add_singleton(TestService)

    async with AsyncInjector(services) as injector:
        service = await injector.require(TestService)

    assert service.initialized is True


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

    async with AsyncInjector(services) as injector:
        service = await injector.require(TestService)

    assert service.initialized == 42


@pytest.mark.asyncio
async def test_inject_async_yield_resolver() -> None:
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

    async with AsyncInjector(services) as injector:
        resource = await injector.require(Resource)

    assert resource.active is True


@pytest.mark.asyncio
async def test_inject_yield_resolver() -> None:
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

    async with AsyncInjector(services) as injector:
        resource = await injector.require(Resource)

    assert resource.active is True


@pytest.mark.asyncio
async def test_injection_context_manager_sync_resolver() -> None:
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

    async with AsyncInjector(services) as injector:
        resource = await injector.require(Resource)
        assert resource.active is True
    assert resource.active is False


@pytest.mark.asyncio
async def test_injection_context_manager_async_resolver() -> None:
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

    async with AsyncInjector(services) as injector:
        resource = await injector.require(Resource)
        assert resource.active is True
    assert resource.active is False


@pytest.mark.asyncio
async def test_injection_context_manager_service() -> None:
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

    async with AsyncInjector(services) as injector:
        resource = await injector.require(Resource)
        assert resource.active is True
    assert resource.active is False


@pytest.mark.asyncio
async def test_injection_async_context_manager_service() -> None:
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

    async with AsyncInjector(services) as injector:
        resource = await injector.require(Resource)
        assert resource.active is True
    assert resource.active is False


@pytest.mark.asyncio
async def test_require_injector() -> None:
    class Service:
        def __init__(self, injector: AsyncInjector) -> None:
            self.injector = injector

    services = ServiceCollection()
    services.add_singleton(Service)

    async with AsyncInjector(services) as injector:
        service = await injector.require(Service)
        assert service.injector is injector


@pytest.mark.asyncio
async def test_require_injector_protocol() -> None:
    class Service:
        def __init__(self, injector: Injector) -> None:
            self.injector = injector

    services = ServiceCollection()
    services.add_singleton(Service)

    async with AsyncInjector(services) as injector:
        service = await injector.require(Service)
        assert service.injector is injector


@pytest.mark.asyncio
async def test_require_generic_type() -> None:
    class Service[T]:
        def __init__(self, cls: type[T]) -> None:
            self.cls = cls

    services = ServiceCollection()
    services.add_singleton(Service)

    async with AsyncInjector(services) as injector:
        service = await injector.require(Service[str])
        assert service.cls is str


@pytest.mark.asyncio
async def test_require_generic_twrap() -> None:
    class Service[T]:
        def __init__(self, tw: TWrap[T]) -> None:
            self.tw = tw

    services = ServiceCollection()
    services.add_singleton(Service)

    async with AsyncInjector(services) as injector:
        service = await injector.require(Service[int])
        assert service.tw == wrap_type(int)


@pytest.mark.asyncio
async def test_require_two_generic_twrap() -> None:
    class Service[T, U]:
        def __init__(self, tw1: TWrap[T], tw2: TWrap[U]) -> None:
            self.tw1 = tw1
            self.tw2 = tw2

    services = ServiceCollection()
    services.add_singleton(Service)

    async with AsyncInjector(services) as injector:
        service = await injector.require(Service[int, str])
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

    async with AsyncInjector(services) as injector:
        service = await injector.require(Service[int, str, float])
        assert service.tw1 == wrap_type(float)
        assert service.tw2 == wrap_type(str)
        assert service.tw3 == wrap_type(int)


@pytest.mark.asyncio
async def test_require_generic_type_in_resolver() -> None:
    class Service[T]:
        def __init__(self, cls: type[T]) -> None:
            self.cls = cls

    def service_resolver[T](cls: type[T]) -> Service[T]:
        return Service(cls)

    services = ServiceCollection()
    services.add_singleton(service_resolver)

    async with AsyncInjector(services) as injector:
        service = await injector.require(Service[float])
        assert service.cls is float


@pytest.mark.asyncio
async def test_require_two_generic_type_in_resolver() -> None:
    class Service[T, U]:
        def __init__(self, cls1: type[T], cls2: type[U]) -> None:
            self.cls1 = cls1
            self.cls2 = cls2

    def service_resolver[T, U](cls1: type[T], cls2: type[U]) -> Service[U, T]:
        return Service(cls2, cls1)

    services = ServiceCollection()
    services.add_singleton(service_resolver)

    async with AsyncInjector(services) as injector:
        service = await injector.require(Service[float, int])
        assert service.cls1 is float
        assert service.cls2 is int


@pytest.mark.asyncio
async def test_fail_circular_dependency() -> None:
    services = ServiceCollection()

    class ServiceA:
        def __init__(self, service_b: "ServiceB") -> None:
            self.service_b = service_b

    class ServiceB:
        def __init__(self, service_a: ServiceA) -> None:
            self.service_a = service_a

    add_type_to_type_globals(ServiceA, ServiceB)

    services.add_singleton(ServiceA)
    services.add_singleton(ServiceB)

    async with AsyncInjector(services) as injector:
        with pytest.raises(CircularDependencyError) as exc_info:
            await injector.require(ServiceA)

    trace = exc_info.value.trace
    assert len(trace) == 3
    assert trace[0].__qualname__ == ServiceA.__init__.__qualname__
    assert trace[1].__qualname__ == ServiceB.__init__.__qualname__
    assert trace[2].__qualname__ == ServiceA.__init__.__qualname__


@pytest.mark.asyncio
async def test_fail_circular_dependency_3_services() -> None:
    services = ServiceCollection()

    class ServiceA:
        def __init__(self, service_b: "ServiceB") -> None:
            self.service_b = service_b

    class ServiceB:
        def __init__(self, service_c: "ServiceC") -> None:
            self.service_c = service_c

    class ServiceC:
        def __init__(self, service_a: ServiceA) -> None:
            self.service_a = service_a

    add_type_to_type_globals(ServiceA, ServiceB)
    add_type_to_type_globals(ServiceB, ServiceC)

    services.add_singleton(ServiceA)
    services.add_singleton(ServiceB)
    services.add_singleton(ServiceC)

    async with AsyncInjector(services) as injector:
        with pytest.raises(CircularDependencyError) as exc_info:
            await injector.require(ServiceA)

    trace = exc_info.value.trace
    assert len(trace) == 4
    assert trace[0].__qualname__ == ServiceA.__init__.__qualname__
    assert trace[1].__qualname__ == ServiceB.__init__.__qualname__
    assert trace[2].__qualname__ == ServiceC.__init__.__qualname__
    assert trace[3].__qualname__ == ServiceA.__init__.__qualname__


@pytest.mark.asyncio
async def test_fail_circular_dependency_in_post_init() -> None:
    services = ServiceCollection()

    class ServiceA:
        def __init__(self) -> None:
            self.resource: str | None = None

        @post_init
        async def setup(self, service_b: "ServiceB") -> None:
            self.resource = await service_b.fetch_data()

    class ServiceB:
        def __init__(self, service_a: ServiceA) -> None:
            self.service_a = service_a

        async def fetch_data(self) -> str:
            return "Data"

    add_type_to_type_globals(ServiceA, ServiceB)

    services.add_singleton(ServiceA)
    services.add_singleton(ServiceB)

    async with AsyncInjector(services) as injector:
        with pytest.raises(CircularDependencyError) as exc_info:
            await injector.require(ServiceA)

    trace = exc_info.value.trace
    assert len(trace) == 4
    assert trace[0].__qualname__ == ServiceA.__init__.__qualname__
    assert trace[1].__qualname__ == ServiceA.setup.__qualname__
    assert trace[2].__qualname__ == ServiceB.__init__.__qualname__
    assert trace[3].__qualname__ == ServiceA.__init__.__qualname__


@pytest.mark.asyncio
async def test_inject_list_of_services() -> None:
    services = ServiceCollection()

    class ServiceInterface(ABC):
        @abstractmethod
        def get_value(self) -> str: ...

    class ServiceA(ServiceInterface):
        @override
        def get_value(self) -> str:
            return "ServiceA"

    class ServiceB(ServiceInterface):
        @override
        def get_value(self) -> str:
            return "ServiceB"

    services.add_singleton(ServiceA)
    services.add_singleton(ServiceB)

    async with AsyncInjector(services) as injector:
        service_list = await injector.require(list[ServiceInterface])

    values = {service.get_value() for service in service_list}
    assert values == {"ServiceA", "ServiceB"}


@pytest.mark.asyncio
async def test_inject_list_of_generic_services() -> None:
    services = ServiceCollection()

    class ServiceInterface[T](ABC):
        @abstractmethod
        def get_value(self) -> T: ...

    class ServiceA(ServiceInterface[int]):
        @override
        def get_value(self) -> int:
            return 42

    class ServiceB(ServiceInterface[str]):
        @override
        def get_value(self) -> str:
            return "Hello"

    services.add_singleton(ServiceA)
    services.add_singleton(ServiceB)

    async with AsyncInjector(services) as injector:
        service_list = await injector.require(list[ServiceInterface[Any]])

    values = {service.get_value() for service in service_list}
    assert values == {42, "Hello"}


@pytest.mark.asyncio
async def test_inject_dict_of_services() -> None:
    services = ServiceCollection()

    class ServiceInterface(ABC):
        @abstractmethod
        def get_value(self) -> str: ...

    class ServiceA(ServiceInterface):
        @override
        def get_value(self) -> str:
            return "ServiceA"

    class ServiceB(ServiceInterface):
        @override
        def get_value(self) -> str:
            return "ServiceB"

    services.add_singleton(ServiceA)
    services.add_singleton(ServiceB)

    async with AsyncInjector(services) as injector:
        service_dict = await injector.require(dict[str, ServiceInterface])

    values = {service.get_value() for service in service_dict.values()}
    assert values == {"ServiceA", "ServiceB"}

    keys = set(service_dict.keys())
    assert keys == {"test_inject_dict_of_services.<locals>.ServiceA", "test_inject_dict_of_services.<locals>.ServiceB"}


@pytest.mark.asyncio
async def test_register_as_any_different_injected() -> None:
    class Service[T]:
        def __init__(self, cls: type[T]) -> None:
            self.cls = cls

    services = ServiceCollection()
    services.add_singleton(Service[Any])

    async with AsyncInjector(services) as injector:
        service_int = await injector.require(Service[int])
        service_str = await injector.require(Service[str])

    assert service_int is not service_str
    assert service_int.cls is int
    assert service_str.cls is str


@pytest.mark.asyncio
async def test_register_complex_generic_structure() -> None:
    class BaseService[T]:
        async def fetch_data(self) -> str: ...

    class Service1[T](BaseService[T]):
        async def fetch_data(self) -> str:
            return "Service1 Data"

    class Service2[T](BaseService[T]):
        async def fetch_data(self) -> str:
            return "Service2 Data"

    class Controller[T]:
        def __init__(self, service: BaseService[T]) -> None:
            self.service = service

        async def get_data(self) -> str:
            return await self.service.fetch_data()

    services = ServiceCollection()
    services.add_singleton(BaseService[Any], Service1)
    services.add_singleton(BaseService[str], Service2)
    services.add_singleton(Controller[int])
    services.add_singleton(Controller[str])

    async with AsyncInjector(services) as injector:
        controller_int = await injector.require(Controller[int])
        assert await controller_int.get_data() == "Service1 Data"

        controller_str = await injector.require(Controller[str])
        assert await controller_str.get_data() == "Service2 Data"

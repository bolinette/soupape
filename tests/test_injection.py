import pytest

from soupape import Injector, ServiceCollection
from soupape.errors import MissingTypeHintError, ServiceNotFoundError
from soupape.injector import SyncInjector


@pytest.mark.asyncio
async def test_simple_injection() -> None:
    services = ServiceCollection()

    class TestService:
        def __init__(self) -> None:
            pass

        def greet(self) -> str:
            return "Hello, World!"

    services.add_singleton(TestService)

    injector = Injector(services)
    my_service = await injector.require(TestService)

    assert my_service.greet() == "Hello, World!"


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

    injector = Injector(services)
    my_service = await injector.require(TestService)

    assert my_service.greet() == "Hello, World!"


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

    injector = Injector(services)
    my_service = await injector.require(AsyncService)

    data = await my_service.fetch_data()
    assert data == "Async Data"


@pytest.mark.asyncio
async def test_call_async_function_with_injected_dependencies() -> None:
    services = ServiceCollection()

    class DependencyService:
        def __init__(self) -> None:
            pass

        def get_value(self) -> str:
            return "Injected Value"

    services.add_singleton(DependencyService)

    injector = Injector(services)

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

    injector = Injector(services)

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

    injector = Injector(services)
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
    injector = Injector(services).get_scoped_injector()
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
    injector = Injector(services)
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
    injector = Injector(services)
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
    injector = Injector(services)
    scoped1 = injector.get_scoped_injector()
    scoped2 = injector.get_scoped_injector()
    instance1 = await scoped1.require(SingletonService)
    instance2 = await scoped2.require(SingletonService)

    assert instance1 is instance2


def test_sync_inject() -> None:
    services = ServiceCollection()

    class TestService:
        def __init__(self) -> None:
            pass

        def greet(self) -> str:
            return "Hello from Sync!"

    services.add_singleton(TestService)
    injector = SyncInjector(services)

    my_service = injector.require(TestService)
    assert my_service.greet() == "Hello from Sync!"


def test_fail_async_call_in_sync_injector() -> None:
    services = ServiceCollection()

    class AsyncService:
        def __init__(self) -> None: ...

        async def fetch_data(self) -> str: ...

    async def async_service_resolver() -> AsyncService: ...

    services.add_singleton(async_service_resolver)
    injector = SyncInjector(services)

    with pytest.raises(RuntimeError):
        injector.require(AsyncService)


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

    with pytest.raises(RuntimeError):
        await injector.call(test_function)


@pytest.mark.asyncio
async def test_fail_inject_unregistered_service() -> None:
    services = ServiceCollection()

    class UnregisteredService:
        def __init__(self) -> None:
            pass

    injector = Injector(services)

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
    injector = Injector(services)

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
    injector = Injector(services)

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
    injector = Injector(services)

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

    injector = Injector(services)
    my_service = await injector.require(ServiceWithPositionalOnly)

    assert my_service.greet() == "Hello from Positional!"


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

    injector = Injector(services)
    my_service = await injector.require(ServiceWithKeywordOnly)

    assert my_service.greet() == "Hello from Keyword!"

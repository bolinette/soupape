"""Behaviour only `AsyncInjector` can exhibit.

Injection paths shared with `SyncInjector` live in `test_base_injection.py`; this file
covers the ones that need a running event loop: coroutine and async-generator resolvers,
async `post_init` hooks, async context-manager services and calling coroutine functions.
"""

import asyncio
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator, AsyncIterator
from types import TracebackType
from typing import Annotated, override

import pytest
from peritype import wrap_type

from soupape import AsyncInjector, ServiceCollection, post_init
from soupape._utils import add_type_to_type_globals
from soupape.errors import CircularDependencyError
from soupape.resolvers import make_annotated_resolver

pytestmark = pytest.mark.asyncio


class TestAsyncResolvers:
    async def test_inject_with_async_resolver(self) -> None:
        """A coroutine resolver is awaited to build the service."""
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

    async def test_inject_with_async_resolver_twice(self) -> None:
        """A coroutine resolver runs once for a singleton."""
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

    async def test_inject_with_async_resolver_custom_interface(self) -> None:
        """A coroutine resolver under two interfaces shares one instance between them."""
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

    async def test_inject_with_async_catch_all_resolver(self) -> None:
        """A generic coroutine resolver is awaited once per specialization."""
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

    async def test_inject_scoped_with_async_resolver(self) -> None:
        """A scoped registration backed by a coroutine resolver resolves."""
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

    async def test_inject_scoped_with_async_resolver_twice(self) -> None:
        """A coroutine resolver runs once per scope for a scoped service."""
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

    async def test_inject_transient_with_async_resolver(self) -> None:
        """A transient registration backed by a coroutine resolver resolves."""
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

    async def test_inject_transient_with_async_resolver_twice(self) -> None:
        """A coroutine resolver runs on every require for a transient service."""
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


class TestAsyncGeneratorResolvers:
    async def test_async_generator_resolver_with_async_iterator_hint(self) -> None:
        """`AsyncIterator[T]` is accepted as the return hint of an async generator resolver."""
        services = ServiceCollection()
        events: list[str] = []

        class Service:
            pass

        async def service_resolver() -> AsyncIterator[Service]:
            yield Service()
            events.append("closed")

        services.add_scoped(service_resolver)

        async with AsyncInjector(services).get_scoped_injector() as injector:
            service = await injector.require(Service)
            assert isinstance(service, Service)
        assert events == ["closed"]

    async def test_inject_async_yield_resolver(self) -> None:
        """An async generator resolver yields the service instance."""
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

    async def test_injection_context_manager_async_resolver(self) -> None:
        """Code after the yield is awaited when the injector scope closes."""
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


class TestAsyncContextManagerServices:
    async def test_injection_async_context_manager_service(self) -> None:
        """An async context-manager service is entered on build and exited with the scope."""
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

    async def test_singleton_async_context_manager_created_in_scope_is_exited_with_root(self) -> None:
        """An async context-manager singleton built inside a scope is exited with the root injector."""
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

        async with AsyncInjector(services) as root:
            async with root.get_scoped_injector() as scoped:
                resource = await scoped.require(Resource)
                assert resource.active is True
            assert resource.active is True
            assert await root.require(Resource) is resource
        assert resource.active is False

    async def test_mixed_context_manager_services_are_exited_in_reverse_build_order(self) -> None:
        """Sync and async context-manager services share one teardown order, dependents first."""
        services = ServiceCollection()
        events: list[str] = []

        class Database:
            async def __aenter__(self) -> "Database":
                return self

            async def __aexit__(
                self,
                exc_type: type[BaseException],
                exc_value: BaseException | None,
                traceback: TracebackType | None,
            ) -> None:
                events.append("database")

        class Repository:
            def __init__(self, database: Database) -> None:
                self.database = database

            def __enter__(self) -> "Repository":
                return self

            def __exit__(
                self,
                exc_type: type[BaseException],
                exc_value: BaseException | None,
                traceback: TracebackType | None,
            ) -> None:
                events.append("repository")

        class Service:
            def __init__(self, repository: Repository) -> None:
                self.repository = repository

            async def __aenter__(self) -> "Service":
                return self

            async def __aexit__(
                self,
                exc_type: type[BaseException],
                exc_value: BaseException | None,
                traceback: TracebackType | None,
            ) -> None:
                events.append("service")

        services.add_scoped(Database)
        services.add_scoped(Repository)
        services.add_scoped(Service)

        async with AsyncInjector(services).get_scoped_injector() as injector:
            await injector.require(Service)
            assert events == []
        assert events == ["service", "repository", "database"]

    async def test_async_context_manager_services_are_all_exited_when_one_exit_fails(self) -> None:
        """A failing `__aexit__` does not stop the other services from being exited, and still propagates."""
        services = ServiceCollection()
        events: list[str] = []

        class Database:
            async def __aenter__(self) -> "Database":
                return self

            async def __aexit__(
                self,
                exc_type: type[BaseException],
                exc_value: BaseException | None,
                traceback: TracebackType | None,
            ) -> None:
                events.append("database")

        class Repository:
            def __init__(self, database: Database) -> None:
                self.database = database

            async def __aenter__(self) -> "Repository":
                return self

            async def __aexit__(
                self,
                exc_type: type[BaseException],
                exc_value: BaseException | None,
                traceback: TracebackType | None,
            ) -> None:
                raise RuntimeError("repository failed")

        services.add_scoped(Database)
        services.add_scoped(Repository)

        with pytest.raises(RuntimeError, match="repository failed"):
            async with AsyncInjector(services).get_scoped_injector() as injector:
                await injector.require(Repository)
        assert events == ["database"]

    async def test_exception_in_scope_is_forwarded_to_async_context_manager_services(self) -> None:
        """An exception leaving the scope is passed to the services' `__aexit__`, then propagates."""
        services = ServiceCollection()
        received: list[type[BaseException] | None] = []

        class Resource:
            async def __aenter__(self) -> "Resource":
                return self

            async def __aexit__(
                self,
                exc_type: type[BaseException] | None,
                exc_value: BaseException | None,
                traceback: TracebackType | None,
            ) -> None:
                received.append(exc_type)

        services.add_scoped(Resource)

        with pytest.raises(ValueError, match="boom"):
            async with AsyncInjector(services).get_scoped_injector() as injector:
                await injector.require(Resource)
                raise ValueError("boom")
        assert received == [ValueError]


class TestAsyncPostInit:
    async def test_inject_with_async_post_init(self) -> None:
        """A coroutine `post_init` hook is awaited after the instance is built."""
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

    async def test_fail_circular_dependency_in_async_post_init(self) -> None:
        """A cycle opened by a coroutine `post_init` hook lists the hook in the trace."""
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

        assert exc_info.value.trace == [wrap_type(ServiceA), ServiceA.setup, wrap_type(ServiceB), wrap_type(ServiceA)]


class TestAsyncFunctionCalls:
    async def test_call_async_function_with_injected_dependencies(self) -> None:
        """`call` awaits a coroutine function and returns its result."""
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


class TestAsyncServiceCollectionInjection:
    async def test_inject_list_of_services_with_async_resolvers(self) -> None:
        """`list[Interface]` collects implementations built by coroutine resolvers."""
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

        async def service_a_resolver() -> ServiceA:
            return ServiceA()

        async def service_b_resolver() -> ServiceB:
            return ServiceB()

        services.add_singleton(service_a_resolver)
        services.add_singleton(service_b_resolver)

        async with AsyncInjector(services) as injector:
            service_list = await injector.require(list[ServiceInterface])

        values = sorted(service.get_value() for service in service_list)
        assert values == ["ServiceA", "ServiceB"]

    async def test_inject_list_of_services_with_async_resolvers_has_no_duplicates(self) -> None:
        """Every matching implementation appears exactly once in `list[Interface]`."""
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

        class ServiceC(ServiceInterface):
            @override
            def get_value(self) -> str:
                return "ServiceC"

        async def service_a_resolver() -> ServiceA:
            return ServiceA()

        async def service_b_resolver() -> ServiceB:
            return ServiceB()

        def service_c_resolver() -> ServiceC:
            return ServiceC()

        services.add_singleton(service_a_resolver)
        services.add_singleton(service_b_resolver)
        services.add_singleton(service_c_resolver)

        async with AsyncInjector(services) as injector:
            service_list = await injector.require(list[ServiceInterface])

        assert len(service_list) == 3
        assert sorted(service.get_value() for service in service_list) == ["ServiceA", "ServiceB", "ServiceC"]

    async def test_inject_dict_of_services_with_async_resolvers(self) -> None:
        """`dict[str, Interface]` collects implementations built by coroutine resolvers."""
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

        async def service_a_resolver() -> ServiceA:
            return ServiceA()

        async def service_b_resolver() -> ServiceB:
            return ServiceB()

        services.add_singleton(service_a_resolver)
        services.add_singleton(service_b_resolver)

        async with AsyncInjector(services) as injector:
            service_dict = await injector.require(dict[str, ServiceInterface])

        assert len(service_dict) == 2
        assert sorted(service.get_value() for service in service_dict.values()) == ["ServiceA", "ServiceB"]
        assert sorted(service_dict.keys()) == sorted([ServiceA.__qualname__, ServiceB.__qualname__])


class TestConcurrentResolution:
    async def test_concurrent_require_of_singleton_builds_it_once(self) -> None:
        """Two coroutines requiring a singleton whose build awaits get the same, single instance."""
        services = ServiceCollection()
        built: list[str] = []

        class Pool:
            async def __aenter__(self) -> "Pool":
                built.append("pool")
                await asyncio.sleep(0)
                return self

            async def __aexit__(
                self,
                exc_type: type[BaseException] | None,
                exc_value: BaseException | None,
                traceback: TracebackType | None,
            ) -> None: ...

        services.add_singleton(Pool)

        async with AsyncInjector(services) as injector:
            first, second = await asyncio.gather(injector.require(Pool), injector.require(Pool))

        assert first is second
        assert built == ["pool"]

    async def test_concurrent_require_of_singleton_from_two_scopes_builds_it_once(self) -> None:
        """The claim lives on the root pool, so two scopes racing on a singleton share it."""
        services = ServiceCollection()
        built: list[str] = []

        class Pool:
            async def __aenter__(self) -> "Pool":
                built.append("pool")
                await asyncio.sleep(0)
                return self

            async def __aexit__(
                self,
                exc_type: type[BaseException] | None,
                exc_value: BaseException | None,
                traceback: TracebackType | None,
            ) -> None: ...

        services.add_singleton(Pool)

        async with AsyncInjector(services) as root:
            async with root.get_scoped_injector() as scoped1, root.get_scoped_injector() as scoped2:
                first, second = await asyncio.gather(scoped1.require(Pool), scoped2.require(Pool))

        assert first is second
        assert built == ["pool"]

    async def test_concurrent_require_of_scoped_service_builds_it_once_per_scope(self) -> None:
        """Two coroutines in one scope share the scoped service; another scope builds its own."""
        services = ServiceCollection()
        built: list[str] = []

        class Session:
            async def __aenter__(self) -> "Session":
                built.append("session")
                await asyncio.sleep(0)
                return self

            async def __aexit__(
                self,
                exc_type: type[BaseException] | None,
                exc_value: BaseException | None,
                traceback: TracebackType | None,
            ) -> None: ...

        services.add_scoped(Session)

        async with AsyncInjector(services) as root:
            async with root.get_scoped_injector() as scoped1, root.get_scoped_injector() as scoped2:
                first, second, other = await asyncio.gather(
                    scoped1.require(Session),
                    scoped1.require(Session),
                    scoped2.require(Session),
                )

        assert first is second
        assert other is not first
        assert built == ["session", "session"]

    async def test_concurrent_require_of_transient_builds_it_every_time(self) -> None:
        """Transients are not stored, so concurrent requires build distinct instances."""
        services = ServiceCollection()

        class Worker:
            async def __aenter__(self) -> "Worker":
                await asyncio.sleep(0)
                return self

            async def __aexit__(
                self,
                exc_type: type[BaseException] | None,
                exc_value: BaseException | None,
                traceback: TracebackType | None,
            ) -> None: ...

        services.add_transient(Worker)

        async with AsyncInjector(services) as injector:
            first, second = await asyncio.gather(injector.require(Worker), injector.require(Worker))

        assert first is not second

    async def test_concurrent_dependents_share_the_singleton_dependency(self) -> None:
        """Two services required concurrently that depend on the same slow singleton get one instance of it."""
        services = ServiceCollection()
        built: list[str] = []

        class Pool:
            async def __aenter__(self) -> "Pool":
                built.append("pool")
                await asyncio.sleep(0)
                return self

            async def __aexit__(
                self,
                exc_type: type[BaseException] | None,
                exc_value: BaseException | None,
                traceback: TracebackType | None,
            ) -> None: ...

        class Users:
            def __init__(self, pool: Pool) -> None:
                self.pool = pool

        class Orders:
            def __init__(self, pool: Pool) -> None:
                self.pool = pool

        services.add_singleton(Pool)
        services.add_transient(Users)
        services.add_transient(Orders)

        async with AsyncInjector(services) as injector:
            users, orders = await asyncio.gather(injector.require(Users), injector.require(Orders))

        assert users.pool is orders.pool
        assert built == ["pool"]

    async def test_failed_build_propagates_to_waiters_and_releases_the_claim(self) -> None:
        """A build that fails fails every waiter with the same error, and a later require builds again."""
        services = ServiceCollection()
        attempts: list[int] = []

        class Pool:
            async def __aenter__(self) -> "Pool":
                attempts.append(len(attempts))
                await asyncio.sleep(0)
                if len(attempts) == 1:
                    raise RuntimeError("connection refused")
                return self

            async def __aexit__(
                self,
                exc_type: type[BaseException] | None,
                exc_value: BaseException | None,
                traceback: TracebackType | None,
            ) -> None: ...

        services.add_singleton(Pool)

        async with AsyncInjector(services) as injector:
            results = await asyncio.gather(injector.require(Pool), injector.require(Pool), return_exceptions=True)
            assert all(isinstance(result, RuntimeError) for result in results)
            assert attempts == [0]
            pool = await injector.require(Pool)

        assert isinstance(pool, Pool)
        assert attempts == [0, 1]

    async def test_fail_cycle_split_across_two_tasks_is_reported_not_deadlocked(self) -> None:
        """Two builds waiting on each other through their post_init hooks raise instead of hanging."""
        services = ServiceCollection()

        class ServiceA:
            @post_init
            async def setup(self, injector: AsyncInjector) -> None:
                await asyncio.sleep(0)
                await injector.require(ServiceB)

        class ServiceB:
            @post_init
            async def setup(self, injector: AsyncInjector) -> None:
                await asyncio.sleep(0)
                await injector.require(ServiceA)

        services.add_singleton(ServiceA)
        services.add_singleton(ServiceB)

        async with AsyncInjector(services) as injector:
            results = await asyncio.wait_for(
                asyncio.gather(injector.require(ServiceA), injector.require(ServiceB), return_exceptions=True),
                timeout=1,
            )

        assert any(isinstance(result, CircularDependencyError) for result in results)


class TestAsyncInjectorRequirements:
    async def test_require_async_injector(self) -> None:
        """A service can depend on `AsyncInjector` by its concrete type."""

        class Service:
            def __init__(self, injector: AsyncInjector) -> None:
                self.injector = injector

        services = ServiceCollection()
        services.add_singleton(Service)

        async with AsyncInjector(services) as injector:
            service = await injector.require(Service)
            assert service.injector is injector


class TestAsyncAnnotatedResolvers:
    async def test_async_annotated_resolver_from_class(self) -> None:
        """An `Annotated` marker with a coroutine `__resolve__` builds the parameter."""
        services = ServiceCollection()

        class Database:
            async def data(self) -> int:
                return 42

        class Service1:
            def __init__(self, value: int) -> None:
                self.value = value

        class Service1Resolver:
            async def __resolve__(self, db: Database) -> Service1:
                return Service1(await db.data())

        class Service2:
            def __init__(self, s1: Annotated[Service1, Service1Resolver()]) -> None:
                self.s1 = s1

        services.add_singleton(Database)
        services.add_scoped(Service1)
        services.add_scoped(Service2)

        async with AsyncInjector(services).get_scoped_injector() as injector:
            s2 = await injector.require(Service2)
            assert s2.s1.value == 42

    async def test_async_annotated_resolver_from_function(self) -> None:
        """Same, for a parameter of a function passed to `call`."""
        services = ServiceCollection()

        class Database:
            async def data(self) -> int:
                return 42

        class Service:
            def __init__(self, value: int) -> None:
                self.value = value

        class TestServiceResolver:
            async def __resolve__(self, db: Database) -> Service:
                return Service(await db.data())

        def call_service(service: Annotated[Service, TestServiceResolver()]) -> int:
            return service.value + 1

        services.add_singleton(Database)
        services.add_scoped(Service)

        async with AsyncInjector(services).get_scoped_injector() as injector:
            result = await injector.call(call_service)
            assert result == 43

    async def test_async_annotated_resolver_of_random_class(self) -> None:
        """`make_annotated_resolver` attaches a coroutine resolver to a bare marker."""
        services = ServiceCollection()

        class Database:
            async def data(self) -> int:
                return 42

        class Service1:
            def __init__(self, value: int) -> None:
                self.value = value

        class RandomAnnotation: ...

        async def resolve_service(_self: RandomAnnotation, db: Database) -> Service1:
            return Service1(await db.data())

        class Service2:
            def __init__(self, s1: Annotated[Service1, RandomAnnotation()]) -> None:
                self.s1 = s1

        services.add_singleton(Database)
        services.add_scoped(Service1)
        services.add_scoped(Service2)
        make_annotated_resolver(RandomAnnotation, resolve_service)

        async with AsyncInjector(services).get_scoped_injector() as injector:
            s2 = await injector.require(Service2)
            assert s2.s1.value == 42

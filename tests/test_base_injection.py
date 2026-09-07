"""Behaviour shared by `SyncInjector` and `AsyncInjector`.

Every test here runs twice, once against each injector, through the `make_injector`
fixture defined in `conftest.py`. Behaviour that only one injector can exhibit lives in
`test_async_injection.py` or `test_sync_injection.py`.
"""

import inspect
from abc import ABC, abstractmethod
from collections.abc import Callable, Generator, Iterator, Sequence
from types import TracebackType
from typing import Annotated, Any, override

import pytest
from conftest import InjectorFactory
from peritype import FWrap, TWrap, wrap_func, wrap_type

from soupape import CallerContext, Injector, ServiceCollection, depends_on, post_init
from soupape._utils import add_type_to_type_globals
from soupape.errors import (
    CallerContextNotAvailableError,
    CaptiveDependencyError,
    CircularDependencyError,
    MissingTypeHintError,
    ScopedServiceNotAvailableError,
    ServiceNotFoundError,
    UnresolvedAnyTypeError,
)
from soupape.extension import (
    InjectionScope,
    ResolutionContext,
    ResolutionFunction,
    ServiceResolver,
    annotation_resolver,
    resolver,
)

pytestmark = pytest.mark.asyncio


class MinimalResolver(ServiceResolver[..., Any]):
    """A custom resolver that instantiates whichever type is required, with a fixed argument.

    It takes nothing from the class it resolves, so the `resolver` decorator can attach it to
    a class before that class exists. `required_types` records what it was asked for.
    """

    def __init__(self) -> None:
        self.required_types: list[TWrap[Any]] = []

    @property
    @override
    def name(self) -> str:
        return "minimal"

    @property
    @override
    def scope(self) -> InjectionScope:
        return InjectionScope.SINGLETON

    @override
    def get_resolution_hints(self, context: ResolutionContext) -> dict[str, TWrap[Any]]:
        return {}

    @override
    def get_instance_function(self) -> FWrap[..., Any]:
        return self._empty_resolver_w

    @override
    def get_resolution_signature(self) -> inspect.Signature:
        return self._empty_resolver_w.signature

    @override
    def get_resolution_func(self, context: ResolutionContext) -> ResolutionFunction[..., Any]:
        required = context.required
        assert required is not None
        self.required_types.append(required)

        def resolve() -> Any:
            return required.instantiate(42)

        return resolve


class TestBasicInjection:
    async def test_simple_injection(self, make_injector: InjectorFactory) -> None:
        """Requires a singleton that has no dependencies."""
        services = ServiceCollection()

        class TestService:
            def __init__(self) -> None:
                pass

            def greet(self) -> str:
                return "Hello, World!"

        services.add_singleton(TestService)

        async with make_injector(services) as injector:
            service = await injector.require(TestService)

        assert service.greet() == "Hello, World!"

    async def test_simple_injection_in_service(self, make_injector: InjectorFactory) -> None:
        """Injects a singleton into another service's constructor."""
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

        async with make_injector(services) as injector:
            service = await injector.require(TestService)

        assert service.greet() == "Hello, World!"

    async def test_inject_service_twice(self, make_injector: InjectorFactory) -> None:
        """Two requires of the same singleton return the same instance."""
        services = ServiceCollection()

        class Service:
            def __init__(self) -> None: ...

        services.add_singleton(Service)

        async with make_injector(services) as injector:
            service1 = await injector.require(Service)
            service2 = await injector.require(Service)

        assert service1 is service2

    async def test_inject_service_with_positional_only_parameter(self, make_injector: InjectorFactory) -> None:
        """Resolves a positional-only constructor parameter."""
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

        async with make_injector(services) as injector:
            service = await injector.require(ServiceWithPositionalOnly)

        assert service.greet() == "Hello from Positional!"

    async def test_inject_service_with_keyword_only_parameter(self, make_injector: InjectorFactory) -> None:
        """Resolves a keyword-only constructor parameter."""
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

        async with make_injector(services) as injector:
            service = await injector.require(ServiceWithKeywordOnly)

        assert service.greet() == "Hello from Keyword!"

    async def test_inject_service_with_variadic_parameters(self, make_injector: InjectorFactory) -> None:
        """Variadic parameters are not injectable, so they are left empty."""
        services = ServiceCollection()

        class Dep: ...

        class ServiceWithVariadics:
            def __init__(self, *args: Dep, **kwargs: Dep) -> None:
                self.args = args
                self.kwargs = kwargs

        services.add_singleton(Dep)
        services.add_singleton(ServiceWithVariadics)

        async with make_injector(services) as injector:
            service = await injector.require(ServiceWithVariadics)

        assert service.args == ()
        assert service.kwargs == {}

    async def test_inject_service_with_unannotated_variadic_parameters(
        self,
        make_injector: InjectorFactory,
    ) -> None:
        """Variadic parameters need no type hint, since nothing is resolved for them."""
        services = ServiceCollection()

        class ServiceWithVariadics:
            def __init__(
                self,
                *args,  # pyright: ignore[reportMissingParameterType, reportUnknownParameterType]
                **kwargs,  # pyright: ignore[reportMissingParameterType, reportUnknownParameterType]
            ) -> None:
                self.args: tuple[Any, ...] = args
                self.kwargs: dict[str, Any] = kwargs

        services.add_singleton(ServiceWithVariadics)

        async with make_injector(services) as injector:
            service = await injector.require(ServiceWithVariadics)

        assert service.args == ()
        assert service.kwargs == {}

    async def test_inject_service_with_variadic_parameter_of_unregistered_type(
        self,
        make_injector: InjectorFactory,
    ) -> None:
        """A variadic parameter annotated with an unregistered service does not fail."""
        services = ServiceCollection()

        class Unregistered: ...

        class ServiceWithVariadic:
            def __init__(self, *args: Unregistered) -> None:
                self.args = args

        services.add_singleton(ServiceWithVariadic)

        async with make_injector(services) as injector:
            service = await injector.require(ServiceWithVariadic)

        assert service.args == ()

    async def test_inject_service_with_declared_and_variadic_parameters(
        self,
        make_injector: InjectorFactory,
    ) -> None:
        """A declared parameter is still injected when a variadic one follows it."""
        services = ServiceCollection()

        class Dep:
            def greet(self) -> str:
                return "Hello from Dep!"

        class ServiceWithBoth:
            def __init__(self, dep: Dep, *rest: Dep) -> None:
                self.dep = dep
                self.rest = rest

        services.add_singleton(Dep)
        services.add_singleton(ServiceWithBoth)

        async with make_injector(services) as injector:
            service = await injector.require(ServiceWithBoth)

        assert service.dep.greet() == "Hello from Dep!"
        assert service.rest == ()


class TestGenericInjection:
    async def test_inject_generic_type(self, make_injector: InjectorFactory) -> None:
        """Requires a generic service registered under a specialized alias."""

        class Service[T]: ...

        services = ServiceCollection()
        services.add_singleton(Service[str])

        async with make_injector(services) as injector:
            service = await injector.require(Service[str])
            assert service is not None
            assert isinstance(service, Service)

    async def test_require_generic_type(self, make_injector: InjectorFactory) -> None:
        """The requested type argument is injected as a `type[T]` parameter."""

        class Service[T]:
            def __init__(self, cls: type[T]) -> None:
                self.cls = cls

        services = ServiceCollection()
        services.add_singleton(Service)

        async with make_injector(services) as injector:
            service = await injector.require(Service[str])
            assert service.cls is str

    async def test_require_generic_twrap(self, make_injector: InjectorFactory) -> None:
        """The requested type argument is injected as a `TWrap[T]` parameter."""

        class Service[T]:
            def __init__(self, tw: TWrap[T]) -> None:
                self.tw = tw

        services = ServiceCollection()
        services.add_singleton(Service)

        async with make_injector(services) as injector:
            service = await injector.require(Service[int])
            assert service.tw == wrap_type(int)

    async def test_require_two_generic_twrap(self, make_injector: InjectorFactory) -> None:
        """Each of two type parameters is injected as its own `TWrap`."""

        class Service[T, U]:
            def __init__(self, tw1: TWrap[T], tw2: TWrap[U]) -> None:
                self.tw1 = tw1
                self.tw2 = tw2

        services = ServiceCollection()
        services.add_singleton(Service)

        async with make_injector(services) as injector:
            service = await injector.require(Service[int, str])
            assert service.tw1 == wrap_type(int)
            assert service.tw2 == wrap_type(str)

    async def test_require_inherited_generic_twrap(self, make_injector: InjectorFactory) -> None:
        """Type parameters are remapped through a chain of generic base classes."""

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

        async with make_injector(services) as injector:
            service = await injector.require(Service[int, str, float])
            assert service.tw1 == wrap_type(float)
            assert service.tw2 == wrap_type(str)
            assert service.tw3 == wrap_type(int)

    async def test_register_as_any_different_injected(self, make_injector: InjectorFactory) -> None:
        """A service registered as `Any` yields one instance per specialization."""

        class Service[T]:
            def __init__(self, cls: type[T]) -> None:
                self.cls = cls

        services = ServiceCollection()
        services.add_singleton(Service[Any])

        async with make_injector(services) as injector:
            service_int = await injector.require(Service[int])
            service_str = await injector.require(Service[str])

        assert service_int is not service_str
        assert service_int.cls is int
        assert service_str.cls is str

    async def test_register_complex_generic_structure(self, make_injector: InjectorFactory) -> None:
        """A generic controller gets the base registration matching its own type argument."""

        class BaseService[T]:
            def fetch_data(self) -> str: ...

        class Service1[T](BaseService[T]):
            def fetch_data(self) -> str:
                return "Service1 Data"

        class Service2[T](BaseService[T]):
            def fetch_data(self) -> str:
                return "Service2 Data"

        class Controller[T]:
            def __init__(self, service: BaseService[T]) -> None:
                self.service = service

            def get_data(self) -> str:
                return self.service.fetch_data()

        services = ServiceCollection()
        services.add_singleton(BaseService[Any], Service1)
        services.add_singleton(BaseService[str], Service2)
        services.add_singleton(Controller[int])
        services.add_singleton(Controller[str])

        async with make_injector(services) as injector:
            controller_int = await injector.require(Controller[int])
            assert controller_int.get_data() == "Service1 Data"

            controller_str = await injector.require(Controller[str])
            assert controller_str.get_data() == "Service2 Data"


class TestInterfaceRegistration:
    async def test_inject_singleton_with_interface(self, make_injector: InjectorFactory) -> None:
        """An implementation registered under a base class shares one instance with it."""
        services = ServiceCollection()

        class BaseService: ...

        class Subservice(BaseService): ...

        services.add_singleton(BaseService, Subservice)
        services.add_singleton(Subservice)

        async with make_injector(services) as injector:
            base_instance = await injector.require(BaseService)
            sub_instance = await injector.require(Subservice)

        assert base_instance is sub_instance

    async def test_inject_with_resolver_custom_interface(self, make_injector: InjectorFactory) -> None:
        """A resolver registered under two interfaces shares one instance between them."""
        services = ServiceCollection()

        class BaseService: ...

        class Service(BaseService):
            def __init__(self) -> None: ...

        def service_resolver() -> Service:
            return Service()

        services.add_singleton(service_resolver)
        services.add_singleton(BaseService, service_resolver)

        async with make_injector(services) as injector:
            service1 = await injector.require(Service)
            service2 = await injector.require(BaseService)

        assert service1 is service2
        assert isinstance(service1, Service)
        assert isinstance(service2, Service)

    async def test_inject_with_catch_all_interface(self, make_injector: InjectorFactory) -> None:
        """An exact specialization wins over the `Any` registration."""
        services = ServiceCollection()

        class Service[T]:
            def fetch_data(self) -> str: ...

        class Service1[T](Service[T]):
            def fetch_data(self) -> str:
                return "Service1 Data"

        class Service2[T](Service[T]):
            def fetch_data(self) -> str:
                return "Service2 Data"

        services.add_singleton(Service[Any], Service1)
        services.add_singleton(Service[str], Service2)

        async with make_injector(services) as injector:
            service1 = await injector.require(Service[int])
            service2 = await injector.require(Service[str])

        assert service1.fetch_data() == "Service1 Data"
        assert service2.fetch_data() == "Service2 Data"

    async def test_register_partial_catch_all_resolver(self, make_injector: InjectorFactory) -> None:
        """Partially specialized registrations are matched most-specific first."""
        services = ServiceCollection()

        class Service[T, U]:
            def fetch_data(self) -> str: ...

        class Service1[T, U](Service[T, U]):
            def fetch_data(self) -> str:
                return "Service1 Data"

        class Service2[T, U](Service[T, U]):
            def fetch_data(self) -> str:
                return "Service2 Data"

        class Service3[T, U](Service[T, U]):
            def fetch_data(self) -> str:
                return "Service3 Data"

        services.add_singleton(Service[int, Any], Service1)
        services.add_singleton(Service[int, str], Service2)
        services.add_singleton(Service[str, Any], Service3)

        async with make_injector(services) as injector:
            service1 = await injector.require(Service[int, float])
            service2 = await injector.require(Service[int, str])
            service3 = await injector.require(Service[str, float])

        assert service1.fetch_data() == "Service1 Data"
        assert service2.fetch_data() == "Service2 Data"
        assert service3.fetch_data() == "Service3 Data"


class TestResolvers:
    async def test_inject_resolver_with_params(self, make_injector: InjectorFactory) -> None:
        """A resolver function gets its own parameters injected."""
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

        async with make_injector(services) as injector:
            service = await injector.require(Service)

        assert service.greet() == "Hello, World!"

    async def test_inject_with_catch_all_resolver(self, make_injector: InjectorFactory) -> None:
        """A generic resolver is called once per requested specialization."""
        services = ServiceCollection()

        class Service[T: int | str]:
            def __init__(self, id: int) -> None:
                self.id = id

            def fetch_data(self) -> str:
                return f"Data {self.id}"

        count = {"id": 0}

        def service_resolver[T: int | str](_cls: type[T]) -> Service[T]:
            count["id"] += 1
            return Service[_cls](count["id"])

        services.add_singleton(service_resolver)

        async with make_injector(services) as injector:
            service1 = await injector.require(Service[int])
            service2 = await injector.require(Service[str])

        assert service1 is not service2
        assert service1.fetch_data() == "Data 1"
        assert service2.fetch_data() == "Data 2"

    async def test_require_generic_type_in_resolver(self, make_injector: InjectorFactory) -> None:
        """A resolver receives the requested type argument as `type[T]`."""

        class Service[T]:
            def __init__(self, cls: type[T]) -> None:
                self.cls = cls

        def service_resolver[T](cls: type[T]) -> Service[T]:
            return Service(cls)

        services = ServiceCollection()
        services.add_singleton(service_resolver)

        async with make_injector(services) as injector:
            service = await injector.require(Service[float])
            assert service.cls is float

    async def test_require_two_generic_type_in_resolver(self, make_injector: InjectorFactory) -> None:
        """A resolver may reorder the type arguments it passes on."""

        class Service[T, U]:
            def __init__(self, cls1: type[T], cls2: type[U]) -> None:
                self.cls1 = cls1
                self.cls2 = cls2

        def service_resolver[T, U](cls1: type[T], cls2: type[U]) -> Service[U, T]:
            return Service(cls2, cls1)

        services = ServiceCollection()
        services.add_singleton(service_resolver)

        async with make_injector(services) as injector:
            service = await injector.require(Service[float, int])
            assert service.cls1 is float
            assert service.cls2 is int

    async def test_require_lambda_resolver(self, make_injector: InjectorFactory) -> None:
        """A lambda registered against an explicit interface builds the service."""

        class Service:
            def __init__(self, value: int) -> None:
                self.value = value

        services = ServiceCollection()
        services.add_singleton(Service, lambda: Service(42))

        async with make_injector(services) as injector:
            service = await injector.require(Service)
            assert service.value == 42

    async def test_inject_resolver_with_variadic_parameters(self, make_injector: InjectorFactory) -> None:
        """A resolver function is called with nothing for its variadic parameters."""

        class Dep: ...

        class Service:
            def __init__(self, args: tuple[Dep, ...], kwargs: dict[str, Dep]) -> None:
                self.args = args
                self.kwargs = kwargs

        def service_resolver(*args: Dep, **kwargs: Dep) -> Service:
            return Service(args, kwargs)

        services = ServiceCollection()
        services.add_singleton(Dep)
        services.add_singleton(service_resolver)

        async with make_injector(services) as injector:
            service = await injector.require(Service)

        assert service.args == ()
        assert service.kwargs == {}


class TestScopes:
    async def test_inject_singleton_in_different_scopes(self, make_injector: InjectorFactory) -> None:
        """A singleton is shared across scoped injectors."""
        services = ServiceCollection()

        class SingletonService:
            def __init__(self) -> None:
                pass

        services.add_singleton(SingletonService)

        async with make_injector(services) as injector:
            scoped1 = injector.get_scoped_injector()
            scoped2 = injector.get_scoped_injector()
            instance1 = await scoped1.require(SingletonService)
            instance2 = await scoped2.require(SingletonService)

        assert instance1 is instance2

    async def test_inject_scoped_twice(self, make_injector: InjectorFactory) -> None:
        """A scoped service is reused inside one scope."""
        services = ServiceCollection()

        class ScopedService:
            def __init__(self) -> None:
                pass

        services.add_scoped(ScopedService)

        async with make_injector(services) as root:
            injector = root.get_scoped_injector()
            instance1 = await injector.require(ScopedService)
            instance2 = await injector.require(ScopedService)

        assert instance1 is instance2

    async def test_inject_scoped_twice_in_different_sessions(self, make_injector: InjectorFactory) -> None:
        """A scoped service is not shared between two scopes."""
        services = ServiceCollection()

        class ScopedService:
            def __init__(self) -> None:
                pass

        services.add_scoped(ScopedService)

        async with make_injector(services) as injector:
            scoped1 = injector.get_scoped_injector()
            scoped2 = injector.get_scoped_injector()
            instance1 = await scoped1.require(ScopedService)
            instance2 = await scoped2.require(ScopedService)

        assert instance1 is not instance2

    async def test_inject_transient(self, make_injector: InjectorFactory) -> None:
        """A transient service is rebuilt on every require."""
        services = ServiceCollection()

        class TransientService:
            def __init__(self) -> None:
                pass

        services.add_transient(TransientService)

        async with make_injector(services) as injector:
            instance1 = await injector.require(TransientService)
            instance2 = await injector.require(TransientService)

        assert instance1 is not instance2

    async def test_inject_scoped_with_resolver(self, make_injector: InjectorFactory) -> None:
        """A scoped registration backed by a resolver function resolves."""
        services = ServiceCollection()

        class Service:
            def __init__(self) -> None:
                pass

            def fetch_data(self) -> str:
                return "Data"

        def service_resolver() -> Service:
            return Service()

        services.add_scoped(service_resolver)

        async with make_injector(services) as injector:
            scoped = injector.get_scoped_injector()
            service = await scoped.require(Service)

        assert service.fetch_data() == "Data"

    async def test_inject_scoped_with_resolver_twice(self, make_injector: InjectorFactory) -> None:
        """A resolver-backed scoped service is reused inside one scope."""
        services = ServiceCollection()

        class Service: ...

        def service_resolver() -> Service:
            return Service()

        services.add_scoped(service_resolver)

        async with make_injector(services) as injector:
            scoped = injector.get_scoped_injector()
            service1 = await scoped.require(Service)
            service2 = await scoped.require(Service)

        assert service1 is service2

    async def test_inject_transient_with_resolver(self, make_injector: InjectorFactory) -> None:
        """A transient registration backed by a resolver function resolves."""
        services = ServiceCollection()

        class Service:
            def __init__(self) -> None:
                pass

            def fetch_data(self) -> str:
                return "Data"

        def service_resolver() -> Service:
            return Service()

        services.add_transient(service_resolver)

        async with make_injector(services) as injector:
            scoped = injector.get_scoped_injector()
            service = await scoped.require(Service)

        assert service.fetch_data() == "Data"

    async def test_inject_transient_with_resolver_twice(self, make_injector: InjectorFactory) -> None:
        """A resolver-backed transient service is rebuilt on every require."""
        services = ServiceCollection()

        class Service: ...

        def service_resolver() -> Service:
            return Service()

        services.add_transient(service_resolver)

        async with make_injector(services) as injector:
            scoped = injector.get_scoped_injector()
            service1 = await scoped.require(Service)
            service2 = await scoped.require(Service)

        assert service1 is not service2

    async def test_fail_inject_scoped_in_root_injector(self, make_injector: InjectorFactory) -> None:
        """Requiring a scoped service from the root injector fails."""
        services = ServiceCollection()

        class ScopedService:
            def __init__(self) -> None:
                pass

        services.add_scoped(ScopedService)

        async with make_injector(services) as injector:
            with pytest.raises(ScopedServiceNotAvailableError) as exc_info:
                await injector.require(ScopedService)

        assert exc_info.value.code == "soupape.scoped_service.not_available"
        assert exc_info.value.message == (
            f"Scoped service for interface '{ScopedService.__qualname__}' is not available in the root scope."
        )


class TestDependencyScopes:
    """A dependency keeps its own registered lifetime, whatever the lifetime of the service requiring it."""

    async def test_singleton_dependency_of_scoped_service_is_shared_with_root(
        self, make_injector: InjectorFactory
    ) -> None:
        """A singleton first built as a dependency inside a scope is the one the root injector serves."""
        services = ServiceCollection()

        class SingletonService:
            def __init__(self) -> None:
                pass

        class ScopedService:
            def __init__(self, singleton: SingletonService) -> None:
                self.singleton = singleton

        services.add_singleton(SingletonService)
        services.add_scoped(ScopedService)

        async with make_injector(services) as root:
            async with root.get_scoped_injector() as scoped:
                scoped_service = await scoped.require(ScopedService)
            from_root = await root.require(SingletonService)

        assert scoped_service.singleton is from_root

    async def test_singleton_dependency_of_scoped_service_is_shared_between_scopes(
        self, make_injector: InjectorFactory
    ) -> None:
        """Two scopes requiring a scoped service get the same singleton dependency."""
        services = ServiceCollection()

        class SingletonService:
            def __init__(self) -> None:
                pass

        class ScopedService:
            def __init__(self, singleton: SingletonService) -> None:
                self.singleton = singleton

        services.add_singleton(SingletonService)
        services.add_scoped(ScopedService)

        async with make_injector(services) as root:
            async with root.get_scoped_injector() as scoped1:
                service1 = await scoped1.require(ScopedService)
            async with root.get_scoped_injector() as scoped2:
                service2 = await scoped2.require(ScopedService)

        assert service1 is not service2
        assert service1.singleton is service2.singleton

    async def test_singleton_dependency_of_transient_service_is_reused(self, make_injector: InjectorFactory) -> None:
        """A singleton first built as a dependency of a transient service is built once."""
        services = ServiceCollection()

        class SingletonService:
            def __init__(self) -> None:
                pass

        class TransientService:
            def __init__(self, singleton: SingletonService) -> None:
                self.singleton = singleton

        services.add_singleton(SingletonService)
        services.add_transient(TransientService)

        async with make_injector(services) as injector:
            transient1 = await injector.require(TransientService)
            transient2 = await injector.require(TransientService)
            direct = await injector.require(SingletonService)

        assert transient1 is not transient2
        assert transient1.singleton is transient2.singleton
        assert transient1.singleton is direct

    async def test_singleton_dependency_of_called_function_is_reused(self, make_injector: InjectorFactory) -> None:
        """A singleton first built for `call` is the one served to later calls and requires."""
        services = ServiceCollection()

        class SingletonService:
            def __init__(self) -> None:
                pass

        services.add_singleton(SingletonService)

        def get_singleton(singleton: SingletonService) -> SingletonService:
            return singleton

        async with make_injector(services) as injector:
            from_call1 = await injector.call(get_singleton)
            from_call2 = await injector.call(get_singleton)
            direct = await injector.require(SingletonService)

        assert from_call1 is from_call2
        assert from_call1 is direct

    async def test_scoped_dependency_of_transient_service_is_reused_in_scope(
        self, make_injector: InjectorFactory
    ) -> None:
        """A scoped service first built as a dependency of a transient service is reused inside the scope."""
        services = ServiceCollection()

        class ScopedService:
            def __init__(self) -> None:
                pass

        class TransientService:
            def __init__(self, scoped: ScopedService) -> None:
                self.scoped = scoped

        services.add_scoped(ScopedService)
        services.add_transient(TransientService)

        async with make_injector(services).get_scoped_injector() as injector:
            transient1 = await injector.require(TransientService)
            transient2 = await injector.require(TransientService)
            direct = await injector.require(ScopedService)

        assert transient1 is not transient2
        assert transient1.scoped is transient2.scoped
        assert transient1.scoped is direct

    async def test_scoped_dependency_of_called_function_is_reused_in_scope(
        self, make_injector: InjectorFactory
    ) -> None:
        """A scoped service first built for `call` is the one served to later calls inside the scope."""
        services = ServiceCollection()

        class ScopedService:
            def __init__(self) -> None:
                pass

        services.add_scoped(ScopedService)

        def get_scoped(scoped: ScopedService) -> ScopedService:
            return scoped

        async with make_injector(services).get_scoped_injector() as injector:
            from_call1 = await injector.call(get_scoped)
            from_call2 = await injector.call(get_scoped)
            direct = await injector.require(ScopedService)

        assert from_call1 is from_call2
        assert from_call1 is direct

    async def test_transient_dependency_of_singleton_service_is_not_cached(
        self, make_injector: InjectorFactory
    ) -> None:
        """A transient injected into a singleton is not served again to a later require."""
        services = ServiceCollection()

        class TransientService:
            def __init__(self) -> None:
                pass

        class SingletonService:
            def __init__(self, transient: TransientService) -> None:
                self.transient = transient

        services.add_transient(TransientService)
        services.add_singleton(SingletonService)

        async with make_injector(services) as injector:
            singleton = await injector.require(SingletonService)
            direct1 = await injector.require(TransientService)
            direct2 = await injector.require(TransientService)

        assert direct1 is not singleton.transient
        assert direct2 is not singleton.transient
        assert direct1 is not direct2

    async def test_transient_dependency_of_scoped_service_is_not_cached(self, make_injector: InjectorFactory) -> None:
        """A transient injected into a scoped service is not served again inside the scope."""
        services = ServiceCollection()

        class TransientService:
            def __init__(self) -> None:
                pass

        class ScopedService:
            def __init__(self, transient: TransientService) -> None:
                self.transient = transient

        services.add_transient(TransientService)
        services.add_scoped(ScopedService)

        async with make_injector(services).get_scoped_injector() as injector:
            scoped = await injector.require(ScopedService)
            direct1 = await injector.require(TransientService)
            direct2 = await injector.require(TransientService)

        assert direct1 is not scoped.transient
        assert direct2 is not scoped.transient
        assert direct1 is not direct2

    async def test_singleton_dependency_of_scoped_service_with_resolver_is_shared_with_root(
        self, make_injector: InjectorFactory
    ) -> None:
        """The dependency lifetime also holds when the singleton comes from a resolver function."""
        services = ServiceCollection()

        class SingletonService:
            def __init__(self) -> None:
                pass

        class ScopedService:
            def __init__(self, singleton: SingletonService) -> None:
                self.singleton = singleton

        def singleton_resolver() -> SingletonService:
            return SingletonService()

        services.add_singleton(singleton_resolver)
        services.add_scoped(ScopedService)

        async with make_injector(services) as root:
            async with root.get_scoped_injector() as scoped:
                scoped_service = await scoped.require(ScopedService)
            from_root = await root.require(SingletonService)

        assert scoped_service.singleton is from_root

    async def test_fail_singleton_depending_on_scoped_service(self, make_injector: InjectorFactory) -> None:
        """A singleton cannot capture a scoped service, whichever injector requires it."""
        services = ServiceCollection()
        instantiated: list[str] = []

        class ScopedService:
            def __init__(self) -> None:
                instantiated.append("scoped")

        class SingletonService:
            def __init__(self, scoped: ScopedService) -> None:
                instantiated.append("singleton")

        services.add_scoped(ScopedService)
        services.add_singleton(SingletonService)

        async with make_injector(services) as root:
            with pytest.raises(CaptiveDependencyError) as root_exc_info:
                await root.require(SingletonService)
            async with root.get_scoped_injector() as scoped:
                with pytest.raises(CaptiveDependencyError) as scoped_exc_info:
                    await scoped.require(SingletonService)

        assert instantiated == []
        for exc_info in (root_exc_info, scoped_exc_info):
            assert exc_info.value.code == "soupape.dependency.captive"
            assert exc_info.value.singleton == SingletonService.__qualname__
            assert exc_info.value.dependency == ScopedService.__qualname__
            assert exc_info.value.message == (
                f"Singleton service '{SingletonService.__qualname__}' "
                f"cannot depend on scoped service '{ScopedService.__qualname__}'."
            )

    async def test_fail_singleton_depending_on_scoped_service_through_transient(
        self, make_injector: InjectorFactory
    ) -> None:
        """A transient living inside a singleton cannot capture a scoped service either."""
        services = ServiceCollection()

        class ScopedService:
            def __init__(self) -> None:
                pass

        class TransientService:
            def __init__(self, scoped: ScopedService) -> None:
                self.scoped = scoped

        class SingletonService:
            def __init__(self, transient: TransientService) -> None:
                self.transient = transient

        services.add_scoped(ScopedService)
        services.add_transient(TransientService)
        services.add_singleton(SingletonService)

        async with make_injector(services).get_scoped_injector() as injector:
            with pytest.raises(CaptiveDependencyError) as exc_info:
                await injector.require(SingletonService)

        assert exc_info.value.singleton == SingletonService.__qualname__
        assert exc_info.value.dependency == ScopedService.__qualname__

    async def test_fail_singleton_resolver_depending_on_scoped_service(self, make_injector: InjectorFactory) -> None:
        """The rule also holds when the singleton comes from a resolver function."""
        services = ServiceCollection()

        class ScopedService:
            def __init__(self) -> None:
                pass

        class SingletonService:
            def __init__(self) -> None:
                pass

        def singleton_resolver(scoped: ScopedService) -> SingletonService:
            return SingletonService()

        services.add_scoped(ScopedService)
        services.add_singleton(singleton_resolver)

        async with make_injector(services).get_scoped_injector() as injector:
            with pytest.raises(CaptiveDependencyError) as exc_info:
                await injector.require(SingletonService)

        assert exc_info.value.singleton == SingletonService.__qualname__
        assert exc_info.value.dependency == ScopedService.__qualname__

    async def test_fail_scoped_service_depending_on_singleton_capturing_scoped_service(
        self, make_injector: InjectorFactory
    ) -> None:
        """The captive singleton is reported even when it is itself a dependency."""
        services = ServiceCollection()

        class ScopedService:
            def __init__(self) -> None:
                pass

        class SingletonService:
            def __init__(self, scoped: ScopedService) -> None:
                self.scoped = scoped

        class OtherScopedService:
            def __init__(self, singleton: SingletonService) -> None:
                self.singleton = singleton

        services.add_scoped(ScopedService)
        services.add_singleton(SingletonService)
        services.add_scoped(OtherScopedService)

        async with make_injector(services).get_scoped_injector() as injector:
            with pytest.raises(CaptiveDependencyError) as exc_info:
                await injector.require(OtherScopedService)

        assert exc_info.value.singleton == SingletonService.__qualname__
        assert exc_info.value.dependency == ScopedService.__qualname__

    async def test_singleton_depending_on_resolve_context(self, make_injector: InjectorFactory) -> None:
        """`ResolutionContext` is never stored in a scope, so a singleton may receive it."""
        services = ServiceCollection()

        class SingletonService:
            def __init__(self, ctx: ResolutionContext) -> None:
                self.ctx = ctx

        services.add_singleton(SingletonService)

        async with make_injector(services) as root:
            from_root = await root.require(SingletonService)
            async with root.get_scoped_injector() as scoped:
                from_scope = await scoped.require(SingletonService)

        assert from_root is from_scope
        assert from_root.ctx.caller_context is None


class TestPostInit:
    async def test_inject_with_post_init(self, make_injector: InjectorFactory) -> None:
        """A `post_init` hook runs after the instance is built."""
        services = ServiceCollection()

        class TestService:
            def __init__(self) -> None:
                self.initialized = False

            @post_init
            def initialize(self) -> None:
                self.initialized = True

        services.add_singleton(TestService)

        async with make_injector(services) as injector:
            service = await injector.require(TestService)

        assert service.initialized is True

    async def test_inject_with_inherited_post_init(self, make_injector: InjectorFactory) -> None:
        """Inherited `post_init` hooks run base class first."""
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

        async with make_injector(services) as injector:
            service = await injector.require(TestService)

        assert service.numbers == [1, 2]

    async def test_overridden_post_init_runs_once(self, make_injector: InjectorFactory) -> None:
        """A `post_init` hook overridden in a subclass runs once, through the override."""
        services = ServiceCollection()
        events: list[str] = []

        class BaseService:
            @post_init
            def initialize(self) -> None:
                events.append("base")

        class ChildService(BaseService):
            @post_init
            @override
            def initialize(self) -> None:
                events.append("child")

        services.add_singleton(ChildService)

        async with make_injector(services) as injector:
            await injector.require(ChildService)

        assert events == ["child"]

    async def test_post_init_overridden_without_decorator_does_not_run(self, make_injector: InjectorFactory) -> None:
        """Overriding a hook without `post_init` removes it: the override is a plain method."""
        services = ServiceCollection()
        events: list[str] = []

        class BaseService:
            @post_init
            def initialize(self) -> None:
                events.append("base")

        class ChildService(BaseService):
            @override
            def initialize(self) -> None:
                events.append("child")

        services.add_singleton(ChildService)

        async with make_injector(services) as injector:
            await injector.require(ChildService)

        assert events == []

    async def test_overridden_post_init_keeps_its_parent_position(self, make_injector: InjectorFactory) -> None:
        """Hooks run parents first, in definition order; an override runs where the parent's hook was."""
        services = ServiceCollection()
        events: list[str] = []

        class BaseService:
            @post_init
            def first(self) -> None:
                events.append("first")

            @post_init
            def second(self) -> None:
                events.append("second")

        class ChildService(BaseService):
            @post_init
            def third(self) -> None:
                events.append("third")

            @post_init
            @override
            def second(self) -> None:
                events.append("child second")

        services.add_singleton(ChildService)

        async with make_injector(services) as injector:
            await injector.require(ChildService)

        assert events == ["first", "child second", "third"]

    async def test_post_init_in_diamond_inheritance_runs_once(self, make_injector: InjectorFactory) -> None:
        """A hook reachable through two base classes runs once, in MRO order."""
        services = ServiceCollection()
        events: list[str] = []

        class Root:
            @post_init
            def init_root(self) -> None:
                events.append("root")

        class Left(Root):
            @post_init
            def init_left(self) -> None:
                events.append("left")

        class Right(Root):
            @post_init
            def init_right(self) -> None:
                events.append("right")

        class Leaf(Left, Right):
            @post_init
            def init_leaf(self) -> None:
                events.append("leaf")

        services.add_singleton(Leaf)

        async with make_injector(services) as injector:
            await injector.require(Leaf)

        assert events == ["root", "right", "left", "leaf"]

    async def test_inject_post_init_with_args(self, make_injector: InjectorFactory) -> None:
        """A `post_init` hook gets its parameters injected."""

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

        async with make_injector(services) as injector:
            service = await injector.require(TestService)

        assert service.initialized == 42

    async def test_inject_post_init_with_variadic_parameters(self, make_injector: InjectorFactory) -> None:
        """A `post_init` hook is called with nothing for its variadic parameters."""

        class Dep: ...

        class TestService:
            def __init__(self) -> None:
                self.args: tuple[Dep, ...] | None = None
                self.kwargs: dict[str, Dep] | None = None

            @post_init
            def initialize(self, *args: Dep, **kwargs: Dep) -> None:
                self.args = args
                self.kwargs = kwargs

        services = ServiceCollection()
        services.add_singleton(Dep)
        services.add_singleton(TestService)

        async with make_injector(services) as injector:
            service = await injector.require(TestService)

        assert service.args == ()
        assert service.kwargs == {}


class TestFunctionCalls:
    async def test_call_function_with_injected_dependencies(self, make_injector: InjectorFactory) -> None:
        """`call` injects a function's parameters and returns its result."""
        services = ServiceCollection()

        class DependencyService:
            def __init__(self) -> None:
                pass

            def get_value(self) -> str:
                return "Injected Value"

        services.add_singleton(DependencyService)

        async with make_injector(services) as injector:

            def test_function(dep_service: DependencyService) -> str:
                return dep_service.get_value()

            result = await injector.call(test_function)

        assert result == "Injected Value"


class TestGeneratorResolvers:
    async def test_inject_yield_resolver(self, make_injector: InjectorFactory) -> None:
        """A generator resolver yields the service instance."""
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

        async with make_injector(services) as injector:
            resource = await injector.require(Resource)

        assert resource.active is True

    async def test_injection_context_manager_sync_resolver(self, make_injector: InjectorFactory) -> None:
        """Code after the yield runs when the injector scope closes."""
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

        async with make_injector(services) as injector:
            resource = await injector.require(Resource)
            assert resource.active is True
        assert resource.active is False


class TestGeneratorResolverHints:
    async def test_generator_resolver_with_iterator_hint(self, make_injector: InjectorFactory) -> None:
        """`Iterator[T]` is accepted as the return hint of a generator resolver."""
        services = ServiceCollection()
        events: list[str] = []

        class Service:
            pass

        def service_resolver() -> Iterator[Service]:
            yield Service()
            events.append("closed")

        services.add_scoped(service_resolver)

        async with make_injector(services).get_scoped_injector() as injector:
            service = await injector.require(Service)
            assert isinstance(service, Service)
        assert events == ["closed"]


class TestGeneratorResolverTeardown:
    async def test_generator_resolvers_are_closed_in_reverse_build_order(self, make_injector: InjectorFactory) -> None:
        """Yield-based resolvers resume dependents first, in the reverse of the order they were built."""
        services = ServiceCollection()
        events: list[str] = []

        class Database:
            pass

        class Repository:
            def __init__(self, database: Database) -> None:
                self.database = database

        def database_resolver() -> Generator[Database]:
            yield Database()
            events.append("database")

        def repository_resolver(database: Database) -> Generator[Repository]:
            yield Repository(database)
            events.append("repository")

        services.add_scoped(database_resolver)
        services.add_scoped(repository_resolver)

        async with make_injector(services).get_scoped_injector() as injector:
            await injector.require(Repository)
            assert events == []
        assert events == ["repository", "database"]

    async def test_generator_resolvers_are_all_closed_when_one_fails(self, make_injector: InjectorFactory) -> None:
        """A resolver raising after its `yield` does not stop the others from resuming, and still propagates."""
        services = ServiceCollection()
        events: list[str] = []

        class Database:
            pass

        class Repository:
            def __init__(self, database: Database) -> None:
                self.database = database

        def database_resolver() -> Generator[Database]:
            try:
                yield Database()
            finally:
                events.append("database")

        def repository_resolver(database: Database) -> Generator[Repository]:
            yield Repository(database)
            raise RuntimeError("repository failed")

        services.add_scoped(database_resolver)
        services.add_scoped(repository_resolver)

        with pytest.raises(RuntimeError, match="repository failed"):
            async with make_injector(services).get_scoped_injector() as injector:
                await injector.require(Repository)
        assert events == ["database"]

    async def test_exception_in_scope_is_thrown_into_generator_resolvers(self, make_injector: InjectorFactory) -> None:
        """An exception leaving the scope is raised at the resolver's `yield`, then propagates."""
        services = ServiceCollection()
        events: list[str] = []

        class Service:
            pass

        def service_resolver() -> Generator[Service]:
            try:
                yield Service()
            except ValueError:
                events.append("caught")
                raise
            finally:
                events.append("closed")

        services.add_scoped(service_resolver)

        with pytest.raises(ValueError, match="boom"):
            async with make_injector(services).get_scoped_injector() as injector:
                await injector.require(Service)
                raise ValueError("boom")
        assert events == ["caught", "closed"]


class TestContextManagerServices:
    async def test_injection_context_manager_service(self, make_injector: InjectorFactory) -> None:
        """A context-manager service is entered on build and exited with the scope."""
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

        async with make_injector(services) as injector:
            resource = await injector.require(Resource)
            assert resource.active is True
        assert resource.active is False

    async def test_singleton_context_manager_created_in_scope_is_exited_with_root(
        self, make_injector: InjectorFactory
    ) -> None:
        """A singleton built inside a scope outlives that scope and is exited with the root injector."""
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

        async with make_injector(services) as root:
            async with root.get_scoped_injector() as scoped:
                resource = await scoped.require(Resource)
                assert resource.active is True
            assert resource.active is True
            assert await root.require(Resource) is resource
            async with root.get_scoped_injector() as scoped:
                assert await scoped.require(Resource) is resource
            assert resource.active is True
        assert resource.active is False

    async def test_singleton_generator_resolver_created_in_scope_is_closed_with_root(
        self, make_injector: InjectorFactory
    ) -> None:
        """A yield-based singleton resolver first run inside a scope resumes with the root injector."""
        services = ServiceCollection()
        events: list[str] = []

        class Service:
            pass

        def service_resolver() -> Generator[Service]:
            events.append("started")
            yield Service()
            events.append("closed")

        services.add_singleton(service_resolver)

        async with make_injector(services) as root:
            async with root.get_scoped_injector() as scoped:
                service = await scoped.require(Service)
            assert events == ["started"]
            assert await root.require(Service) is service
        assert events == ["started", "closed"]

    async def test_scoped_context_manager_created_in_nested_scope_is_exited_with_its_scope(
        self, make_injector: InjectorFactory
    ) -> None:
        """A scoped service built in an inner scope is exited when that inner scope closes, not later."""
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

        services.add_scoped(Resource)

        async with make_injector(services).get_scoped_injector() as outer:
            async with outer.get_scoped_injector() as inner:
                inner_resource = await inner.require(Resource)
                assert inner_resource.active is True
            assert inner_resource.active is False
            outer_resource = await outer.require(Resource)
            assert outer_resource is not inner_resource
            assert outer_resource.active is True
        assert outer_resource.active is False

    async def test_transient_held_by_singleton_is_exited_with_root(self, make_injector: InjectorFactory) -> None:
        """A transient lives with the service that required it: held by a singleton, it is exited with root."""
        services = ServiceCollection()

        class Connection:
            def __init__(self) -> None:
                self.active = True

            def __enter__(self) -> "Connection":
                return self

            def __exit__(
                self,
                exc_type: type[BaseException],
                exc_value: BaseException | None,
                traceback: TracebackType | None,
            ) -> None:
                self.active = False

        class Cache:
            def __init__(self, connection: Connection) -> None:
                self.connection = connection

        services.add_transient(Connection)
        services.add_singleton(Cache)

        async with make_injector(services) as root:
            async with root.get_scoped_injector() as scoped:
                cache = await scoped.require(Cache)
            assert cache.connection.active is True
            assert await root.require(Cache) is cache
        assert cache.connection.active is False

    async def test_transient_chain_held_by_singleton_is_exited_with_root(self, make_injector: InjectorFactory) -> None:
        """Transients reached through other transients follow the singleton that ultimately holds them."""
        services = ServiceCollection()

        class Connection:
            def __init__(self) -> None:
                self.active = True

            def __enter__(self) -> "Connection":
                return self

            def __exit__(
                self,
                exc_type: type[BaseException],
                exc_value: BaseException | None,
                traceback: TracebackType | None,
            ) -> None:
                self.active = False

        class Channel:
            def __init__(self, connection: Connection) -> None:
                self.connection = connection

        class Cache:
            def __init__(self, channel: Channel) -> None:
                self.channel = channel

        services.add_transient(Connection)
        services.add_transient(Channel)
        services.add_singleton(Cache)

        async with make_injector(services) as root:
            async with root.get_scoped_injector() as scoped:
                cache = await scoped.require(Cache)
            assert cache.channel.connection.active is True
        assert cache.channel.connection.active is False

    async def test_transient_held_by_scoped_service_is_exited_with_scope(self, make_injector: InjectorFactory) -> None:
        """Held by a scoped service, a transient is exited with that scope."""
        services = ServiceCollection()

        class Connection:
            def __init__(self) -> None:
                self.active = True

            def __enter__(self) -> "Connection":
                return self

            def __exit__(
                self,
                exc_type: type[BaseException],
                exc_value: BaseException | None,
                traceback: TracebackType | None,
            ) -> None:
                self.active = False

        class Repository:
            def __init__(self, connection: Connection) -> None:
                self.connection = connection

        services.add_transient(Connection)
        services.add_scoped(Repository)

        async with make_injector(services) as root:
            async with root.get_scoped_injector() as scoped:
                repository = await scoped.require(Repository)
                assert repository.connection.active is True
            assert repository.connection.active is False

    async def test_transient_required_directly_is_exited_with_its_injector(
        self, make_injector: InjectorFactory
    ) -> None:
        """Required directly, a transient lives with the injector that built it."""
        services = ServiceCollection()

        class Connection:
            def __init__(self) -> None:
                self.active = True

            def __enter__(self) -> "Connection":
                return self

            def __exit__(
                self,
                exc_type: type[BaseException],
                exc_value: BaseException | None,
                traceback: TracebackType | None,
            ) -> None:
                self.active = False

        services.add_transient(Connection)

        async with make_injector(services) as root:
            async with root.get_scoped_injector() as scoped:
                from_scope = await scoped.require(Connection)
                assert from_scope.active is True
            assert from_scope.active is False
            from_root = await root.require(Connection)
            assert from_root.active is True
        assert from_root.active is False

    async def test_context_manager_services_are_exited_in_reverse_build_order(
        self, make_injector: InjectorFactory
    ) -> None:
        """Services are exited dependents first, in the reverse of the order they were built."""
        services = ServiceCollection()
        events: list[str] = []

        class Database:
            def __enter__(self) -> "Database":
                return self

            def __exit__(
                self,
                exc_type: type[BaseException],
                exc_value: BaseException | None,
                traceback: TracebackType | None,
            ) -> None:
                events.append("database")

        class Cache:
            def __enter__(self) -> "Cache":
                return self

            def __exit__(
                self,
                exc_type: type[BaseException],
                exc_value: BaseException | None,
                traceback: TracebackType | None,
            ) -> None:
                events.append("cache")

        class Repository:
            def __init__(self, database: Database, cache: Cache) -> None:
                self.database = database
                self.cache = cache

            def __enter__(self) -> "Repository":
                return self

            def __exit__(
                self,
                exc_type: type[BaseException],
                exc_value: BaseException | None,
                traceback: TracebackType | None,
            ) -> None:
                events.append("repository")

        services.add_scoped(Database)
        services.add_scoped(Cache)
        services.add_scoped(Repository)

        async with make_injector(services).get_scoped_injector() as injector:
            await injector.require(Repository)
            assert events == []
        assert events == ["repository", "cache", "database"]

    async def test_context_manager_services_are_all_exited_when_one_exit_fails(
        self, make_injector: InjectorFactory
    ) -> None:
        """A failing `__exit__` does not stop the other services from being exited, and still propagates."""
        services = ServiceCollection()
        events: list[str] = []

        class Database:
            def __enter__(self) -> "Database":
                return self

            def __exit__(
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
                raise RuntimeError("repository failed")

        services.add_scoped(Database)
        services.add_scoped(Repository)

        with pytest.raises(RuntimeError, match="repository failed"):
            async with make_injector(services).get_scoped_injector() as injector:
                await injector.require(Repository)
        assert events == ["database"]

    async def test_exception_in_scope_is_forwarded_to_context_manager_services(
        self, make_injector: InjectorFactory
    ) -> None:
        """An exception leaving the scope is passed to the services' `__exit__`, then propagates."""
        services = ServiceCollection()
        received: list[type[BaseException] | None] = []

        class Resource:
            def __enter__(self) -> "Resource":
                return self

            def __exit__(
                self,
                exc_type: type[BaseException] | None,
                exc_value: BaseException | None,
                traceback: TracebackType | None,
            ) -> None:
                received.append(exc_type)

        services.add_scoped(Resource)

        with pytest.raises(ValueError, match="boom"):
            async with make_injector(services).get_scoped_injector() as injector:
                await injector.require(Resource)
                raise ValueError("boom")
        assert received == [ValueError]


class TestServiceCollectionInjection:
    async def test_inject_list_of_services(self, make_injector: InjectorFactory) -> None:
        """Requiring `list[Interface]` collects every registered implementation."""
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

        async with make_injector(services) as injector:
            service_list = await injector.require(list[ServiceInterface])

        values = {service.get_value() for service in service_list}
        assert values == {"ServiceA", "ServiceB"}

    async def test_inject_list_of_generic_services(self, make_injector: InjectorFactory) -> None:
        """Requiring a list of a generic interface collects every specialization."""
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

        async with make_injector(services) as injector:
            service_list = await injector.require(list[ServiceInterface[Any]])

        values = {service.get_value() for service in service_list}
        assert values == {42, "Hello"}

    async def test_inject_dict_of_services(self, make_injector: InjectorFactory) -> None:
        """Requiring `dict[str, Interface]` keys each implementation by its type name."""
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

        async with make_injector(services) as injector:
            service_dict = await injector.require(dict[str, ServiceInterface])

        values = {service.get_value() for service in service_dict.values()}
        assert values == {"ServiceA", "ServiceB"}

        assert set(service_dict.keys()) == {ServiceA.__qualname__, ServiceB.__qualname__}


class TestCircularDependencies:
    async def test_fail_circular_dependency(self, make_injector: InjectorFactory) -> None:
        """Two services depending on each other report the cycle."""
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

        async with make_injector(services) as injector:
            with pytest.raises(CircularDependencyError) as exc_info:
                await injector.require(ServiceA)

        assert exc_info.value.trace == [wrap_type(ServiceA), wrap_type(ServiceB), wrap_type(ServiceA)]

    async def test_fail_circular_dependency_3_services(self, make_injector: InjectorFactory) -> None:
        """A three-service cycle is reported with the full trace."""
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

        async with make_injector(services) as injector:
            with pytest.raises(CircularDependencyError) as exc_info:
                await injector.require(ServiceA)

        assert exc_info.value.trace == [
            wrap_type(ServiceA),
            wrap_type(ServiceB),
            wrap_type(ServiceC),
            wrap_type(ServiceA),
        ]

    async def test_fail_circular_dependency_in_post_init(self, make_injector: InjectorFactory) -> None:
        """A cycle opened by a `post_init` hook lists the hook in the trace."""
        services = ServiceCollection()

        class ServiceA:
            def __init__(self) -> None:
                self.resource: str | None = None

            @post_init
            def setup(self, service_b: "ServiceB") -> None:
                self.resource = service_b.fetch_data()

        class ServiceB:
            def __init__(self, service_a: ServiceA) -> None:
                self.service_a = service_a

            def fetch_data(self) -> str:
                return "Data"

        add_type_to_type_globals(ServiceA, ServiceB)

        services.add_singleton(ServiceA)
        services.add_singleton(ServiceB)

        async with make_injector(services) as injector:
            with pytest.raises(CircularDependencyError) as exc_info:
                await injector.require(ServiceA)

        assert exc_info.value.trace == [wrap_type(ServiceA), ServiceA.setup, wrap_type(ServiceB), wrap_type(ServiceA)]

    async def test_variadic_parameter_does_not_create_a_cycle(self, make_injector: InjectorFactory) -> None:
        """A dependency edge that exists only through a variadic parameter is not a cycle."""
        services = ServiceCollection()

        class ServiceA:
            def __init__(self, *service_b: "ServiceB") -> None:
                self.service_b = service_b

        class ServiceB:
            def __init__(self, service_a: ServiceA) -> None:
                self.service_a = service_a

        add_type_to_type_globals(ServiceA, ServiceB)

        services.add_singleton(ServiceA)
        services.add_singleton(ServiceB)

        async with make_injector(services) as injector:
            service_b = await injector.require(ServiceB)

        assert service_b.service_a.service_b == ()


class TestGenericCircularDependencies:
    async def test_generic_service_specialized_twice_is_not_a_cycle(self, make_injector: InjectorFactory) -> None:
        """Two specializations of one generic class on a single path share an `__init__` but are not a cycle."""
        services = ServiceCollection()

        class Repository[T]:
            def __init__(self, item: T) -> None:
                self.item = item

        class Leaf:
            pass

        class Node:
            def __init__(self, repository: Repository[Leaf]) -> None:
                self.repository = repository

        services.add_singleton(Repository[Leaf])
        services.add_singleton(Repository[Node])
        services.add_singleton(Leaf)
        services.add_singleton(Node)

        async with make_injector(services) as injector:
            repository = await injector.require(Repository[Node])

        assert isinstance(repository.item, Node)
        assert isinstance(repository.item.repository.item, Leaf)

    async def test_generic_resolver_specialized_twice_is_not_a_cycle(self, make_injector: InjectorFactory) -> None:
        """Same, when the specializations come from one generic resolver function."""
        services = ServiceCollection()

        class Repository[T]:
            def __init__(self, item: T) -> None:
                self.item = item

        class Leaf:
            pass

        class Node:
            def __init__(self, repository: Repository[Leaf]) -> None:
                self.repository = repository

        def repository_resolver[T](item: T) -> Repository[T]:
            return Repository(item)

        services.add_singleton(repository_resolver)
        services.add_singleton(Leaf)
        services.add_singleton(Node)

        async with make_injector(services) as injector:
            repository = await injector.require(Repository[Node])

        assert isinstance(repository.item, Node)
        assert isinstance(repository.item.repository.item, Leaf)

    async def test_fail_circular_dependency_through_generic_specializations(
        self, make_injector: InjectorFactory
    ) -> None:
        """A real cycle running through two specializations is still reported, with the specializations in the trace."""
        services = ServiceCollection()

        class Repository[T]:
            def __init__(self, item: T) -> None:
                self.item = item

        class ServiceA:
            def __init__(self, repository: "Repository[ServiceB]") -> None:
                self.repository = repository

        class ServiceB:
            def __init__(self, repository: Repository[ServiceA]) -> None:
                self.repository = repository

        add_type_to_type_globals(ServiceA, Repository)
        add_type_to_type_globals(ServiceA, ServiceB)

        services.add_singleton(Repository[ServiceA])
        services.add_singleton(Repository[ServiceB])
        services.add_singleton(ServiceA)
        services.add_singleton(ServiceB)

        async with make_injector(services) as injector:
            with pytest.raises(CircularDependencyError) as exc_info:
                await injector.require(Repository[ServiceA])

        assert exc_info.value.trace == [
            wrap_type(Repository[ServiceA]),
            wrap_type(ServiceA),
            wrap_type(Repository[ServiceB]),
            wrap_type(ServiceB),
            wrap_type(Repository[ServiceA]),
        ]


class TestStoredInstances:
    async def test_transient_registration_ignores_singleton_instance_of_same_implementation(
        self, make_injector: InjectorFactory
    ) -> None:
        """A transient stays transient even if its implementation is stored under another interface."""
        services = ServiceCollection()

        class Interface:
            pass

        class Implementation(Interface):
            pass

        services.add_singleton(Interface, Implementation)
        services.add_transient(Implementation)

        async with make_injector(services) as injector:
            singleton = await injector.require(Interface)
            assert await injector.require(Interface) is singleton
            first = await injector.require(Implementation)
            second = await injector.require(Implementation)

        assert first is not singleton
        assert second is not singleton
        assert first is not second


class TestInjectorRequirements:
    async def test_require_injector_protocol(self, make_injector: InjectorFactory) -> None:
        """A service can depend on the `Injector` protocol and gets the running injector."""

        class Service:
            def __init__(self, injector: Injector) -> None:
                self.injector = injector

        services = ServiceCollection()
        services.add_singleton(Service)

        async with make_injector(services) as injector:
            service = await injector.require(Service)
            assert service.injector is injector.injector

    async def test_require_service_collection(self, make_injector: InjectorFactory) -> None:
        """An injected `ServiceCollection` is a copy owned by the injector."""

        class Service:
            def __init__(self, services: ServiceCollection) -> None:
                self.services = services

        services = ServiceCollection()
        services.add_singleton(Service)

        async with make_injector(services) as injector:
            service = await injector.require(Service)
            assert isinstance(service.services, ServiceCollection)
            assert service.services is not services
            assert all(service.services.is_registered(rtype) for rtype in services.registered_types)
            assert not all(services.is_registered(rtype) for rtype in service.services.registered_types)

    async def test_require_resolve_context(self, make_injector: InjectorFactory) -> None:
        """An injected `ResolutionContext` describes the service receiving it and how it was requested."""
        services = ServiceCollection()

        class Service1:
            def __init__(self, ctx: ResolutionContext) -> None:
                self.ctx = ctx

        class Service2:
            def __init__(self, s1: Service1, ctx: ResolutionContext) -> None:
                self.s1 = s1
                self.ctx = ctx

        services.add_scoped(Service1)
        services.add_transient(Service2)

        async with make_injector(services).get_scoped_injector() as injector:
            s2 = await injector.require(Service2)
            assert s2.ctx.injector is injector.injector
            assert s2.ctx.required == wrap_type(Service2)
            assert s2.ctx.scope is InjectionScope.TRANSIENT
            assert s2.ctx.caller_context is None
            assert s2.s1.ctx.required == wrap_type(Service1)
            assert s2.s1.ctx.scope is InjectionScope.SCOPED
            assert s2.s1.ctx.caller_context is not None
            assert s2.s1.ctx.caller_context.param_name == "s1"
            assert s2.s1.ctx.caller_context.caller.func is Service2.__init__

    async def test_require_caller_context(self, make_injector: InjectorFactory) -> None:
        """An injected `CallerContext` names the parameter and constructor that asked for the service."""
        services = ServiceCollection()

        class Logger:
            def __init__(self, caller: CallerContext) -> None:
                self.caller = caller

        class Service:
            def __init__(self, logger: Logger) -> None:
                self.logger = logger

        services.add_transient(Logger)
        services.add_singleton(Service)

        async with make_injector(services) as injector:
            service = await injector.require(Service)

        assert service.logger.caller.param_name == "logger"
        assert service.logger.caller.caller.func is Service.__init__

    async def test_fail_require_caller_context_directly(self, make_injector: InjectorFactory) -> None:
        """A service needing a `CallerContext` cannot be required directly, nobody asked for it."""
        services = ServiceCollection()

        class Logger:
            def __init__(self, caller: CallerContext) -> None:
                self.caller = caller

        services.add_transient(Logger)

        async with make_injector(services) as injector:
            with pytest.raises(CallerContextNotAvailableError) as exc_info:
                await injector.require(Logger)

        assert exc_info.value.code == "soupape.caller_context.not_available"
        assert exc_info.value.service == Logger.__qualname__


class TestDependsOn:
    async def test_require_service_type_with_depends_on(self, make_injector: InjectorFactory) -> None:
        """A `depends_on` registerer runs before the service it declares is required."""

        class Service:
            def hello(self) -> str:
                return "hello"

        class Registerer:
            @post_init
            def _register_service(self, injector: Injector) -> None:
                injector.services.add_singleton(Service)

        depends_on(Service, Registerer)

        services = ServiceCollection()
        services.add_singleton(Registerer)

        async with make_injector(services) as injector:
            assert not injector.services.is_registered(Service)
            service = await injector.require(Service)
            assert service.hello() == "hello"
            assert injector.services.is_registered(Service)

    async def test_require_generic_service_type_with_depends_on(self, make_injector: InjectorFactory) -> None:
        """Same, for a generic service required by specialization."""

        class Service[T]:
            def __init__(self, t: type[T]) -> None:
                self.t = t

            def hello(self) -> type[T]:
                return self.t

        class Registerer:
            @post_init
            def _register_service(self, injector: Injector) -> None:
                injector.services.add_singleton(Service)

        depends_on(Service, Registerer)

        services = ServiceCollection()
        services.add_singleton(Registerer)

        async with make_injector(services) as injector:
            assert not injector.services.is_registered(Service)
            service = await injector.require(Service[int])
            assert service.hello() is int
            assert injector.services.is_registered(Service)

    async def test_require_service_type_with_depends_on_decorator(self, make_injector: InjectorFactory) -> None:
        """The decorator form of `depends_on` declares the same dependency as the call form."""

        class Registerer:
            @post_init
            def _register_service(self, injector: Injector) -> None:
                injector.services.add_singleton(Service)

        @depends_on(Registerer)
        class Service:
            def hello(self) -> str:
                return "hello"

        services = ServiceCollection()
        services.add_singleton(Registerer)

        async with make_injector(services) as injector:
            assert not injector.services.is_registered(Service)
            service = await injector.require(Service)
            assert service.hello() == "hello"

    async def test_require_service_type_with_two_depends_on(self, make_injector: InjectorFactory) -> None:
        """Two dependencies declared on one service both run before it is required."""

        class Value:
            def get(self) -> int:
                return 42

        class Service:
            def __init__(self, value: Value) -> None:
                self.value = value

        class ValueRegisterer:
            @post_init
            def _register_value(self, injector: Injector) -> None:
                injector.services.add_singleton(Value)

        class ServiceRegisterer:
            @post_init
            def _register_service(self, injector: Injector) -> None:
                injector.services.add_singleton(Service)

        depends_on(Service, ValueRegisterer)
        depends_on(Service, ServiceRegisterer)

        services = ServiceCollection()
        services.add_singleton(ValueRegisterer)
        services.add_singleton(ServiceRegisterer)

        async with make_injector(services) as injector:
            service = await injector.require(Service)
            assert service.value.get() == 42

    async def test_fail_depends_on_cycle(self, make_injector: InjectorFactory) -> None:
        """Two services declaring `depends_on` each other is reported as a cycle, not a recursion error."""

        class ServiceA:
            pass

        class ServiceB:
            pass

        depends_on(ServiceA, ServiceB)
        depends_on(ServiceB, ServiceA)

        services = ServiceCollection()
        services.add_singleton(ServiceA)
        services.add_singleton(ServiceB)

        async with make_injector(services) as injector:
            with pytest.raises(CircularDependencyError) as exc_info:
                await injector.require(ServiceA)

        assert exc_info.value.code == "soupape.dependency.circular"
        assert exc_info.value.trace == [wrap_type(ServiceA), wrap_type(ServiceB), wrap_type(ServiceA)]

    async def test_fail_depends_on_self(self, make_injector: InjectorFactory) -> None:
        """A service declaring `depends_on` itself is reported as a cycle."""

        class Service:
            pass

        depends_on(Service, Service)

        services = ServiceCollection()
        services.add_singleton(Service)

        async with make_injector(services) as injector:
            with pytest.raises(CircularDependencyError) as exc_info:
                await injector.require(Service)

        assert exc_info.value.trace == [wrap_type(Service), wrap_type(Service)]

    async def test_depends_on_shared_between_siblings_is_not_a_cycle(self, make_injector: InjectorFactory) -> None:
        """A dependency reached through two `depends_on` branches is not mistaken for a cycle."""

        class Shared:
            pass

        class Left:
            pass

        class Right:
            pass

        class Root:
            pass

        depends_on(Left, Shared)
        depends_on(Root, Left)
        depends_on(Root, Right)
        depends_on(Root, Shared)

        services = ServiceCollection()
        for service_type in (Shared, Left, Right, Root):
            services.add_singleton(service_type)

        async with make_injector(services) as injector:
            root = await injector.require(Root)

        assert isinstance(root, Root)

    async def test_fail_depends_on_without_arguments(self) -> None:
        """`depends_on` rejects a call that names neither a dependent nor a dependency."""
        with pytest.raises(TypeError, match="Unknown parameters"):
            depends_on()  # pyright: ignore[reportCallIssue]


class TestCustomResolvers:
    async def test_custom_resolver_for_class_service(self, make_injector: InjectorFactory) -> None:
        """A custom `ServiceResolver` builds a class from resolver-provided arguments."""

        class CommandRunArgs:
            def __init__(self, numbers: Sequence[int]) -> None:
                self.number = numbers

        class CustomArgResolver(ServiceResolver[..., Any]):
            def __init__(self, name: str, position: int) -> None:
                super().__init__()
                self.arg_name = name
                self.position = position
                self.func = self._build_new_signature()

            @staticmethod
            def _build_new_signature() -> FWrap[..., Any]:
                def _new_func(run_args: CommandRunArgs): ...

                return wrap_func(_new_func)

            @property
            @override
            def name(self) -> str:
                return f"Argument-{self.arg_name}-{self.position}"

            @property
            @override
            def scope(self) -> InjectionScope:
                return InjectionScope.SINGLETON

            @override
            def get_resolution_hints(self, context: ResolutionContext) -> dict[str, TWrap[Any]]:
                return {"run_args": wrap_type(CommandRunArgs)}

            @override
            def get_instance_function(self) -> FWrap[..., Any]:
                return self.func

            @override
            def get_resolution_signature(self) -> inspect.Signature:
                return self.func.signature

            @override
            def get_resolution_func(self, context: ResolutionContext) -> ResolutionFunction[..., Any]:
                def resolve(run_args: CommandRunArgs) -> Any:
                    return run_args.number[self.position]

                return resolve

        class CustomCommandResolver(ServiceResolver[..., Any]):
            def __init__(self, cls: type[Any]) -> None:
                super().__init__()
                self.twrap = wrap_type(cls)
                self.func = wrap_func(cls)

            @property
            @override
            def name(self) -> str:
                return str(self.twrap)

            @property
            @override
            def scope(self) -> InjectionScope:
                return InjectionScope.SINGLETON

            @override
            def get_resolution_hints(self, context: ResolutionContext) -> dict[str, ServiceResolver[..., Any]]:
                return {a: CustomArgResolver(a, i) for i, a in enumerate(self.func.parameters)}

            @override
            def get_instance_function(self) -> FWrap[..., Any]:
                return self.func

            @override
            def get_resolution_signature(self) -> inspect.Signature:
                return self.func.signature

            @override
            def get_resolution_func(self, context: ResolutionContext) -> ResolutionFunction[..., Any]:
                def resolve(*args: Any, **kwargs: Any) -> Any:
                    return self.twrap.instantiate(*args, **kwargs)

                return resolve

        class CustomIntCommand:
            def __init__(self, a: int, b: int) -> None:
                self.a = a
                self.b = b

            def compute(self) -> int:
                return self.a + self.b

        resolver(CustomIntCommand, CustomCommandResolver(CustomIntCommand))

        services = ServiceCollection()

        services.add_scoped(CommandRunArgs, lambda: CommandRunArgs([2, 3]))

        async with make_injector(services).get_scoped_injector() as injector:
            command = await injector.require(CustomIntCommand)
            assert command.compute() == 5

    async def test_custom_resolver_for_function(self, make_injector: InjectorFactory) -> None:
        """A custom `ServiceResolver` supplies the arguments of a called function."""

        class CommandRunArgs:
            def __init__(self, numbers: Sequence[int]) -> None:
                self.number = numbers

        class CustomArgResolver(ServiceResolver[..., Any]):
            def __init__(self, name: str, position: int) -> None:
                super().__init__()
                self.arg_name = name
                self.position = position
                self.func = self._build_new_signature()

            @staticmethod
            def _build_new_signature() -> FWrap[..., Any]:
                def _new_func(run_args: CommandRunArgs): ...

                return wrap_func(_new_func)

            @property
            @override
            def name(self) -> str:
                return f"Argument-{self.arg_name}-{self.position}"

            @property
            @override
            def scope(self) -> InjectionScope:
                return InjectionScope.SINGLETON

            @override
            def get_resolution_hints(self, context: ResolutionContext) -> dict[str, TWrap[Any]]:
                return {"run_args": wrap_type(CommandRunArgs)}

            @override
            def get_instance_function(self) -> FWrap[..., Any]:
                return self.func

            @override
            def get_resolution_signature(self) -> inspect.Signature:
                return self.func.signature

            @override
            def get_resolution_func(self, context: ResolutionContext) -> ResolutionFunction[..., Any]:
                def resolve(run_args: CommandRunArgs) -> Any:
                    return run_args.number[self.position]

                return resolve

        class CustomCommandResolver(ServiceResolver[..., Any]):
            def __init__(self, func: Callable[..., Any]) -> None:
                super().__init__()
                self.func = wrap_func(func)

            @property
            @override
            def name(self) -> str:
                return str(self.func)

            @property
            @override
            def scope(self) -> InjectionScope:
                return InjectionScope.SINGLETON

            @override
            def get_resolution_hints(self, context: ResolutionContext) -> dict[str, ServiceResolver[..., Any]]:
                return {a: CustomArgResolver(a, i) for i, a in enumerate(self.func.parameters)}

            @override
            def get_instance_function(self) -> FWrap[..., Any]:
                return self.func

            @override
            def get_resolution_signature(self) -> inspect.Signature:
                return self.func.signature

            @override
            def get_resolution_func(self, context: ResolutionContext) -> ResolutionFunction[..., Any]:
                def resolve(*args: Any, **kwargs: Any) -> Any:
                    return self.func(*args, **kwargs)

                return resolve

        def custom_int_command(a: int, b: int) -> int:
            return a + b

        resolver(custom_int_command, CustomCommandResolver(custom_int_command))

        services = ServiceCollection()

        services.add_scoped(CommandRunArgs, lambda: CommandRunArgs([2, 3]))

        async with make_injector(services).get_scoped_injector() as injector:
            result = await injector.call(custom_int_command)
            assert result == 5

    async def test_custom_resolver_from_decorator(self, make_injector: InjectorFactory) -> None:
        """The decorator form of `resolver` attaches a custom resolver to the class it decorates."""

        @resolver(MinimalResolver())
        class Command:
            def __init__(self, value: int) -> None:
                self.value = value

        services = ServiceCollection()

        async with make_injector(services) as injector:
            command = await injector.require(Command)
            assert command.value == 42

    async def test_custom_resolver_on_generic_class(self, make_injector: InjectorFactory) -> None:
        """A custom resolver on a generic class is found when a specialization is required."""
        custom = MinimalResolver()

        @resolver(custom)
        class Service[T]:
            def __init__(self, value: int) -> None:
                self.value = value

        services = ServiceCollection()

        async with make_injector(services) as injector:
            service = await injector.require(Service[int])
            assert isinstance(service, Service)
            assert service.value == 42

        assert custom.required_types == [wrap_type(Service[int])]

    async def test_fail_resolver_without_arguments(self) -> None:
        """`resolver` rejects a call that names neither a resolvable nor a resolver."""
        with pytest.raises(TypeError, match="Unknown parameters"):
            resolver()  # pyright: ignore[reportCallIssue]


class TestAnnotatedResolvers:
    async def test_annotated_resolver_from_class(self, make_injector: InjectorFactory) -> None:
        """An `Annotated` marker with `__resolve__` builds the constructor parameter."""
        services = ServiceCollection()

        class Database:
            def data(self) -> int:
                return 42

        class Service1:
            def __init__(self, value: int) -> None:
                self.value = value

        class Service1Resolver:
            def __resolve__(self, db: Database) -> Service1:
                return Service1(db.data())

        class Service2:
            def __init__(self, s1: Annotated[Service1, Service1Resolver()]) -> None:
                self.s1 = s1

        services.add_singleton(Database)
        services.add_scoped(Service1)
        services.add_scoped(Service2)

        async with make_injector(services).get_scoped_injector() as injector:
            s2 = await injector.require(Service2)
            assert s2.s1.value == 42

    async def test_annotated_resolver_from_function(self, make_injector: InjectorFactory) -> None:
        """An `Annotated` marker with `__resolve__` builds a called function's parameter."""
        services = ServiceCollection()

        class Database:
            def data(self) -> int:
                return 42

        class Service:
            def __init__(self, value: int) -> None:
                self.value = value

        class TestServiceResolver:
            def __resolve__(self, db: Database) -> Service:
                return Service(db.data())

        def call_service(service: Annotated[Service, TestServiceResolver()]) -> int:
            return service.value + 1

        services.add_singleton(Database)
        services.add_scoped(Service)

        async with make_injector(services).get_scoped_injector() as injector:
            result = await injector.call(call_service)
            assert result == 43

    async def test_annotated_resolver_of_random_class(self, make_injector: InjectorFactory) -> None:
        """`annotation_resolver` attaches a resolver to a marker with no `__resolve__`."""
        services = ServiceCollection()

        class Database:
            def data(self) -> int:
                return 42

        class Service1:
            def __init__(self, value: int) -> None:
                self.value = value

        class RandomAnnotation: ...

        def resolve_service(_self: RandomAnnotation, db: Database) -> Service1:
            return Service1(db.data())

        class Service2:
            def __init__(self, s1: Annotated[Service1, RandomAnnotation()]) -> None:
                self.s1 = s1

        services.add_singleton(Database)
        services.add_scoped(Service1)
        services.add_scoped(Service2)
        annotation_resolver(RandomAnnotation, resolve_service)

        async with make_injector(services).get_scoped_injector() as injector:
            s2 = await injector.require(Service2)
            assert s2.s1.value == 42

    async def test_annotation_resolver_decorator(self, make_injector: InjectorFactory) -> None:
        """`annotation_resolver` also works as a decorator on the resolution function."""
        services = ServiceCollection()

        class Database:
            def data(self) -> int:
                return 42

        class Service1:
            def __init__(self, value: int) -> None:
                self.value = value

        class RandomAnnotation: ...

        @annotation_resolver(RandomAnnotation)
        def resolve_service(_self: RandomAnnotation, db: Database) -> Service1:
            return Service1(db.data())

        class Service2:
            def __init__(self, s1: Annotated[Service1, RandomAnnotation()]) -> None:
                self.s1 = s1

        services.add_singleton(Database)
        services.add_scoped(Service1)
        services.add_scoped(Service2)

        async with make_injector(services).get_scoped_injector() as injector:
            s2 = await injector.require(Service2)
            assert s2.s1.value == 42
        assert resolve_service(RandomAnnotation(), Database()).value == 42

    async def test_fail_annotation_resolver_without_arguments(self) -> None:
        """`annotation_resolver` rejects a call that names no annotation class."""
        with pytest.raises(TypeError, match="Unknown parameters"):
            annotation_resolver()  # pyright: ignore[reportCallIssue]


class TestErrors:
    async def test_fail_store_service_registered_with_any(self, make_injector: InjectorFactory) -> None:
        """A stored service whose type still contains `Any` at resolution cannot be kept."""
        services = ServiceCollection()

        class Box[T]:
            def __init__(self) -> None:
                pass

        services.add_singleton(Box[Any])

        async with make_injector(services) as injector:
            with pytest.raises(UnresolvedAnyTypeError) as exc_info:
                await injector.require(Box[Any])

        assert exc_info.value.code == "soupape.type.unresolved_any"
        assert exc_info.value.interface == f"{Box.__qualname__}[Any]"

    async def test_fail_service_not_found(self, make_injector: InjectorFactory) -> None:
        """Requiring a service from an empty collection fails."""
        services = ServiceCollection()

        class TestService:
            def __init__(self) -> None:
                pass

            def greet(self) -> str:
                return "Hello, World!"

        async with make_injector(services) as injector:
            with pytest.raises(ServiceNotFoundError):
                await injector.require(TestService)

    async def test_fail_generic_service_not_found(self, make_injector: InjectorFactory) -> None:
        """Requiring a specialization that was not registered fails."""

        class Service[T]: ...

        services = ServiceCollection()
        services.add_singleton(Service[int])

        async with make_injector(services) as injector:
            with pytest.raises(ServiceNotFoundError):
                await injector.require(Service[str])

    async def test_fail_inject_unregistered_service(self, make_injector: InjectorFactory) -> None:
        """Requiring a service that was never registered fails."""
        services = ServiceCollection()

        class UnregisteredService:
            def __init__(self) -> None:
                pass

        async with make_injector(services) as injector:
            with pytest.raises(ServiceNotFoundError):
                await injector.require(UnregisteredService)

    async def test_fail_inject_unregistered_service_in_dependency(self, make_injector: InjectorFactory) -> None:
        """A missing dependency of a registered service fails."""
        services = ServiceCollection()

        class UnregisteredService:
            def __init__(self) -> None:
                pass

        class DependentService:
            def __init__(self, unreg_service: UnregisteredService) -> None:
                self.unreg_service = unreg_service

        services.add_singleton(DependentService)

        async with make_injector(services) as injector:
            with pytest.raises(ServiceNotFoundError):
                await injector.require(DependentService)

    async def test_fail_missing_type_hint_in_dependency(self, make_injector: InjectorFactory) -> None:
        """An unannotated constructor parameter fails, naming the parameter."""
        services = ServiceCollection()

        class DependencyService:
            def __init__(self) -> None:
                pass

        class ServiceWithoutTypeHint:
            def __init__(
                self,
                dep_service,  # pyright: ignore[reportMissingParameterType, reportUnknownParameterType]
            ) -> None:
                self.dep_service = dep_service

        services.add_singleton(DependencyService)
        services.add_singleton(ServiceWithoutTypeHint)

        async with make_injector(services) as injector:
            with pytest.raises(MissingTypeHintError) as exc_info:
                await injector.require(ServiceWithoutTypeHint)

        assert exc_info.value.code == "soupape.type_hint.missing"
        assert exc_info.value.message == (
            f"Missing type hint for parameter 'dep_service' of '{ServiceWithoutTypeHint.__qualname__}.__init__'."
        )

    async def test_fail_missing_type_hint_in_function_call(self, make_injector: InjectorFactory) -> None:
        """An unannotated parameter of a called function fails, naming the parameter."""
        services = ServiceCollection()

        class DependencyService:
            def __init__(self) -> None:
                pass

        services.add_singleton(DependencyService)

        async with make_injector(services) as injector:

            def function_without_type_hint(
                dep_service,  # pyright: ignore[reportMissingParameterType, reportUnknownParameterType]
            ) -> None: ...

            with pytest.raises(MissingTypeHintError) as exc_info:
                await injector.call(function_without_type_hint)  # pyright: ignore[reportUnknownArgumentType]

        assert exc_info.value.code == "soupape.type_hint.missing"
        assert exc_info.value.message == (
            f"Missing type hint for parameter 'dep_service' of '{function_without_type_hint.__qualname__}'."
        )

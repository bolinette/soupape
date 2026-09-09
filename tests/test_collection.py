from collections.abc import Callable
from typing import Any

import pytest
from escondite import Cache
from peritype import wrap_func

from soupape import ServiceCollection, injectable
from soupape._decorators._injectable import Injectable, InjectableContainer
from soupape._resolvers import FunctionResolver
from soupape.errors import (
    AmbiguousServiceMatchError,
    IncompatibleInterfaceError,
    InvalidResolverReturnHintError,
    MissingInterfaceError,
    ServiceAlreadyRegisteredError,
    ServiceNotFoundError,
    UnknownInjectionScopeError,
)
from soupape.extension import InjectionScope


class TestRegistration:
    def test_service_registration(self) -> None:
        """Registering under an interface makes the interface resolvable, not the implementation."""
        services = ServiceCollection()

        class BaseService:
            pass

        class Service1(BaseService):
            pass

        class Service2(BaseService):
            pass

        class Service3(BaseService):
            pass

        def resolver() -> Service3: ...

        services.add_singleton(Service1)
        services.add_singleton(BaseService, Service2)
        services.add_singleton(resolver)

        assert services.is_registered(BaseService)
        assert services.is_registered(Service1)
        assert not services.is_registered(Service2)
        assert services.is_registered(Service3)

    def test_lambda_resolver(self) -> None:
        """A lambda registered against an explicit interface is accepted."""
        services = ServiceCollection()

        class Service:
            pass

        services.add_singleton(Service, lambda: Service())

        assert services.is_registered(Service)

    def test_callable_object_resolver(self) -> None:
        """An instance with a `__call__` is accepted as a resolver, and its return hint is read."""
        services = ServiceCollection()

        class Service: ...

        class Builder:
            def __call__(self) -> Service:
                return Service()

        services.add_singleton(Builder())

        assert services.is_registered(Service)


class TestCollectionCopies:
    def test_copy_collection(self) -> None:
        """A copy keeps existing registrations and does not leak new ones back."""
        services = ServiceCollection()

        class Service: ...

        services.add_singleton(Service)
        copied = services.copy()

        assert copied.is_registered(Service)

        class AnotherService: ...

        copied.add_singleton(AnotherService)

        assert not services.is_registered(AnotherService)
        assert copied.is_registered(AnotherService)

    def test_merge_collections(self) -> None:
        """Merging unions two collections without touching either original."""
        services1 = ServiceCollection()
        services2 = ServiceCollection()

        class Service1: ...

        class Service2: ...

        services1.add_singleton(Service1)
        services2.add_singleton(Service2)

        assert services1.is_registered(Service1)
        assert not services1.is_registered(Service2)
        assert services2.is_registered(Service2)
        assert not services2.is_registered(Service1)

        merged = services1 | services2

        assert merged.is_registered(Service1)
        assert merged.is_registered(Service2)

        class Service3: ...

        merged.add_singleton(Service3)

        assert not services1.is_registered(Service3)
        assert not services2.is_registered(Service3)
        assert merged.is_registered(Service3)


class TestGetResolver:
    def test_get_resolver_by_type(self) -> None:
        """`get_resolver` accepts a plain type and returns the resolver it was registered with."""
        services = ServiceCollection()

        class Service: ...

        services.add_scoped(Service)

        assert services.get_resolver(Service).scope is InjectionScope.SCOPED

    def test_fail_get_resolver_not_registered(self) -> None:
        """`get_resolver` on an unregistered type fails."""
        services = ServiceCollection()

        class Service: ...

        with pytest.raises(ServiceNotFoundError):
            services.get_resolver(Service)

    def test_get_resolver_by_catch_all_match(self) -> None:
        """`get_resolver` falls back to the single registration that matches the requested type."""
        services = ServiceCollection()

        class Service[T]: ...

        services.add_scoped(Service[Any])

        assert services.get_resolver(Service[int]).scope is InjectionScope.SCOPED

    def test_fail_get_resolver_ambiguous_match(self) -> None:
        """`get_resolver` fails when several registrations match the requested type equally well."""
        services = ServiceCollection()

        class Service[K, V]: ...

        services.add_singleton(Service[Any, str])
        services.add_singleton(Service[str, Any])

        with pytest.raises(AmbiguousServiceMatchError) as exc_info:
            services.get_resolver(Service[str, str])

        assert exc_info.value.code == "soupape.service.ambiguous_match"


class TestInjectableDecorator:
    def test_add_singleton_from_cache(self) -> None:
        """`add_from_cache` registers a class marked `@injectable.singleton` as a singleton."""
        cache = Cache()
        services = ServiceCollection()

        @injectable.singleton(cache=cache)
        class Service: ...

        services.add_from_cache(cache)

        assert services.get_resolver(Service).scope is InjectionScope.SINGLETON

    def test_add_scoped_from_cache(self) -> None:
        """`add_from_cache` registers a class marked `@injectable.scoped` as scoped."""
        cache = Cache()
        services = ServiceCollection()

        @injectable.scoped(cache=cache)
        class Service: ...

        services.add_from_cache(cache)

        assert services.get_resolver(Service).scope is InjectionScope.SCOPED

    def test_add_transient_from_cache(self) -> None:
        """`add_from_cache` registers a class marked `@injectable.transient` as transient."""
        cache = Cache()
        services = ServiceCollection()

        @injectable.transient(cache=cache)
        class Service: ...

        services.add_from_cache(cache)

        assert services.get_resolver(Service).scope is InjectionScope.TRANSIENT

    @pytest.mark.parametrize(
        ("mark", "scope"),
        [
            (injectable.singleton, InjectionScope.SINGLETON),
            (injectable.scoped, InjectionScope.SCOPED),
            (injectable.transient, InjectionScope.TRANSIENT),
        ],
        ids=["singleton", "scoped", "transient"],
    )
    def test_mark_injectable_by_direct_call(
        self,
        mark: Callable[..., Any],
        scope: InjectionScope,
    ) -> None:
        """Passing the class positionally marks it without decorator syntax, and returns it unchanged."""
        cache = Cache()
        services = ServiceCollection()

        class Service: ...

        assert mark(Service, cache=cache) is Service

        services.add_from_cache(cache)

        assert services.get_resolver(Service).scope is scope

    def test_add_from_cache_ignores_cache_without_injectables(self) -> None:
        """A cache holding no injectables registers nothing."""
        services = ServiceCollection()

        services.add_from_cache(Cache())

        assert next(services.registered_types, None) is None

    def test_fail_add_from_cache_with_unknown_scope(self) -> None:
        """A cached injectable with a scope that cannot be registered fails."""
        cache = Cache()
        services = ServiceCollection()

        class Service: ...

        cache.add(Injectable.CACHE_KEY, InjectableContainer(InjectionScope.IMMEDIATE, Service))

        with pytest.raises(UnknownInjectionScopeError) as exc_info:
            services.add_from_cache(cache)

        assert exc_info.value.code == "soupape.scope.unknown"
        assert exc_info.value.scope is InjectionScope.IMMEDIATE


class TestRegistrationErrors:
    def test_fail_register_incompatible_interface(self) -> None:
        """Registering an implementation that does not subclass the interface fails."""
        services = ServiceCollection()

        class BaseService: ...

        class Subservice: ...

        with pytest.raises(IncompatibleInterfaceError) as exc_info:
            services.add_singleton(BaseService, Subservice)

        assert exc_info.value.interface == BaseService.__qualname__
        assert exc_info.value.implementation == Subservice.__qualname__

    def test_fail_lambda_resolver_no_interface(self) -> None:
        """A lambda with no return annotation and no interface fails."""
        services = ServiceCollection()

        class Service:
            pass

        with pytest.raises(MissingInterfaceError) as exc_info:
            services.add_singleton(lambda: Service())

        assert exc_info.value.code == "soupape.interface.missing"
        assert exc_info.value.message == (
            f"Interface missing for resolver '{self.test_fail_lambda_resolver_no_interface.__qualname__}"
            ".<locals>.<lambda>': no return type hint or required type."
        )

    def test_fail_register_same_interface_twice(self) -> None:
        """Registering the same interface a second time fails."""
        services = ServiceCollection()

        class Service: ...

        services.add_singleton(Service)

        with pytest.raises(ServiceAlreadyRegisteredError) as exc_info:
            services.add_singleton(Service)

        assert exc_info.value.code == "soupape.service.already_registered"
        assert exc_info.value.interface == Service.__qualname__
        assert exc_info.value.message == f"Service for interface '{Service.__qualname__}' is already registered."

    def test_fail_add_resolver_without_required_type(self) -> None:
        """`add_resolver` rejects a resolver that declares no required type."""
        services = ServiceCollection()

        class Service: ...

        def service_resolver() -> Service:
            return Service()

        resolver = FunctionResolver(InjectionScope.SINGLETON, wrap_func(service_resolver))

        with pytest.raises(MissingInterfaceError) as exc_info:
            services.add_resolver(resolver)

        assert exc_info.value.resolver == resolver.name

    def test_fail_register_unsupported_arguments(self) -> None:
        """An argument that is neither a type nor a callable fails."""
        services = ServiceCollection()

        with pytest.raises(TypeError, match=r"Cannot register a service from arguments \(42,\)"):
            services.add_singleton(42)  # pyright: ignore[reportArgumentType, reportCallIssue]

    def test_fail_generator_resolver_without_iterable_hint(self) -> None:
        """A generator resolver annotated with the service type instead of `Iterable[T]` fails."""
        services = ServiceCollection()

        class Service: ...

        def service_resolver() -> Service:  # pyright: ignore[reportInvalidTypeForm]
            yield Service()  # pyright: ignore[reportReturnType]

        with pytest.raises(InvalidResolverReturnHintError) as exc_info:
            services.add_singleton(service_resolver)

        assert exc_info.value.code == "soupape.resolver.invalid_return_hint"
        assert exc_info.value.accepted == ("Generator[T]", "Iterator[T]", "Iterable[T]")
        assert exc_info.value.message == (
            f"Resolver '{service_resolver.__qualname__}' must have a return type hint of "
            "Generator[T], Iterator[T] or Iterable[T]."
        )

    def test_fail_async_generator_resolver_without_async_generator_hint(self) -> None:
        """An async generator resolver annotated with the service type instead of `AsyncGenerator[T]` fails."""
        services = ServiceCollection()

        class Service: ...

        async def service_resolver() -> Service:  # pyright: ignore[reportInvalidTypeForm]
            yield Service()  # pyright: ignore[reportReturnType]

        with pytest.raises(InvalidResolverReturnHintError) as exc_info:
            services.add_singleton(service_resolver)

        assert exc_info.value.accepted == ("AsyncGenerator[T]", "AsyncIterator[T]", "AsyncIterable[T]")

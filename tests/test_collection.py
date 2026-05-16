import pytest
from escondite import Cache

from soupape import ServiceCollection, injectable
from soupape.errors import IncompatibleInterfaceError


def test_service_registration() -> None:
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


def test_fail_register_incompatible_interface() -> None:
    services = ServiceCollection()

    class BaseService: ...

    class Subservice: ...

    with pytest.raises(IncompatibleInterfaceError) as exc_info:
        services.add_singleton(BaseService, Subservice)

    assert exc_info.value.interface == "test_fail_register_incompatible_interface.<locals>.BaseService"
    assert exc_info.value.implementation == "test_fail_register_incompatible_interface.<locals>.Subservice"


def test_copy_collection() -> None:
    services = ServiceCollection()

    class Service: ...

    services.add_singleton(Service)
    copied = services.copy()

    assert copied.is_registered(Service)

    class AnotherService: ...

    copied.add_singleton(AnotherService)

    assert not services.is_registered(AnotherService)
    assert copied.is_registered(AnotherService)


def test_merge_collections() -> None:
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


def test_use_decorate_service() -> None:
    cache = Cache()
    services = ServiceCollection()

    @injectable.singleton(cache=cache)
    class Service: ...

    services.add_from_cache(cache)

    assert services.is_registered(Service)

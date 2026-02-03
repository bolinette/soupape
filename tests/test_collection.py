import pytest

from soupape import ServiceCollection
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

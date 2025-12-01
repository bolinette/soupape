from typing import Protocol

from soupape import ServiceCollection


def test_service_registration() -> None:
    services = ServiceCollection()

    class ProtoService(Protocol):
        pass

    class Service1:
        pass

    class Service2:
        pass

    class Service3:
        pass

    def resolver() -> Service3: ...

    services.add_singleton(Service1)
    services.add_singleton(ProtoService, Service2)
    services.add_singleton(resolver)

    assert services.is_registered(ProtoService)
    assert services.is_registered(Service1)
    assert not services.is_registered(Service2)
    assert services.is_registered(Service3)

from typing import TYPE_CHECKING, Any

from peritype import TWrap

if TYPE_CHECKING:
    from soupape.collection import ServiceCollection


class ServiceDefaultResolver[T]:
    def __init__(
        self,
        services: "ServiceCollection",
        interface: TWrap[T],
        implementation: TWrap[Any],
    ) -> None:
        self._services = services
        self._interface = interface
        self._implementation = implementation

    def __call__(self, *args: Any, **kwds: Any) -> T:
        return self._implementation.instantiate(*args, **kwds)

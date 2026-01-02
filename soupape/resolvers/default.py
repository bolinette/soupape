from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING, Any

from peritype import TWrap

from soupape.metadata import meta
from soupape.post_init import PostInitMetadata
from soupape.resolvers import AsyncServiceDefaultResolver, SyncServiceDefaultResolver
from soupape.types import Injector, ServiceResolver, ServiceResolverFactory

if TYPE_CHECKING:
    from soupape.collection import ServiceCollection


class ServiceDefaultResolver[T](ServiceResolverFactory):
    def __init__(
        self,
        services: "ServiceCollection",
        interface: TWrap[T],
        implementation: TWrap[Any],
    ) -> None:
        self._services = services
        self._interface = interface
        self._implementation = implementation

    @property
    def interface(self) -> TWrap[T]:
        return self._interface

    @property
    def implementation(self) -> TWrap[Any]:
        return self._implementation

    def get_post_inits(self, twrap: TWrap[Any]) -> Iterable[Callable[..., Any]]:
        inner_type: type[Any] = twrap.inner_type
        for attr in vars(inner_type).values():
            if callable(attr) and meta.has(attr, PostInitMetadata.KEY):
                yield attr

    def with_injector(self, injector: Injector) -> ServiceResolver[..., T]:
        if injector.is_async:
            return AsyncServiceDefaultResolver(self, injector)
        else:
            return SyncServiceDefaultResolver(self, injector)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError()

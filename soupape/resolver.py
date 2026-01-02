import asyncio
from collections.abc import Awaitable, Callable, Iterable
from typing import TYPE_CHECKING, Any

from peritype import TWrap

from soupape import Injector
from soupape.metadata import meta
from soupape.post_init import PostInitMetadata
from soupape.types import ServiceResolver

if TYPE_CHECKING:
    from soupape.collection import ServiceCollection


class ServiceResolverFactory[**P, T]:
    def __init__(
        self,
        factory: Callable[[Injector], ServiceResolver[P, T]],
    ) -> None:
        self._factory = factory

    def __call__(self, injector: Injector) -> ServiceResolver[P, T]:
        return self._factory(injector)


class ServiceDefaultResolver[T]:
    def __init__(
        self,
        injector: Injector,
        services: "ServiceCollection",
        interface: TWrap[T],
        implementation: TWrap[Any],
    ) -> None:
        self._injector = injector
        self._services = services
        self._interface = interface
        self._implementation = implementation

    def _get_post_inits(self, twrap: TWrap[Any]) -> Iterable[Callable[..., Any]]:
        inner_type: type[Any] = twrap.inner_type
        for attr in vars(inner_type).values():
            if callable(attr) and meta.has(attr, PostInitMetadata.KEY):
                yield attr

    async def _continue_awaitable(
        self,
        instance: T,
        next_post_init: Awaitable[Any],
        post_inits: Iterable[Callable[..., Any]],
    ) -> T:
        await next_post_init
        for post_init in post_inits:
            result = self._injector.call(post_init, positional_args=[instance])
            if asyncio.iscoroutine(result):
                await result
        return instance

    def _run_call(self, *args: Any, **kwds: Any) -> T | Awaitable[T]:
        instance = self._implementation.instantiate(*args, **kwds)
        post_inits = self._get_post_inits(self._implementation)
        for post_init in post_inits:
            result = self._injector.call(post_init, positional_args=[instance])
            if asyncio.iscoroutine(result):
                return self._continue_awaitable(instance, result, post_inits)
        return instance

    def __call__(self, *args: Any, **kwds: Any) -> T | Awaitable[T]:
        return self._run_call(*args, **kwds)

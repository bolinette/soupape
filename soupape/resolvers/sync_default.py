import asyncio
from collections.abc import Generator
from typing import TYPE_CHECKING, Any

from soupape.errors import AsyncInSyncInjectorError
from soupape.types import Injector

if TYPE_CHECKING:
    from soupape.resolvers import ServiceDefaultResolver


class SyncServiceDefaultResolver[T]:
    def __init__(self, resolver: "ServiceDefaultResolver[T]", injector: Injector) -> None:
        self.resolver = resolver
        self.injector = injector

    def __call__(self, *args: Any, **kwargs: Any) -> Generator[T]:
        instance = self.resolver.implementation.instantiate(*args, **kwargs)
        post_inits = self.resolver.get_post_inits(self.resolver.implementation)
        for post_init in post_inits:
            result = self.injector.call(post_init, positional_args=[instance])
            if asyncio.iscoroutine(result):
                raise AsyncInSyncInjectorError(result)
        yield instance

import asyncio
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any

from soupape.types import Injector

if TYPE_CHECKING:
    from soupape.resolvers import ServiceDefaultResolver


class AsyncServiceDefaultResolver[T]:
    def __init__(self, resolver: "ServiceDefaultResolver[T]", injector: Injector) -> None:
        self._resolver = resolver
        self._injector = injector

    async def __call__(self, *args: Any, **kwargs: Any) -> AsyncGenerator[T]:
        instance = self._resolver.implementation.instantiate(*args, **kwargs)
        post_inits = self._resolver.get_post_inits(self._resolver.implementation)
        for post_init in post_inits:
            result = self._injector.call(post_init, positional_args=[instance])
            if asyncio.iscoroutine(result):
                await result
        yield instance

import asyncio
from collections.abc import AsyncGenerator, Callable, Generator, Iterable
from typing import TYPE_CHECKING, Any

from peritype import TWrap

from soupape.errors import AsyncInSyncInjectorError
from soupape.metadata import meta
from soupape.post_init import PostInitMetadata
from soupape.types import (
    AsyncContextManager,
    InjectionContext,
    ServiceResolver,
    ServiceResolverFactory,
    SyncContextManager,
)

if TYPE_CHECKING:
    from soupape.collection import ServiceCollection


class DefaultResolverFactory[T](ServiceResolverFactory):
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
        for node in twrap.nodes:
            for base in node.bases:
                yield from self.get_post_inits(base)
        inner_type: type[Any] = twrap.inner_type
        for attr in vars(inner_type).values():
            if callable(attr) and meta.has(attr, PostInitMetadata.KEY):
                yield attr

    def __with_context__(self, context: InjectionContext) -> ServiceResolver[..., T]:
        if context.injector.is_async:
            return _AsyncServiceDefaultResolver(self, context)
        else:
            return _SyncServiceDefaultResolver(self, context)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError()


class _AsyncServiceDefaultResolver[T]:
    def __init__(self, resolver: "DefaultResolverFactory[T]", context: InjectionContext) -> None:
        self._resolver = resolver
        self._context = context
        self._injector = context.injector

    async def __call__(self, *args: Any, **kwargs: Any) -> AsyncGenerator[T]:
        instance = self._resolver.implementation.instantiate(*args, **kwargs)
        post_inits = self._resolver.get_post_inits(self._resolver.implementation)
        for post_init in post_inits:
            result = self._injector.call(
                post_init,
                positional_args=[instance],
                origin=self._context.origin,
            )
            if asyncio.iscoroutine(result):
                await result
        if isinstance(instance, AsyncContextManager):
            async with instance:
                yield instance  # pyright: ignore[reportReturnType]
            return
        if isinstance(instance, SyncContextManager):
            with instance:
                yield instance  # pyright: ignore[reportReturnType]
            return
        yield instance


class _SyncServiceDefaultResolver[T]:
    def __init__(self, resolver: "DefaultResolverFactory[T]", context: InjectionContext) -> None:
        self.resolver = resolver
        self._context = context
        self._injector = context.injector

    def __call__(self, *args: Any, **kwargs: Any) -> Generator[T]:
        instance = self.resolver.implementation.instantiate(*args, **kwargs)
        post_inits = self.resolver.get_post_inits(self.resolver.implementation)
        for post_init in post_inits:
            result = self._injector.call(
                post_init,
                positional_args=[instance],
                origin=self._context.origin,
            )
            if asyncio.iscoroutine(result):
                raise AsyncInSyncInjectorError(result)
        if isinstance(instance, SyncContextManager):
            with instance:
                yield instance  # pyright: ignore[reportReturnType]
            return
        yield instance

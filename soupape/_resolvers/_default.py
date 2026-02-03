import asyncio
import inspect
from collections.abc import AsyncGenerator, Callable, Generator, Iterable
from typing import Any, override

from peritype import FWrap, TWrap

from soupape._post_init import PostInitMetadata
from soupape._resolvers import ServiceResolver
from soupape._types import (
    AsyncContextManager,
    InjectionContext,
    InjectionScope,
    ResolveFunction,
    SyncContextManager,
)
from soupape._utils import meta
from soupape.errors import AsyncInSyncInjectorError


class DefaultResolver[**P, T](ServiceResolver[P, T]):
    def __init__(
        self,
        scope: InjectionScope,
        interface: TWrap[T],
        implementation: TWrap[Any],
    ) -> None:
        self._scope = scope
        self._interface = interface
        self._implementation = implementation

    @property
    @override
    def name(self) -> str:
        return str(self._implementation.init)

    @property
    @override
    def scope(self) -> InjectionScope:
        return self._scope

    @property
    @override
    def required(self) -> TWrap[T]:
        return self._interface

    @property
    @override
    def registered(self) -> TWrap[Any]:
        return self._implementation

    @override
    def get_resolve_hints(self, context: InjectionContext) -> dict[str, TWrap[Any]]:
        return self._implementation.init.get_signature_hints(belongs_to=context.origin)

    @override
    def get_instance_function(self) -> FWrap[P, T]:
        return self._implementation.init

    @override
    def get_resolve_signature(self) -> inspect.Signature:
        return self._implementation.signature

    @override
    def get_resolve_func(self, context: InjectionContext) -> ResolveFunction[P, T]:
        if context.injector.is_async:
            return _AsyncServiceDefaultResolveFunc(self, context)
        else:
            return _SyncServiceDefaultResolveFunc(self, context)

    def get_post_inits(self, twrap: TWrap[Any]) -> Iterable[Callable[..., Any]]:
        for node in twrap.nodes:
            for base in node.bases:
                yield from self.get_post_inits(base)
        inner_type: type[Any] = twrap.inner_type
        for attr in vars(inner_type).values():
            if callable(attr) and meta.has(attr, PostInitMetadata.KEY):
                yield attr


class _AsyncServiceDefaultResolveFunc[**P, T]:
    def __init__(self, resolver: "DefaultResolver[P, T]", context: InjectionContext) -> None:
        self._resolver = resolver
        self._context = context
        self._injector = context.injector

    async def __call__(self, *args: Any, **kwargs: Any) -> AsyncGenerator[T]:
        instance = self._resolver.registered.instantiate(*args, **kwargs)
        post_inits = self._resolver.get_post_inits(self._resolver.registered)
        for post_init in post_inits:
            result = self._injector.call(
                post_init,
                positional_args=[instance],
                origin=self._context.origin,
                circular_guard=self._context.circular_guard.copy(),
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


class _SyncServiceDefaultResolveFunc[**P, T]:
    def __init__(self, resolver: "DefaultResolver[P, T]", context: InjectionContext) -> None:
        self.resolver = resolver
        self._context = context
        self._injector = context.injector

    def __call__(self, *args: Any, **kwargs: Any) -> Generator[T]:
        instance = self.resolver.registered.instantiate(*args, **kwargs)
        post_inits = self.resolver.get_post_inits(self.resolver.registered)
        for post_init in post_inits:
            result = self._injector.call(
                post_init,
                positional_args=[instance],
                origin=self._context.origin,
                circular_guard=self._context.circular_guard.copy(),
            )
            if asyncio.iscoroutine(result):
                raise AsyncInSyncInjectorError(result)
        if isinstance(instance, SyncContextManager):
            with instance:
                yield instance  # pyright: ignore[reportReturnType]
            return
        yield instance

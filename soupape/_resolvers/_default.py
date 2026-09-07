import asyncio
import inspect
from collections.abc import AsyncGenerator, Callable, Generator, Iterable
from typing import Any, override

from peritype import FWrap, TWrap

from soupape._decorators._post_init import PostInitMetadata
from soupape._resolvers import ServiceResolver
from soupape._types import (
    AsyncContextManager,
    InjectionContext,
    InjectionScope,
    ResolveFunction,
    SyncContextManager,
)
from soupape._utils import meta
from soupape.errors import AsyncContextManagerInSyncInjectorError


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
        self._post_inits: tuple[Callable[..., Any], ...] | None = None
        inner_type: type[Any] = implementation.inner_type
        self.is_sync_context_manager = issubclass(inner_type, SyncContextManager)
        self.is_async_context_manager = issubclass(inner_type, AsyncContextManager)

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

    @property
    def post_inits(self) -> tuple[Callable[..., Any], ...]:
        if self._post_inits is None:
            self._post_inits = tuple(self.get_post_inits(self._implementation))
        return self._post_inits

    def get_post_inits(self, twrap: TWrap[Any]) -> Iterable[Callable[..., Any]]:
        inner_type: type[Any] = twrap.inner_type
        hooks: dict[str, Callable[..., Any]] = {}
        for cls in reversed(inner_type.__mro__):
            for name, attr in vars(cls).items():
                if callable(attr) and meta.has(attr, PostInitMetadata.KEY):
                    hooks[name] = attr
                else:
                    hooks.pop(name, None)
        yield from hooks.values()


class _AsyncServiceDefaultResolveFunc[**P, T]:
    def __init__(self, resolver: "DefaultResolver[P, T]", context: InjectionContext) -> None:
        self._resolver = resolver
        self._context = context
        self._injector = context.injector

    async def __call__(self, *args: Any, **kwargs: Any) -> AsyncGenerator[T]:
        instance = self._resolver.registered.instantiate(*args, **kwargs)
        for post_init in self._resolver.post_inits:
            result = self._injector.call(
                post_init,
                positional_args=[instance],
                origin=self._context.origin,
                circular_guard=self._context.circular_guard.copy(),
            )
            if asyncio.iscoroutine(result):
                await result
        if self._resolver.is_async_context_manager:
            async with instance:
                yield instance  # pyright: ignore[reportReturnType]
            return
        if self._resolver.is_sync_context_manager:
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
        if self.resolver.is_async_context_manager and not self.resolver.is_sync_context_manager:
            raise AsyncContextManagerInSyncInjectorError(str(self.resolver.registered))
        for post_init in self.resolver.post_inits:
            self._injector.call(
                post_init,
                positional_args=[instance],
                origin=self._context.origin,
                circular_guard=self._context.circular_guard.copy(),
            )
        if self.resolver.is_sync_context_manager:
            with instance:
                yield instance  # pyright: ignore[reportReturnType]
            return
        yield instance

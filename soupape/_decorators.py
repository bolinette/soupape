from collections.abc import Callable
from typing import overload

from escondite import Cache

from soupape._types import InjectionScope


class InjectableContainer[T]:
    def __init__(self, scope: InjectionScope, func: T) -> None:
        self.scope = scope
        self.func = func


class Injectable:
    CACHE_KEY = "__soupape_injectable__"

    def _get_container[T](self, scope: InjectionScope, func: T) -> InjectableContainer[T]:
        return InjectableContainer(scope, func)

    @overload
    def transcient[T](self, func: T, *, cache: Cache | None = None) -> T: ...
    @overload
    def transcient[T](self, *, cache: Cache | None = None) -> Callable[[T], T]: ...
    def transcient[T](
        self,
        func: T | None = None,
        *,
        cache: Cache | None = None,
    ) -> T | Callable[[T], T]:
        def inner(func: T) -> T:
            container = self._get_container(InjectionScope.TRANSIENT, func)
            Cache.with_fallback(cache).add(self.CACHE_KEY, container)
            return func

        if func is None:
            return inner
        return inner(func)

    @overload
    def singleton[T](self, func: T, *, cache: Cache | None = None) -> T: ...
    @overload
    def singleton[T](self, *, cache: Cache | None = None) -> Callable[[T], T]: ...
    def singleton[T](
        self,
        func: T | None = None,
        *,
        cache: Cache | None = None,
    ) -> T | Callable[[T], T]:
        def inner(func: T) -> T:
            container = self._get_container(InjectionScope.SINGLETON, func)
            Cache.with_fallback(cache).add(self.CACHE_KEY, container)
            return func

        if func is None:
            return inner
        return inner(func)

    @overload
    def scoped[T](self, func: T, *, cache: Cache | None = None) -> T: ...
    @overload
    def scoped[T](self, *, cache: Cache | None = None) -> Callable[[T], T]: ...
    def scoped[T](
        self,
        func: T | None = None,
        *,
        cache: Cache | None = None,
    ) -> T | Callable[[T], T]:
        def inner(func: T) -> T:
            container = self._get_container(InjectionScope.SCOPED, func)
            Cache.with_fallback(cache).add(self.CACHE_KEY, container)
            return func

        if func is None:
            return inner
        return inner(func)


injectable = Injectable()

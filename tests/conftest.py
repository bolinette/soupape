import inspect
from collections.abc import Awaitable, Callable
from typing import Any, Unpack, cast

import pytest
from peritype import FWrap, TWrap

from soupape import AsyncInjector, ServiceCollection, SyncInjector
from soupape._types import InjectorCallArgs


async def _resolved[T](result: T | Awaitable[T]) -> T:
    if inspect.isawaitable(result):
        return await cast(Awaitable[T], result)
    return cast(T, result)


class InjectorHarness:
    """An awaitable-uniform facade over `SyncInjector` and `AsyncInjector`.

    Behaviour shared by both injectors is written once against this facade: `require` and
    `call` are always awaited and the scope is always entered with `async with`, whichever
    concrete injector backs it.
    """

    def __init__(self, injector: SyncInjector | AsyncInjector) -> None:
        self.injector = injector

    @property
    def services(self) -> ServiceCollection:
        return self.injector.services

    @property
    def is_async(self) -> bool:
        return self.injector.is_async

    async def require[T](self, interface: type[T] | TWrap[T]) -> T:
        return await _resolved(self.injector.require(interface))

    async def call[T](
        self,
        callable: Callable[..., T] | FWrap[..., T],
        **kwargs: Unpack[InjectorCallArgs],
    ) -> T:
        return await _resolved(self.injector.call(callable, **kwargs))

    def get_scoped_injector(self) -> "InjectorHarness":
        return InjectorHarness(self.injector.get_scoped_injector())

    async def __aenter__(self) -> "InjectorHarness":
        if isinstance(self.injector, AsyncInjector):
            await self.injector.__aenter__()
        else:
            self.injector.__enter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: Any,
    ) -> None:
        if isinstance(self.injector, AsyncInjector):
            await self.injector.__aexit__(exc_type, exc_value, traceback)
        else:
            self.injector.__exit__(exc_type, exc_value, traceback)


type InjectorFactory = Callable[[ServiceCollection], InjectorHarness]


@pytest.fixture(params=[SyncInjector, AsyncInjector], ids=["sync", "async"])
def make_injector(request: pytest.FixtureRequest) -> InjectorFactory:
    injector_type = cast(type[SyncInjector] | type[AsyncInjector], request.param)

    def factory(services: ServiceCollection) -> InjectorHarness:
        return InjectorHarness(injector_type(services))

    return factory

from typing import Any

from soupape import AsyncInjector, ServiceCollection


async def test_inject_with_catch_all_interface() -> None:
    services = ServiceCollection()

    class Service[T]:
        async def fetch_data(self) -> str: ...

    class Service1[T](Service[T]):
        async def fetch_data(self) -> str:
            return "Service1 Data"

    class Service2[T](Service[T]):
        async def fetch_data(self) -> str:
            return "Service2 Data"

    services.add_singleton(Service[Any], Service1)
    services.add_singleton(Service[str], Service2)

    async with AsyncInjector(services) as injector:
        service1 = await injector.require(Service[int])
        service2 = await injector.require(Service[str])

    data1 = await service1.fetch_data()
    data2 = await service2.fetch_data()
    assert data1 == "Service1 Data"
    assert data2 == "Service2 Data"


if __name__ == "__main__":
    import asyncio

    asyncio.run(test_inject_with_catch_all_interface())

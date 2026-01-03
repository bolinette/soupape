# Soupape

Soupape is a dependency injection and inversion of control library in pure Python.
It allows you to manage the dependencies of your services in your application in a clean and efficient way.
Soupape is a standalone library that does not rely on any framework and can be used in any Python project.

## Installation

```shell
$ pip install soupape  # or use your preferred package manager
```

## Features

### Service Registration and Injection

Let's first write some services.

```python
from typing import Any

from my_app.models import User


class HttpService:
    async def get(self, url: str) -> dict[str, Any]: ...


class UserService:
    async def get_user(self, user_id: int) -> User: ...


class AuthService:
    def __init__(self, http: HttpService, user_service: UserService) -> None:
        self.http = http
        self.user_service = user_service

    async def authenticate(self, token: str) -> User: ...
```

Now, we can register them in the service collection.

```python
from soupape import ServiceCollection

from my_app.services import AuthService, HttpService, UserService


def define_services() -> ServiceCollection:
    services = ServiceCollection()
    services.add_singleton(HttpService)
    services.add_scoped(UserService)
    services.add_scoped(AuthService)
    return services


async def main():
    services = define_services()
    async with AsyncInjector(services) as injector:
        async with injector.get_scoped_injector() as scoped_injector:
            auth_service = await scoped_injector.require(AuthService)
            token = ...  # obtain token from somewhere
            user = await auth_service.authenticate(token)
```

Let's break down what we did here:
- We created a 'HttpService' as a singleton, meaning there will be only one instance of it throughout the main injector's lifetime.
- We created 'UserService' and 'AuthService' as scoped services, meaning a new instance will be created for each scoped injector.

A `SyncInjector` also exists for synchronous code only.
In the example above, a synchronous injector could be used because none of the services require asynchronous initialization.
See below for more details on initialization.

### Type hints

Soupape uses type hints to resolve dependencies.
This library makes all type hints mandatory for service constructors and resolver functions.

Errors will be raised if type hints are missing.

### Service Lifetimes

Soupape supports three service lifetimes:
- **Transient**:
   - A new instance is created every time the service is requested.
- **Singleton**:
   - A single instance is created and shared throughout the lifetime of the main injector.
   - A singleton service instance is kept alive in the main injector, even when it is created in a scoped injection session.
   - Singleton services are disposed of when the main injector is closed.
   - Singleton services can only depend on singleton or transient services.
- **Scoped**:
   - The main injector cannot create scoped services, only scoped injectors can.
   - A new instance is created in the scoped injection session.
   - When using multi-level scoped injectors, a scoped service instance is kept alive in the scoped injection session where it was created.
   A child injection session will use the instances from its parent sessions.
   Be careful which scoped injector you request a scoped service from.
   - Scoped services are disposed of when the scoped injection session they were created in is closed.
   - Scoped services can depend on singleton, transient, or scoped services.

### Context manager services

When registered through the default resolver, services can implement the context manager protocol (sync or async) to manage resources.

The `__enter__` (or `__aenter__`) method will be called when the service is created, and the `__exit__` (or `__aexit__`) method will be called when the injection session that created the service is closed.

The `SyncInjector` will raise an error during service injection if any dependency implements the async context manager protocol.
The `AsyncInjector` can handle both sync and async context managers.
If a service implements both protocols, the async one will be used and the sync one will be ignored.

```python
from typing import Self
from types import TracebackType

from soupape import AsyncInjector, ServiceCollection


class ServiceWithResources:
    def __init__(self) -> None:
        self.resource = None

    async def __aenter__(self) -> Self:
        self.resource = await acquire_resource()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None
    ) -> None:
        await release_resource(self.resource)
        self.resource = None


services = ServiceCollection()
services.add_scoped(ServiceWithResources)


async def main():
    async with AsyncInjector(services) as injector:
        async with injector.get_scoped_injector() as scoped_injector:
            service = await scoped_injector.require(ServiceWithResources)
            assert service.resource is not None
        assert service.resource is None
```

When using custom resolver functions, see below, you are responsible for managing the context manager protocol if needed.

### Post init methods

Another way to organize service initialization is to use post init methods.

A post init method can be synchronous or asynchronous.
These methods will be called after the service is created, but before it is returned to the caller.
They will be called in the order they are defined in the class.
Post init methods in parent classes will be called before those in child classes.

```python
from soupape import AsyncInjector, ServiceCollection, post_init


class ServiceWithPostInit:
    def __init__(self) -> None:
        self.state = 'created'

    @post_init
    async def _init_state(self) -> None:
        self.state = 'initialized
```

When using custom resolver functions, post init methods will be ignored.

### Custom resolver functions

You can register your services using your own resolver functions.
It can be useful when you need to pass some parameters to the service constructor that are not managed by the injector.

```python
from soupape import AsyncInjector, ServiceCollection

from my_app.models import User


class UserRepository:
    async def get_user(self, user_id: int) -> User: ...


class CurrentUserService:
    def __init__(self, current_user: User) -> None:
        self._current_user = current_user

    def get_user(self) -> User:
        return self._current_user


async def current_user_service_resolver(
    user_repository: UserRepository
) -> CurrentUserService:
    user_id = ...  # obtain user id from somewhere
    current_user = await user_repository.get_user(user_id)
    return CurrentUserService(current_user)


services = ServiceCollection()
services.add_scoped(UserRepository)
services.add_scoped(current_user_service_resolver)

async def main():
    async with AsyncInjector(services) as injector:
        async with injector.get_scoped_injector() as scoped_injector:
            current_user_service = await scoped_injector.require(CurrentUserService)
            user = current_user_service.get_user()
```

Again, type hints are mandatory for the resolver function parameters and return type.
The registration and the dependency resolution are linked through the return type hint of the resolver function that must match.

When using custom resolver functions, Soupape does not manage the context manager protocol for you.

You can use a context manager in the resolver function, as shown below.

```python
async def service_with_resources_resolver() -> ServiceWithResources:
    async with ServiceWithResources() as service:
        return service

services = ServiceCollection()
services.add_scoped(service_with_resources_resolver)
```

### Generator resolver functions

Resolver functions can use the `yield` statement instead of context managers to execute instructions after the injection session is closed.

```python
from collections.abc import AsyncGenerator


class Service:
    def __init__(self) -> None:
        self.state = 'created'

    async def initialize(self) -> None:
        self.state = 'initialized'

    async def cleanup(self) -> None:
        self.state = 'closed'


async def service_resolver() -> AsyncGenerator[Service]:
    service = Service()
    await service.initialize()
    try:
        yield service
    finally:
        await service.cleanup()


services = ServiceCollection()
services.add_scoped(service_resolver)


async def main():
    async with AsyncInjector(services) as injector:
        async with injector.get_scoped_injector() as scoped_injector:
            service = await scoped_injector.require(Service)
            assert service.state == 'initialized'
        assert service.state == 'closed'
```

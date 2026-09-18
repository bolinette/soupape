# Soupape

Soupape is a dependency injection and inversion of control library in pure Python.
It allows you to manage the dependencies of your services in your application in a clean and efficient way.
Soupape is a standalone library that does not rely on any framework and can be used in any Python project.

Synchronous and asynchronous applications get the same API: `SyncInjector` and `AsyncInjector` register, resolve and dispose services the same way.

Soupape is used by the [Bolinette project](https://github.com/bolinette) as its whole service layer, and its extension surface is what every Bolinette extension registers through.

```python
from soupape import ServiceCollection, SyncInjector


class Database:
    def query(self, sql: str) -> list[str]: ...


class UserService:
    def __init__(self, db: Database) -> None:
        self.db = db


services = ServiceCollection()
services.add_singleton(Database)
services.add_scoped(UserService)

with SyncInjector(services) as injector:
    with injector.get_scoped_injector() as scoped:
        assert isinstance(scoped.require(UserService).db, Database)
```

## Installation

```shell
$ pip install soupape  # or use your preferred package manager
```

## Requirements

Soupape requires Python 3.13 (or newer), and depends on [peritype](https://pypi.org/project/peritype/) to read the type hints it resolves services from, on [hafersack](https://pypi.org/project/hafersack/) to tag the classes its decorators collect, and on [escondite](https://pypi.org/project/escondite/) for the cache those decorators write to.

## Quick start

Write your services as plain classes.
The dependencies are declared as type hints in the constructor, and the injector will resolve them automatically.

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

Register them in a `ServiceCollection`, then resolve them from an injector.

```python
from soupape import AsyncInjector, ServiceCollection

from my_app.services import AuthService, HttpService, UserService


def define_services() -> ServiceCollection:
    services = ServiceCollection()
    services.add_singleton(HttpService)
    services.add_scoped(UserService)
    services.add_scoped(AuthService)
    return services


async def main() -> None:
    async with AsyncInjector(define_services()) as injector:
        async with injector.get_scoped_injector() as scoped_injector:
            auth_service = await scoped_injector.require(AuthService)
            token = ...  # obtain token from somewhere
            user = await auth_service.authenticate(token)
```

`HttpService` is a singleton: a single instance shared for the lifetime of the main injector.
`UserService` and `AuthService` are scoped: a new instance per scoped injector, disposed of when that injection session closes.
The same registrations run on a `SyncInjector`, as long as no service requires asynchronous initialization.

## What Soupape does

- **Service lifetimes** — singleton, scoped and transient.
  Each service can define its own lifetime, the nested injectors will manage their instances accordingly.
- **Injection sessions** — scoped injectors, nested or not.
  Scoped services will be created once per session, and disposed of when the session they belong to closes.
  Child sessions will inherit the parent session's scoped services.
- **Initialization and teardown** — services can implement the sync or async context manager protocol, or declare `@post_init` hooks.
  The injector will enter them as it builds them, and exit them in reverse order, the dependents before their dependencies.
- **Resolver functions** — register a function instead of a class, synchronous, asynchronous, or a generator that cleans up on teardown.
  Its return type hint is the registration.
- **Function calls** — `injector.call(func)` will inject the parameters of any function and call it.
  Some parameters can be given as `positional_args` or `named_args`, the injector will resolve the others.
- **Per-call fallbacks** — `require` and `call` accept a list of fallback resolvers.
  They will serve the parameters no registered service matches, by name or by anything else the resolution context knows about.
- **Custom and annotated resolvers** — `soupape.extension` is the extension surface.
  A `ServiceResolver` will take over a whole type, an `Annotated` marker with a `__resolve__` method will build a single parameter.
- **Collection and context injection** — a `list[T]` or a `dict[str, T]` parameter will receive every registered service assignable to `T`.
  The injector itself, the resolution context and the caller context can be injected the same way.
- **Generic services** — generic services are registered and resolved by specialization.
  `Repository[User]` and `Repository[Order]` are two different services.
- **Registration helpers** — the `@injectable` decorators will register your services from a cache.
- **Errors** — every failure raises a `SoupapeError` with its own error code.
  Unknown services, missing type hints, captive dependencies and circular dependencies are all detected before any instance is created.

Soupape is fully typed and checked in Pyright's strict mode.

## Reference

### Errors

All errors derive from `soupape.errors.SoupapeError`, and carry a dotted `code` alongside their message.

| Error                                  | Code                                            | Raised when                                                          |
| -------------------------------------- | ----------------------------------------------- | -------------------------------------------------------------------- |
| `ServiceNotFoundError`                 | `soupape.service.not_found`                     | No registered service matches an interface                           |
| `AmbiguousServiceMatchError`           | `soupape.service.ambiguous_match`               | More than one service matches an interface                           |
| `ServiceAlreadyRegisteredError`        | `soupape.service.already_registered`            | An interface is registered twice                                     |
| `MissingTypeHintError`                 | `soupape.type_hint.missing`                     | A parameter to inject has no type hint                               |
| `UnresolvedAnyTypeError`               | `soupape.type.unresolved_any`                   | An instance would be stored under a type still holding `Any`         |
| `ScopedServiceNotAvailableError`       | `soupape.scoped_service.not_available`          | A scoped service is required from the root injector                  |
| `CaptiveDependencyError`               | `soupape.dependency.captive`                    | A singleton depends on a scoped service                              |
| `CircularDependencyError`              | `soupape.dependency.circular`                   | Services depend on each other in a cycle                             |
| `CallerContextNotAvailableError`       | `soupape.caller_context.not_available`          | A service reading its caller was required directly                   |
| `AsyncInSyncInjectorError`             | `soupape.injector.async_in_sync`                | A synchronous injector meets an asynchronous resolver                |
| `AsyncContextManagerInSyncInjectorError` | `soupape.injector.async_context_manager_in_sync` | A synchronous injector meets an async context manager              |
| `IncompatibleInterfaceError`           | `soupape.interface.incompatible`                | An implementation does not satisfy the interface it is registered on |
| `MissingInterfaceError`                | `soupape.interface.missing`                     | A resolver has no return type hint and no required type              |
| `InvalidResolverReturnHintError`       | `soupape.resolver.invalid_return_hint`          | A generator resolver does not return an accepted hint                |
| `UnknownInjectionScopeError`           | `soupape.scope.unknown`                         | A registration carries a scope the injector does not know            |

## License

Soupape is released under the MIT license, see [LICENSE.txt](LICENSE.txt).

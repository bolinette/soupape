from collections.abc import Callable, Iterator
from typing import Any, overload

from soupape._utils import meta


class ServiceDependencyMetadata:
    KEY = "__soupape_depends_on__"

    def __init__(self) -> None:
        self._dependencies: set[type[Any]] = set()

    def add(self, dependency: type[Any]) -> None:
        self._dependencies.add(dependency)

    def __iter__(self) -> Iterator[type[Any]]:
        return iter(self._dependencies)


def _push_dependency(dependent: type[Any], dependency: type[Any]) -> None:
    if not meta.has(dependent, ServiceDependencyMetadata.KEY):
        deps_meta = ServiceDependencyMetadata()
        meta.set(dependent, ServiceDependencyMetadata.KEY, deps_meta)
    else:
        deps_meta: ServiceDependencyMetadata = meta.get(dependent, ServiceDependencyMetadata.KEY)
    deps_meta.add(dependency)


@overload
def depends_on[T](dependent: type[T], dependency: type[Any], /) -> type[T]: ...
@overload
def depends_on[T](dependency: type[Any], /) -> Callable[[type[T]], type[T]]: ...
def depends_on[T](*args: Any) -> Any:
    match args:
        case (dependent, dependency):
            _push_dependency(dependent, dependency)
            return dependent
        case (dependency,):

            def inner(dependent: type[T]) -> type[T]:
                _push_dependency(dependent, dependency)
                return dependent

            return inner
        case _:
            raise TypeError(f"Unknown parameters {args}")

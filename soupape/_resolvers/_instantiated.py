import inspect
from typing import Any, override

from peritype import FWrap, TWrap

from soupape._instances import InstancePoolStack
from soupape._resolvers import ServiceResolver
from soupape._types import InjectionScope, ResolutionContext, ResolutionFunction
from soupape.errors import ServiceNotFoundError


class InstantiatedResolver[T](ServiceResolver[[], T]):
    def __init__(self, interface: TWrap[T], implementation: TWrap[Any]) -> None:
        self._interface = interface
        self._implementation = implementation

    @property
    @override
    def scope(self) -> InjectionScope:
        return InjectionScope.IMMEDIATE

    @override
    def get_resolution_hints(self, context: ResolutionContext) -> dict[str, TWrap[Any]]:
        return {}

    @override
    def get_instance_function(self) -> FWrap[[], T]:
        return self._empty_resolver_w

    @override
    def get_resolution_signature(self) -> inspect.Signature:
        return self._empty_resolver_w.signature

    @override
    def get_resolution_func(self, context: ResolutionContext) -> ResolutionFunction[[], T]:
        return _InstantiatedResolveFunc[T](context.injector.instances, self._implementation)  # pyright: ignore[reportReturnType]


class _InstantiatedResolveFunc[T]:
    def __init__(self, instances: InstancePoolStack, tw: TWrap[T]) -> None:
        self._instances = instances
        self._type = tw

    def __call__(self) -> T:
        if self._type not in self._instances:
            raise ServiceNotFoundError(str(self._type))
        return self._instances.get_instance(self._type)

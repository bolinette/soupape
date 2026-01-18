import inspect
from typing import Any, override

from peritype import FWrap, TWrap

from soupape.errors import ServiceNotFoundError
from soupape.instances import InstancePoolStack
from soupape.resolvers import ServiceResolver
from soupape.types import InjectionContext, InjectionScope, ResolveFunction


class InstantiatedResolver[T](ServiceResolver[[], T]):
    def __init__(self, interface: TWrap[T], implementation: TWrap[Any]) -> None:
        self._interface = interface
        self._implementation = implementation

    @property
    @override
    def name(self) -> str:
        return str(self._interface)

    @property
    @override
    def scope(self) -> InjectionScope:
        return InjectionScope.IMMEDIATE

    @property
    @override
    def required(self) -> TWrap[T]:
        return self._interface

    @property
    @override
    def registered(self) -> TWrap[Any]:
        return self._implementation

    @override
    def get_resolve_hints(self, **kwargs: Any) -> dict[str, TWrap[Any]]:
        return {}

    @override
    def get_instance_function(self) -> FWrap[[], T]:
        return self._empty_resolver_w

    @override
    def get_resolve_signature(self) -> inspect.Signature:
        return self._empty_resolver_w.signature

    @override
    def get_resolve_func(self, context: InjectionContext) -> ResolveFunction[[], T]:
        return _InstantiatedResolveFunc[T](context.injector.instances, self._implementation)  # pyright: ignore[reportReturnType]


class _InstantiatedResolveFunc[T]:
    def __init__(self, instances: InstancePoolStack, tw: TWrap[T]) -> None:
        self._instances = instances
        self._type = tw

    def __call__(self) -> T:
        if self._type not in self._instances:
            raise ServiceNotFoundError(str(self._type))
        return self._instances.get_instance(self._type)

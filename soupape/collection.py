from collections.abc import Callable
from typing import Any, overload

from peritype import TWrap, wrap_func, wrap_type
from peritype.collections import TypeBag, TypeMap

from soupape.resolver import ServiceDefaultResolver
from soupape.types import InjectionScope, ServiceResolver, TypeResolverMetadata


class ServiceCollection:
    def __init__(self) -> None:
        self._registered_services = TypeBag()
        self._resolvers = TypeMap[Any, TypeResolverMetadata[..., Any]]()

    def _add_resolver(self, metadata: TypeResolverMetadata[..., Any]) -> None:
        if metadata.interface in self._registered_services:
            raise ValueError(f"Service resolver for type {metadata.interface} is already registered.")
        self._registered_services.add(metadata.interface)
        self._resolvers.add(metadata.interface, metadata)

    def _unpack_registration_args(
        self,
        scope: InjectionScope,
        args: tuple[Any, ...],
    ) -> TypeResolverMetadata[..., Any]:
        implementation: type[Any] | None = None
        interface: type[Any] | None = None
        match args:
            case (type() as i1,):
                implementation = i1
                interface = i1
                resolver = None
            case (type() as i1, type() as i2):
                interface = i1
                implementation = i2
                resolver = None
            case (Callable() as r1,):
                interface = None
                implementation = None
                resolver = r1
            case _:
                raise TypeError()

        if interface is None or implementation is None:
            assert resolver is not None
            fwrap = wrap_func(resolver)
            wrap_interface = fwrap.get_return_hint()
            wrap_implementation = wrap_interface
        else:
            assert resolver is None
            wrap_interface = wrap_type(interface)
            wrap_implementation = wrap_type(implementation)
            resolver = ServiceDefaultResolver(self, wrap_interface, wrap_implementation)
        fwrap = wrap_interface.init
        return TypeResolverMetadata(
            scope=scope,
            interface=wrap_interface,
            implementation=wrap_implementation,
            resolver=resolver,
            signature=wrap_implementation.signature,
            fwrap=fwrap,
        )

    def is_registered[T](self, interface: type[T] | TWrap[T]) -> bool:
        if not isinstance(interface, TWrap):
            interface = wrap_type(interface)
        return interface in self._registered_services

    def get_metadata[T](self, interface: type[T] | TWrap[T]) -> TypeResolverMetadata[..., T]:
        if not isinstance(interface, TWrap):
            interface = wrap_type(interface)
        return self._resolvers[interface]

    @overload
    def add_singleton[IntrT, ImplT](self, interface: type[IntrT], implementation: type[ImplT], /) -> None: ...
    @overload
    def add_singleton[ImplT](self, implementation: type[ImplT], /) -> None: ...
    @overload
    def add_singleton[**P, IntrT](self, resolver: ServiceResolver[P, IntrT], /) -> None: ...
    def add_singleton(self, *args: Any) -> None:
        metadata = self._unpack_registration_args(InjectionScope.SINGLETON, args)
        self._add_resolver(metadata)

    @overload
    def add_scoped[IntrT, ImplT](self, interface: type[IntrT], implementation: type[ImplT], /) -> None: ...
    @overload
    def add_scoped[ImplT](self, implementation: type[ImplT], /) -> None: ...
    def add_scoped(self, *args: Any) -> None:
        metadata = self._unpack_registration_args(InjectionScope.SCOPED, args)
        self._add_resolver(metadata)

    @overload
    def add_transient[IntrT, ImplT](self, interface: type[IntrT], implementation: type[ImplT], /) -> None: ...
    @overload
    def add_transient[ImplT](self, implementation: type[ImplT], /) -> None: ...
    def add_transient(self, *args: Any) -> None:
        metadata = self._unpack_registration_args(InjectionScope.TRANSIENT, args)
        self._add_resolver(metadata)

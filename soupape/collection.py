import inspect
from collections.abc import AsyncGenerator, AsyncIterable, Callable, Generator, Iterable
from typing import Any, overload

from peritype import FWrap, TWrap, wrap_func, wrap_type
from peritype.collections import TypeBag, TypeMap

from soupape.resolver import ServiceDefaultResolver, ServiceResolverFactory
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

    def _unpack_resolver_function_return(self, func: FWrap[..., Any]) -> TWrap[Any]:
        original = func.func
        hint = func.get_return_hint()
        if inspect.isasyncgenfunction(original):
            if hint.match(AsyncGenerator[Any, Any] | AsyncIterable[Any]):
                return hint.generic_params[0]
            else:
                raise TypeError("Async generator resolver functions must have return type hint of AsyncGenerator[T].")
        elif inspect.isgeneratorfunction(original):
            if hint.match(Iterable[Any] | Generator[Any, Any, Any]):
                return hint.generic_params[0]
            else:
                raise TypeError("Generator resolver functions must have return type hint of Iterable[T].")
        return hint

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
            wrap_interface = self._unpack_resolver_function_return(fwrap)
            wrap_implementation = wrap_interface
            signature = fwrap.signature
        else:
            assert resolver is None
            wrap_interface = wrap_type(interface)
            wrap_implementation = wrap_type(implementation)
            resolver = ServiceResolverFactory(
                lambda injector: ServiceDefaultResolver(injector, self, wrap_interface, wrap_implementation)
            )
            signature = wrap_implementation.signature
            fwrap = wrap_interface.init

        return TypeResolverMetadata(
            scope=scope,
            interface=wrap_interface,
            implementation=wrap_implementation,
            resolver=resolver,
            signature=signature,
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
    @overload
    def add_scoped[**P, IntrT](self, resolver: ServiceResolver[P, IntrT], /) -> None: ...
    def add_scoped(self, *args: Any) -> None:
        metadata = self._unpack_registration_args(InjectionScope.SCOPED, args)
        self._add_resolver(metadata)

    @overload
    def add_transient[IntrT, ImplT](self, interface: type[IntrT], implementation: type[ImplT], /) -> None: ...
    @overload
    def add_transient[ImplT](self, implementation: type[ImplT], /) -> None: ...
    @overload
    def add_transient[**P, IntrT](self, resolver: ServiceResolver[P, IntrT], /) -> None: ...
    def add_transient(self, *args: Any) -> None:
        metadata = self._unpack_registration_args(InjectionScope.TRANSIENT, args)
        self._add_resolver(metadata)

    def copy(self) -> "ServiceCollection":
        new_collection = ServiceCollection()
        new_collection._registered_services = self._registered_services.copy()
        new_collection._resolvers = self._resolvers.copy()
        return new_collection

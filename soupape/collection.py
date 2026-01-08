import inspect
from collections.abc import AsyncGenerator, AsyncIterable, Generator, Iterable
from typing import Any, overload

from peritype import FWrap, TWrap, wrap_func, wrap_type
from peritype.collections import TypeBag, TypeMap

from soupape.errors import ServiceNotFoundError
from soupape.resolvers import DefaultResolverFactory
from soupape.types import InjectionScope, ServiceResolver, TypeResolverMetadata
from soupape.utils import is_type_like


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
            case (arg1,) if is_type_like(arg1):
                interface = arg1
                implementation = arg1
                resolver = None
            case (arg1, arg2) if is_type_like(arg1) and is_type_like(arg2):
                interface = arg1
                implementation = arg2
                resolver = None
            case (arg1,) if callable(arg1):
                interface = None
                implementation = None
                resolver = arg1
            case (arg1, arg2) if callable(arg1) and is_type_like(arg2):
                interface = arg2
                implementation = None
                resolver = arg1
            case _:
                raise TypeError()

        if resolver is not None:
            if inspect.ismethod(resolver) or inspect.isfunction(resolver):
                fwrap = wrap_func(resolver)
            else:
                fwrap = wrap_func(resolver.__call__)
            resolver_return = self._unpack_resolver_function_return(fwrap)
            if interface is None:
                wrap_interface = resolver_return
                wrap_implementation = resolver_return
            else:
                wrap_interface = wrap_type(interface)
                wrap_implementation = resolver_return
            signature = fwrap.signature
        else:
            assert implementation is not None and interface is not None
            wrap_interface = wrap_type(interface)
            wrap_implementation = wrap_type(implementation)
            resolver = DefaultResolverFactory(self, wrap_interface, wrap_implementation)
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
        return interface in self._registered_services or self._registered_services.contains_matching(interface)

    def get_metadata[T](self, interface: type[T] | TWrap[T]) -> TypeResolverMetadata[..., T]:
        if not isinstance(interface, TWrap):
            interface = wrap_type(interface)
        if interface in self._registered_services:
            return self._resolvers[interface]
        if self._registered_services.contains_matching(interface):
            matched = self._registered_services.get_matching(interface)
            assert matched is not None
            return self._resolvers[matched]
        raise ServiceNotFoundError(str(interface))

    @overload
    def add_singleton[IntrT, ImplT](self, interface: type[IntrT], implementation: type[ImplT], /) -> None: ...
    @overload
    def add_singleton[ImplT](self, implementation: type[ImplT], /) -> None: ...
    @overload
    def add_singleton[**P, IntrT](self, resolver: ServiceResolver[P, IntrT], /) -> None: ...
    @overload
    def add_singleton[**P, IntrT](self, resolver: ServiceResolver[P, IntrT], interface: type[IntrT], /) -> None: ...

    def add_singleton(self, *args: Any) -> None:
        metadata = self._unpack_registration_args(InjectionScope.SINGLETON, args)
        self._add_resolver(metadata)

    @overload
    def add_scoped[IntrT, ImplT](self, interface: type[IntrT], implementation: type[ImplT], /) -> None: ...
    @overload
    def add_scoped[ImplT](self, implementation: type[ImplT], /) -> None: ...
    @overload
    def add_scoped[**P, IntrT](self, resolver: ServiceResolver[P, IntrT], /) -> None: ...
    @overload
    def add_scoped[**P, IntrT](self, resolver: ServiceResolver[P, IntrT], interface: type[IntrT], /) -> None: ...

    def add_scoped(self, *args: Any) -> None:
        metadata = self._unpack_registration_args(InjectionScope.SCOPED, args)
        self._add_resolver(metadata)

    @overload
    def add_transient[IntrT, ImplT](self, interface: type[IntrT], implementation: type[ImplT], /) -> None: ...
    @overload
    def add_transient[ImplT](self, implementation: type[ImplT], /) -> None: ...
    @overload
    def add_transient[**P, IntrT](self, resolver: ServiceResolver[P, IntrT], /) -> None: ...
    @overload
    def add_transient[**P, IntrT](self, resolver: ServiceResolver[P, IntrT], interface: type[IntrT], /) -> None: ...

    def add_transient(self, *args: Any) -> None:
        metadata = self._unpack_registration_args(InjectionScope.TRANSIENT, args)
        self._add_resolver(metadata)

    def copy(self) -> "ServiceCollection":
        new_collection = ServiceCollection()
        new_collection._registered_services = self._registered_services.copy()
        new_collection._resolvers = self._resolvers.copy()
        return new_collection

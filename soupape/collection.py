import inspect
from collections.abc import AsyncGenerator, AsyncIterable, Generator, Iterable
from typing import Any, overload

from peritype import FWrap, TWrap, wrap_func, wrap_type
from peritype.collections import TypeBag, TypeMap

from soupape.errors import ServiceNotFoundError
from soupape.resolvers import (
    DefaultResolverContainer,
    FunctionResolverContainer,
    ServiceResolver,
)
from soupape.types import InjectionScope, ResolveFunction
from soupape.utils import is_type_like


class ServiceCollection:
    def __init__(self) -> None:
        self._registered_services = TypeBag()
        self._resolvers = TypeMap[Any, ServiceResolver[..., Any]]()

    def add_resolver(self, resolver: ServiceResolver[..., Any]) -> None:
        if resolver.required is None:
            raise ValueError("Service resolver must have a required type.")
        if resolver.required in self._registered_services:
            raise ValueError(f"Service resolver for type {resolver.required} is already registered.")
        self._registered_services.add(resolver.required)
        self._resolvers.add(resolver.required, resolver)

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
    ) -> ServiceResolver[..., Any]:
        implementation: type[Any] | None = None
        interface: type[Any] | None = None
        match args:
            case (arg1,) if is_type_like(arg1):
                interface = arg1
                implementation = arg1
                func_resolver = None
            case (arg1, arg2) if is_type_like(arg1) and is_type_like(arg2):
                interface = arg1
                implementation = arg2
                func_resolver = None
            case (arg1,) if callable(arg1):
                interface = None
                implementation = None
                func_resolver = arg1
            case (arg1, arg2) if is_type_like(arg1) and callable(arg2):
                interface = arg1
                implementation = None
                func_resolver = arg2
            case _:
                raise TypeError()

        if func_resolver is not None:
            if inspect.ismethod(func_resolver) or inspect.isfunction(func_resolver):
                fwrap = wrap_func(func_resolver)
            else:
                fwrap = wrap_func(func_resolver.__call__)
            func_resolver_return = self._unpack_resolver_function_return(fwrap)
            if interface is None:
                interface_w = func_resolver_return
                implementation_w = func_resolver_return
            else:
                interface_w = wrap_type(interface)
                implementation_w = func_resolver_return
            return FunctionResolverContainer(scope, fwrap, required=interface_w, registered=implementation_w)

        assert implementation is not None and interface is not None
        interface_w = wrap_type(interface)
        implementation_w = wrap_type(implementation)
        return DefaultResolverContainer(scope, interface_w, implementation_w)

    def is_registered[T](self, interface: type[T] | TWrap[T]) -> bool:
        if not isinstance(interface, TWrap):
            interface = wrap_type(interface)
        return interface in self._registered_services or self._registered_services.contains_matching(interface)

    def get_resolver[T](self, interface: type[T] | TWrap[T]) -> ServiceResolver[..., T]:
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
    def add_singleton[**P, IntrT](self, resolver: ResolveFunction[P, IntrT], /) -> None: ...
    @overload
    def add_singleton[**P, IntrT](self, interface: type[IntrT], resolver: ResolveFunction[P, IntrT], /) -> None: ...

    def add_singleton(self, *args: Any) -> None:
        resolver = self._unpack_registration_args(InjectionScope.SINGLETON, args)
        self.add_resolver(resolver)

    @overload
    def add_scoped[IntrT, ImplT](self, interface: type[IntrT], implementation: type[ImplT], /) -> None: ...
    @overload
    def add_scoped[ImplT](self, implementation: type[ImplT], /) -> None: ...
    @overload
    def add_scoped[**P, IntrT](self, resolver: ResolveFunction[P, IntrT], /) -> None: ...
    @overload
    def add_scoped[**P, IntrT](self, interface: type[IntrT], resolver: ResolveFunction[P, IntrT], /) -> None: ...

    def add_scoped(self, *args: Any) -> None:
        resolver = self._unpack_registration_args(InjectionScope.SCOPED, args)
        self.add_resolver(resolver)

    @overload
    def add_transient[IntrT, ImplT](self, interface: type[IntrT], implementation: type[ImplT], /) -> None: ...
    @overload
    def add_transient[ImplT](self, implementation: type[ImplT], /) -> None: ...
    @overload
    def add_transient[**P, IntrT](self, resolver: ResolveFunction[P, IntrT], /) -> None: ...
    @overload
    def add_transient[**P, IntrT](self, interface: type[IntrT], resolver: ResolveFunction[P, IntrT], /) -> None: ...

    def add_transient(self, *args: Any) -> None:
        resolver = self._unpack_registration_args(InjectionScope.TRANSIENT, args)
        self.add_resolver(resolver)

    def copy(self) -> "ServiceCollection":
        new_collection = ServiceCollection()
        new_collection._registered_services = self._registered_services.copy()
        new_collection._resolvers = self._resolvers.copy()
        return new_collection

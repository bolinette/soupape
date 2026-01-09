import inspect
from collections.abc import Callable
from typing import Any, Unpack, cast, overload

from peritype import FWrap, TWrap, wrap_func, wrap_type

from soupape.collection import ServiceCollection
from soupape.errors import AsyncInSyncInjectorError
from soupape.injector import BaseInjector
from soupape.instances import InstancePoolStack
from soupape.resolvers import DependencyTreeNode, FunctionResolverContainer
from soupape.types import (
    InjectionContext,
    InjectionScope,
    Injector,
    InjectorCallArgs,
)


class SyncInjector(BaseInjector, Injector):
    def __init__(self, services: ServiceCollection, instance_pool: InstancePoolStack | None = None) -> None:
        super().__init__(services, instance_pool)
        self._set_injector_in_services()

    @property
    def is_async(self) -> bool:
        return False

    def _set_injector_in_services(self) -> None:
        self._instance_pool.set_instance(injector_w, self)
        self._instance_pool.set_instance(sync_injector_w, self)

    def _resolve_service[T](
        self,
        context: InjectionContext,
        dsep_node: DependencyTreeNode[..., T],
    ) -> T:
        resolved_args: list[Any] = []
        if context.positional_args is not None:
            positional_args = context.positional_args
            for arg in positional_args:
                resolved_args.append(arg)
        for arg in dsep_node.args:
            resolved_arg = self._resolve_service(context.copy(dsep_node.scope, arg.required), arg)
            resolved_args.append(resolved_arg)

        resolved_kwargs: dict[str, Any] = {}
        for kwarg_name, kwarg in dsep_node.kwargs.items():
            resolved_kwarg = self._resolve_service(context.copy(dsep_node.scope, kwarg.required), kwarg)
            resolved_kwargs[kwarg_name] = resolved_kwarg

        resolver = dsep_node.resolver.get_resolve_func(context)
        resolved = resolver(*resolved_args, **resolved_kwargs)

        if inspect.isgenerator(resolved):
            self._generators_to_close.append(resolved)
            resolved = next(resolved)
        elif inspect.isasyncgen(resolved):
            raise AsyncInSyncInjectorError(resolved)
        if inspect.iscoroutine(resolved):
            raise AsyncInSyncInjectorError(resolved)

        if dsep_node.registered is not None:
            self._set_instance(dsep_node.scope, dsep_node.registered, resolved)

        return resolved  # type: ignore

    def require[T](self, interface: type[T] | TWrap[T]) -> T:
        if not isinstance(interface, TWrap):
            twrap = wrap_type(interface)
        else:
            twrap = interface
        return self._require(twrap)

    def _require[T](self, interface: TWrap[T]) -> T:
        resolver = self._get_service_resolver(interface)
        context = self._get_injection_context(interface, resolver.scope, interface)
        dep_node = self._build_dependency_tree(context, resolver)
        resolved = self._resolve_service(context, dep_node)
        return resolved

    @overload
    def call[**P, T](
        self,
        callable: FWrap[P, T],
        **kwargs: Unpack[InjectorCallArgs],
    ) -> T: ...
    @overload
    def call[**P, T](
        self,
        callable: Callable[P, T],
        **kwargs: Unpack[InjectorCallArgs],
    ) -> T: ...
    def call(
        self,
        callable: Callable[..., Any] | FWrap[..., Any],
        **kwargs: Unpack[InjectorCallArgs],
    ) -> Any:
        if not isinstance(callable, FWrap):
            fwrap = wrap_func(callable)
        else:
            fwrap = cast(FWrap[..., Any], callable)

        context = self._get_injection_context(
            kwargs.get("origin"),
            InjectionScope.IMMEDIATE,
            positional_args=kwargs.get("positional_args"),
        )
        resolver = FunctionResolverContainer(InjectionScope.IMMEDIATE, fwrap)
        dep_node = self._build_dependency_tree(context, resolver)
        return self._resolve_service(context, dep_node)

    def get_scoped_injector(self) -> "SyncInjector":
        return SyncInjector(self._services, self._instance_pool.stack())


sync_injector_w = wrap_type(SyncInjector)
injector_w = wrap_type(Injector)

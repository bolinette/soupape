import inspect
from collections.abc import Callable, Generator
from contextlib import ExitStack, contextmanager
from types import TracebackType
from typing import Any, Self, Unpack, cast, overload

from peritype import FWrap, TWrap, wrap_func, wrap_type

from soupape._collection import ServiceCollection
from soupape._injector._base import BaseInjector, injector_w
from soupape._instances import InstancePoolStack
from soupape._resolvers import DependencyTreeNode
from soupape._types import (
    InjectionContext,
    InjectionScope,
    Injector,
    InjectorCallArgs,
)
from soupape._utils import CircularGuard
from soupape.errors import AsyncInSyncInjectorError


class SyncInjector(BaseInjector, Injector):
    def __init__(
        self,
        services: ServiceCollection,
        instance_pool: InstancePoolStack | None = None,
        *,
        parent: Self | None = None,
    ) -> None:
        super().__init__(services, instance_pool, parent=parent)
        self._exit_stack = ExitStack()
        self._set_injector_in_services()

    @property
    def is_async(self) -> bool:
        return False

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._exit_stack.__exit__(exc_type, exc_value, traceback)

    def _set_injector_in_services(self) -> None:
        self._instance_pool.set_instance(injector_w, self)
        self._instance_pool.set_instance(sync_injector_w, self)

    def _enter_generator[T](
        self,
        context: InjectionContext,
        generator: Generator[T, Any, Any],
    ) -> T:
        owner = self._get_generator_owner(context)
        return owner._exit_stack.enter_context(_enter_generator(generator))

    def _resolve_service[T](
        self,
        context: InjectionContext,
        dep_node: DependencyTreeNode[..., T],
    ) -> T:
        self._enter_circular_guard(context, dep_node.resolver)
        context = self._with_singleton_owner(context, dep_node.resolver)
        key = self._get_storage_key(context, dep_node)
        if key is not None and self._has_instance(key):
            return self._instance_pool.get_instance(key)
        return self._build_service(context, dep_node)

    def _build_service[T](
        self,
        context: InjectionContext,
        dep_node: DependencyTreeNode[..., T],
    ) -> T:
        resolved_args: list[Any] = []
        if context.positional_args is not None:
            for arg in context.positional_args:
                resolved_args.append(arg)
        for arg in dep_node.args:
            resolved_arg = self._resolve_service(
                context.new_required(arg.scope, arg.required, arg.caller_context),
                arg,
            )
            resolved_args.append(resolved_arg)

        resolved_kwargs: dict[str, Any] = {}
        for kwarg_name, kwarg in dep_node.kwargs.items():
            resolved_kwarg = self._resolve_service(
                context.new_required(kwarg.scope, kwarg.required, kwarg.caller_context),
                kwarg,
            )
            resolved_kwargs[kwarg_name] = resolved_kwarg

        resolver = dep_node.resolver.get_resolution_func(context)
        resolved = resolver(*resolved_args, **resolved_kwargs)

        if inspect.isgenerator(resolved):
            resolved = self._enter_generator(context, resolved)
        elif inspect.isasyncgen(resolved):
            raise AsyncInSyncInjectorError(resolved)
        if inspect.iscoroutine(resolved):
            raise AsyncInSyncInjectorError(resolved)

        if dep_node.registered is not None:
            self._set_instance(context, dep_node.registered, resolved)

        return resolved  # type: ignore

    def require[T](self, interface: type[T] | TWrap[T]) -> T:
        if not isinstance(interface, TWrap):
            twrap = wrap_type(interface)
        else:
            twrap = interface
        return self._require(twrap, CircularGuard())

    def _resolve_depends_on_services(self, interface: TWrap[Any], circular_guard: CircularGuard) -> None:
        for dep_type in self._get_depends_on_services(interface):
            self._require(wrap_type(dep_type), circular_guard)

    def _require[T](self, interface: TWrap[T], circular_guard: CircularGuard) -> T:
        depends_on_guard = circular_guard.copy()
        depends_on_guard.enter_type(interface)
        self._resolve_depends_on_services(interface, depends_on_guard)
        resolver = self._get_service_resolver(interface)
        context = self._get_injection_context(
            interface,
            resolver.scope,
            circular_guard,
            required=interface,
        )
        dep_node = self._build_dependency_tree(context.fork(), resolver)
        resolved = self._resolve_service(context.fork(), dep_node)
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
            circular_guard=kwargs.get("circular_guard"),
            positional_args=kwargs.get("positional_args"),
        )
        resolver = self._get_function_resolver(fwrap)
        dep_node = self._build_dependency_tree(context.fork(), resolver)
        return self._resolve_service(context.fork(), dep_node)

    def get_scoped_injector(self) -> "SyncInjector":
        return SyncInjector(self._services, self._instance_pool.stack(), parent=self)


sync_injector_w = wrap_type(SyncInjector)


def _identity[T](generator: Generator[T, Any, Any]) -> Generator[T, Any, Any]:
    return generator


_enter_generator = contextmanager(_identity)

from collections.abc import Generator
from typing import Any, Self

from peritype import TWrap

from soupape import ServiceCollection
from soupape.errors import MissingTypeHintError, ScopedServiceNotAvailableError, ServiceNotFoundError
from soupape.instances import InstancePoolStack
from soupape.resolvers import (
    DependencyTreeNode,
    InstantiatedResolverContainer,
    RawTypeResolverContainer,
    ServiceResolver,
    WrappedTypeResolverContainer,
)
from soupape.types import (
    InjectionContext,
    InjectionScope,
    Injector,
)
from soupape.utils import CircularGuard


class BaseInjector(Injector):
    def __init__(self, services: ServiceCollection, instance_pool: InstancePoolStack | None = None) -> None:
        self._services = services.copy()
        self._instance_pool = instance_pool if instance_pool is not None else InstancePoolStack()
        self._generators_to_close: list[Generator[Any]] = []
        self._register_common_resolvers()

    def _register_common_resolvers(self) -> None:
        if self.is_root_injector:
            self._services.add_resolver(RawTypeResolverContainer())
            self._services.add_resolver(WrappedTypeResolverContainer())

    def _get_injection_context(
        self,
        origin: TWrap[Any] | None,
        scope: InjectionScope,
        circular_guard: CircularGuard | None = None,
        required: TWrap[Any] | None = None,
        positional_args: list[Any] | None = None,
    ) -> InjectionContext:
        return InjectionContext(
            injector=self,
            origin=origin,
            scope=scope,
            required=required,
            positional_args=positional_args,
            circular_guard=circular_guard or CircularGuard(),
        )

    @property
    def is_root_injector(self) -> bool:
        return len(self._instance_pool) == 1

    @property
    def instances(self) -> InstancePoolStack:
        return self._instance_pool

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: Any,
    ) -> None:
        for gen in self._generators_to_close:
            try:
                next(gen)
            except StopIteration:
                pass

    def _has_instance(self, twrap: TWrap[Any]) -> bool:
        return twrap in self._instance_pool

    def _set_instance(self, scope: InjectionScope, twrap: TWrap[Any], instance: Any) -> None:
        match scope:
            case InjectionScope.IMMEDIATE | InjectionScope.TRANSIENT:
                return
            case InjectionScope.SINGLETON:
                set_to_root = True
            case InjectionScope.SCOPED:
                if self.is_root_injector:
                    raise ScopedServiceNotAvailableError(str(twrap))
                set_to_root = False
        self._instance_pool.set_instance(twrap, instance, root=set_to_root)

    def _make_instantiated_resolver[T](
        self,
        interface: TWrap[T],
        implementation: TWrap[Any] | None = None,
    ) -> ServiceResolver[..., Any]:
        return InstantiatedResolverContainer(interface, implementation or interface)

    def _get_service_resolver(self, interface: TWrap[Any]) -> ServiceResolver[..., Any]:
        if self._services.is_registered(interface):
            resolver = self._services.get_resolver(interface)
            registered = resolver.registered
            if registered is not None and self._has_instance(registered):
                return self._make_instantiated_resolver(interface, registered)
            return resolver
        if self._has_instance(interface):
            return self._make_instantiated_resolver(interface)
        raise ServiceNotFoundError(str(interface))

    def _build_dependency_tree(
        self,
        context: InjectionContext,
        resolver: ServiceResolver[..., Any],
    ) -> DependencyTreeNode[..., Any]:
        context.circular_guard.enter(resolver.get_instance_function())

        args: list[DependencyTreeNode[..., Any]] = []
        kwargs: dict[str, DependencyTreeNode[..., Any]] = {}
        hints = resolver.get_resolve_hints(belongs_to=context.origin)

        if context.positional_args is not None:
            skip = len(context.positional_args)
        else:
            skip = 0

        for param_name, param in resolver.get_resolve_signature().parameters.items():
            if skip > 0:
                skip -= 1
                continue
            if param_name not in hints:
                raise MissingTypeHintError(param_name, resolver.name)
            hint = hints[param_name]
            hint_resolver = self._get_service_resolver(hint)
            dep_node = self._build_dependency_tree(
                context.new_required(hint_resolver.scope, hint),
                hint_resolver,
            )
            if param.kind in (param.POSITIONAL_ONLY, param.POSITIONAL_OR_KEYWORD):
                args.append(dep_node)
            elif param.kind == param.KEYWORD_ONLY:
                kwargs[param_name] = dep_node

        return DependencyTreeNode(
            scope=resolver.scope,
            args=args,
            kwargs=kwargs,
            resolver=resolver,
            required=context.required,
            registered=resolver.registered,
        )

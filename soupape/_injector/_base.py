from collections.abc import Iterable
from typing import Any, Self

from peritype import FWrap, TWrap, wrap_type

from soupape._collection import ServiceCollection
from soupape._decorators import get_custom_resolver
from soupape._decorators._depends_on import ServiceDependencyMetadata
from soupape._instances import InstancePoolStack
from soupape._resolvers import (
    CallerContextResolver,
    DependencyTreeNode,
    DictResolver,
    FunctionResolver,
    InstantiatedResolver,
    ListResolver,
    RawTypeResolver,
    ResolutionContextResolver,
    ServiceResolver,
    WrappedTypeResolver,
)
from soupape._traits import get_annotated_resolver
from soupape._types import CallerContext, InjectionContext, InjectionScope, Injector
from soupape._utils import CircularGuard, accumulate_meta_on_twrap
from soupape.errors import (
    CaptiveDependencyError,
    MissingTypeHintError,
    ScopedServiceNotAvailableError,
    ServiceNotFoundError,
    UnresolvedAnyTypeError,
)


class BaseInjector(Injector):
    def __init__(
        self,
        services: ServiceCollection,
        instance_pool: InstancePoolStack | None = None,
        *,
        parent: Self | None = None,
    ) -> None:
        self._services = services.copy()
        self._instance_pool = instance_pool if instance_pool is not None else InstancePoolStack()
        self._root = self if parent is None else parent._root
        self._register_common_resolvers()
        self._register_base_services()

    def _register_common_resolvers(self) -> None:
        if self.is_root_injector:
            self._services.add_resolver(RawTypeResolver())
            self._services.add_resolver(WrappedTypeResolver())
            self._services.add_resolver(ListResolver())
            self._services.add_resolver(DictResolver())
            self._services.add_resolver(ResolutionContextResolver())
            self._services.add_resolver(CallerContextResolver())

    def _register_base_services(self) -> None:
        if self.is_root_injector:
            self._instance_pool.set_instance(service_collection_w, self.services)

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

    def _enter_circular_guard(self, context: InjectionContext, resolver: ServiceResolver[..., Any]) -> None:
        if context.required is not None:
            context.circular_guard.enter_type(context.required)
        else:
            context.circular_guard.enter(resolver.get_instance_function())

    def _with_singleton_owner(self, context: InjectionContext, resolver: ServiceResolver[..., Any]) -> InjectionContext:
        if resolver.scope is InjectionScope.SINGLETON and resolver.registered is not None:
            return context.with_singleton_owner(resolver)
        return context

    def _get_generator_owner(self, context: InjectionContext) -> Self:
        if context.singleton_owner is not None:
            return self._root
        return self

    @property
    def instances(self) -> InstancePoolStack:
        return self._instance_pool

    @property
    def services(self) -> ServiceCollection:
        return self._services

    def _has_instance(self, twrap: TWrap[Any]) -> bool:
        return twrap in self._instance_pool

    def _get_instance_key(self, context: InjectionContext, twrap: TWrap[Any]) -> TWrap[Any]:
        if twrap.contains_any:
            if context.required is not None:
                twrap = twrap.specialize_with(context.required)
            if twrap.contains_any:
                raise UnresolvedAnyTypeError(str(twrap))
        return twrap

    def _set_instance(self, context: InjectionContext, twrap: TWrap[Any], instance: Any) -> None:
        twrap = self._get_instance_key(context, twrap)
        match context.scope:
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
        return InstantiatedResolver(interface, implementation or interface)

    def _get_service_resolver(
        self,
        interface: TWrap[Any],
        *,
        scope: InjectionScope = InjectionScope.IMMEDIATE,
    ) -> ServiceResolver[..., Any]:
        if (annotated := get_annotated_resolver(interface, scope)) is not None:
            return annotated
        if (resolv_meta := get_custom_resolver(interface)) is not None:
            return resolv_meta
        if self._services.is_registered(interface):
            return self._services.get_resolver(interface)
        if self._has_instance(interface):
            return self._make_instantiated_resolver(interface)
        raise ServiceNotFoundError(str(interface))

    def _get_function_resolver(self, fwrap: FWrap[..., Any]) -> ServiceResolver[..., Any]:
        if (resolv_meta := get_custom_resolver(fwrap)) is not None:
            return resolv_meta
        return FunctionResolver(InjectionScope.IMMEDIATE, fwrap)

    def _get_storage_key(self, context: InjectionContext, dep_node: DependencyTreeNode[..., Any]) -> TWrap[Any] | None:
        if dep_node.registered is None or context.scope not in (InjectionScope.SINGLETON, InjectionScope.SCOPED):
            return None
        return self._get_instance_key(context, dep_node.registered)

    def _build_dependency_tree(
        self,
        context: InjectionContext,
        resolver: ServiceResolver[..., Any],
    ) -> DependencyTreeNode[..., Any]:
        self._enter_circular_guard(context, resolver)

        context = self._with_singleton_owner(context, resolver)

        args: list[DependencyTreeNode[..., Any]] = []
        kwargs: dict[str, DependencyTreeNode[..., Any]] = {}
        hints = resolver.get_resolution_hints(context)

        if context.positional_args is not None:
            skip = len(context.positional_args)
        else:
            skip = 0

        for param_name, param in resolver.get_resolution_signature().parameters.items():
            if skip > 0:
                skip -= 1
                continue

            if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
                continue
            if param_name not in hints:
                raise MissingTypeHintError(param_name, resolver.name)
            hint = hints[param_name]

            if isinstance(hint, ServiceResolver):
                hint_resolver = hint
                hint = hint_resolver.required
            else:
                hint_resolver = self._get_service_resolver(hint, scope=context.scope)

            if (
                (owner := context.singleton_owner) is not None
                and hint_resolver.scope is InjectionScope.SCOPED
                and hint_resolver.registered is not None
            ):
                raise CaptiveDependencyError(
                    str(owner.required) if owner.required is not None else owner.name,
                    str(hint) if hint is not None else hint_resolver.name,
                )

            sub_call_ctx = CallerContext(param_name=param_name, caller=resolver.get_instance_function())
            dep_node = self._build_dependency_tree(
                context.new_required(hint_resolver.scope, hint, sub_call_ctx),
                hint_resolver,
            )
            if param.kind in (param.POSITIONAL_ONLY, param.POSITIONAL_OR_KEYWORD):
                args.append(dep_node)
            else:
                kwargs[param_name] = dep_node

        return DependencyTreeNode(
            scope=resolver.scope,
            args=args,
            kwargs=kwargs,
            resolver=resolver,
            required=context.required,
            registered=resolver.registered,
            caller_context=context.caller_context,
        )

    def _get_depends_on_services(self, interface: TWrap[Any]) -> Iterable[type[Any]]:
        return accumulate_meta_on_twrap(interface, ServiceDependencyMetadata.KEY, lambda: [])


service_collection_w = wrap_type(ServiceCollection)
injector_w = wrap_type(Injector)

import inspect
from abc import abstractmethod
from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from typing import Any, Self, cast, override

from peritype import FWrap, TWrap, wrap_func, wrap_type

from soupape._collection import ServiceCollection
from soupape._decorators import get_custom_resolver
from soupape._instances import InstancePoolStack
from soupape._resolvers import (
    CallerContextResolver,
    DependencyTreeNode,
    DictResolver,
    DirectInstanceResolver,
    FallbackRunnerResolver,
    FunctionResolver,
    InstantiatedResolver,
    ListResolver,
    RawTypeResolver,
    ResolutionContextResolver,
    ServiceResolver,
    WrappedTypeResolver,
)
from soupape._traits import FallbackResolver, get_annotated_resolver
from soupape._types import CallerContext, InjectionContext, InjectionScope, Injector
from soupape._utils import Absent, CircularGuard, ResolverCache
from soupape.errors import (
    CaptiveDependencyError,
    MissingTypeHintError,
    ScopedServiceNotAvailableError,
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
        self._cache = ResolverCache() if parent is None else parent._cache
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

    def _get_context(
        self,
        node: DependencyTreeNode[..., Any],
    ) -> InjectionContext:
        if node.context is None:
            node.context = InjectionContext(
                injector=self,
                origin=node.origin,
                scope=node.scope,
                required=node.required,
                caller_context=node.caller_context,
                node=node,
                require_within=self._require_within,
                call_within=self._call_within,
            )
        return node.context

    @property
    def is_root_injector(self) -> bool:
        return len(self._instance_pool) == 1

    def _enter_circular_guard(
        self,
        circular_guard: CircularGuard,
        required: TWrap[Any] | None,
        resolver: ServiceResolver[..., Any],
    ) -> None:
        if required is None:
            circular_guard.enter(resolver.get_instance_function())
        elif not isinstance(resolver, FallbackRunnerResolver):
            circular_guard.enter_type(required)

    def _get_generator_owner(self, node: DependencyTreeNode[..., Any]) -> Self:
        if node.singleton_owner is not None:
            return self._root
        return self

    @property
    @override
    def instances(self) -> InstancePoolStack:
        return self._instance_pool

    @property
    @override
    def services(self) -> ServiceCollection:
        return self._services

    def _has_instance(self, twrap: TWrap[Any]) -> bool:
        return twrap in self._instance_pool

    def _get_instance_key(self, required: TWrap[Any] | None, twrap: TWrap[Any]) -> TWrap[Any]:
        if twrap.contains_any:
            if required is not None:
                twrap = twrap.specialize_with(required)
            if twrap.contains_any:
                raise UnresolvedAnyTypeError(str(twrap))
        return twrap

    def _set_instance(self, node: DependencyTreeNode[..., Any], instance: Any) -> None:
        if node.registered is None:
            return
        twrap = self._get_instance_key(node.required, node.registered)
        match node.scope:
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
        fallbacks: Sequence[FallbackResolver],
        *,
        scope: InjectionScope = InjectionScope.IMMEDIATE,
        caller_context: CallerContext | None = None,
    ) -> ServiceResolver[..., Any]:
        if (annotated := get_annotated_resolver(interface, scope, self._cache)) is not None:
            return annotated
        if (resolv_meta := get_custom_resolver(interface, self._cache)) is not None:
            return resolv_meta
        if self._services.is_registered(interface):
            return self._services.get_resolver(interface)
        if self._has_instance(interface):
            return self._make_instantiated_resolver(interface)
        if caller_context is not None and caller_context.has_default_value:
            return self._with_fallbacks(fallbacks, DirectInstanceResolver(caller_context.default_value))
        if interface.nullable:
            return self._with_fallbacks(fallbacks, DirectInstanceResolver(None))
        return FallbackRunnerResolver(fallbacks)

    def _with_fallbacks(
        self,
        fallbacks: Sequence[FallbackResolver],
        fallthrough: ServiceResolver[..., Any],
    ) -> ServiceResolver[..., Any]:
        if not fallbacks:
            return fallthrough
        return FallbackRunnerResolver(fallbacks, fallthrough)

    def _get_function_resolver(self, fwrap: FWrap[..., Any]) -> ServiceResolver[..., Any]:
        if (resolv_meta := get_custom_resolver(fwrap, self._cache)) is not None:
            return resolv_meta
        return FunctionResolver(InjectionScope.IMMEDIATE, fwrap)

    def _get_storage_key(self, node: DependencyTreeNode[..., Any]) -> TWrap[Any] | None:
        if node.registered is None or node.scope not in (InjectionScope.SINGLETON, InjectionScope.SCOPED):
            return None
        return self._get_instance_key(node.required, node.registered)

    def _build_dependency_tree(
        self,
        resolver: ServiceResolver[..., Any],
        fallbacks: Sequence[FallbackResolver],
        *,
        required: TWrap[Any] | None,
        origin: TWrap[Any] | None,
        caller_context: CallerContext | None,
        parent: DependencyTreeNode[..., Any] | None,
        singleton_owner: ServiceResolver[..., Any] | None,
        circular_guard: CircularGuard,
        positional_args: list[Any] | None = None,
        named_args: dict[str, Any] | None = None,
    ) -> DependencyTreeNode[..., Any]:
        self._enter_circular_guard(circular_guard, required, resolver)
        if resolver.scope is InjectionScope.SINGLETON and resolver.registered is not None:
            singleton_owner = resolver

        node = DependencyTreeNode(
            scope=resolver.scope,
            args=[],
            kwargs={},
            resolver=resolver,
            required=required,
            registered=resolver.registered,
            origin=origin,
            caller_context=caller_context,
            singleton_owner=singleton_owner,
            trace=circular_guard.trace,
            parent=parent,
        )
        hints = resolver.get_resolution_hints(self._get_context(node))

        parameters = resolver.get_resolution_signature().parameters
        skip = len(positional_args) if positional_args is not None else 0
        named = named_args or {}
        self._check_named_args(resolver, parameters, skip, named)

        for param_name, param in parameters.items():
            if skip > 0:
                skip -= 1
                continue

            if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD) or param_name in named:
                continue
            if param_name not in hints:
                raise MissingTypeHintError(param_name, resolver.name)
            hint = hints[param_name]

            caller_context = CallerContext(
                param_name=param_name,
                caller=resolver.get_instance_function(),
                default_value=Absent() if param.default is param.empty else param.default,
            )

            if isinstance(hint, ServiceResolver):
                hint_resolver = hint
                hint = hint_resolver.required
            else:
                hint_resolver = self._get_service_resolver(
                    hint,
                    scope=resolver.scope,
                    caller_context=caller_context,
                    fallbacks=fallbacks,
                )

            if (
                singleton_owner is not None
                and hint_resolver.scope is InjectionScope.SCOPED
                and hint_resolver.registered is not None
            ):
                raise CaptiveDependencyError(
                    str(singleton_owner.required) if singleton_owner.required is not None else singleton_owner.name,
                    str(hint) if hint is not None else hint_resolver.name,
                )

            child = self._build_dependency_tree(
                hint_resolver,
                (),
                required=hint,
                origin=hint if hint is not None else origin,
                caller_context=caller_context,
                parent=node,
                singleton_owner=singleton_owner,
                circular_guard=circular_guard.copy(),
            )
            if param.kind in (param.POSITIONAL_ONLY, param.POSITIONAL_OR_KEYWORD):
                node.args.append(child)
            else:
                node.kwargs[param_name] = child

        return node

    def _check_named_args(
        self,
        resolver: ServiceResolver[..., Any],
        parameters: Mapping[str, inspect.Parameter],
        skip: int,
        named_args: dict[str, Any],
    ) -> None:
        if not named_args:
            return
        accepts_any_name = any(param.kind is param.VAR_KEYWORD for param in parameters.values())
        positional_names = set(list(parameters)[:skip])
        for name in named_args:
            param = parameters.get(name)
            if param is None:
                if not accepts_any_name:
                    raise TypeError(f"'{resolver.name}' got an unexpected named argument '{name}'")
            elif param.kind is param.POSITIONAL_ONLY:
                raise TypeError(f"'{resolver.name}' got positional-only argument '{name}' passed by name")
            elif name in positional_names:
                raise TypeError(f"'{resolver.name}' got multiple values for argument '{name}'")

    @abstractmethod
    def require[T](
        self,
        interface: type[T] | TWrap[T],
        *,
        fallbacks: Iterable[FallbackResolver] | None = None,
    ) -> T | Awaitable[T]: ...

    @abstractmethod
    def call[T](
        self,
        callable: Callable[..., T] | FWrap[..., T],
        *,
        positional_args: list[Any] | None = None,
        named_args: dict[str, Any] | None = None,
        fallbacks: Iterable[FallbackResolver] | None = None,
    ) -> T | Awaitable[T]: ...

    @abstractmethod
    def _require[T](
        self,
        interface: TWrap[T],
        circular_guard: CircularGuard,
        fallbacks: Sequence[FallbackResolver],
    ) -> T | Awaitable[T]: ...

    @abstractmethod
    def _call(
        self,
        fwrap: FWrap[..., Any],
        positional_args: list[Any],
        named_args: dict[str, Any],
        origin: TWrap[Any] | None,
        circular_guard: CircularGuard,
        fallbacks: Sequence[FallbackResolver],
    ) -> Any: ...

    def _require_within(
        self,
        interface: type[Any] | TWrap[Any],
        circular_guard: CircularGuard,
        fallbacks: Sequence[FallbackResolver],
    ) -> Any:
        twrap = interface if isinstance(interface, TWrap) else wrap_type(interface)
        return self._require(twrap, circular_guard, fallbacks)

    def _call_within(
        self,
        callable: Callable[..., Any] | FWrap[..., Any],
        positional_args: list[Any],
        named_args: dict[str, Any],
        origin: TWrap[Any] | None,
        circular_guard: CircularGuard,
        fallbacks: Sequence[FallbackResolver],
    ) -> Any:
        fwrap = cast(FWrap[..., Any], callable) if isinstance(callable, FWrap) else wrap_func(callable)
        return self._call(fwrap, positional_args, named_args, origin, circular_guard, fallbacks)


service_collection_w = wrap_type(ServiceCollection)
injector_w = wrap_type(Injector)

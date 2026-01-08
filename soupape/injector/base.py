from collections.abc import Generator
from typing import Any, Self

from peritype import TWrap

from soupape import ServiceCollection
from soupape.errors import MissingTypeHintError, ScopedServiceNotAvailableError, ServiceNotFoundError
from soupape.instances import InstancePoolStack
from soupape.resolvers import InstantiatedServiceResolver, RawTypeResolverFactory, WrappedTypeResolverFactory
from soupape.types import (
    InjectionContext,
    InjectionScope,
    Injector,
    ResolverCallArgs,
    ResolverMetadata,
    ServiceResolver,
    ServiceResolverFactory,
    TypeResolverMetadata,
)


class BaseInjector(Injector):
    def __init__(self, services: ServiceCollection, instance_pool: InstancePoolStack | None = None) -> None:
        self._services = services.copy()
        self._instance_pool = instance_pool if instance_pool is not None else InstancePoolStack()
        self._generators_to_close: list[Generator[Any]] = []
        self._register_common_resolvers()

    def _register_common_resolvers(self) -> None:
        if not self._services.is_registered(type[Any]):
            self._services.add_transient(RawTypeResolverFactory(), type[Any])
        if not self._services.is_registered(TWrap[Any]):
            self._services.add_transient(WrappedTypeResolverFactory(), TWrap[Any])

    def _get_injection_context(
        self,
        origin: TWrap[Any] | None,
        scope: InjectionScope,
        required: TWrap[Any] | None = None,
        positional_args: list[Any] | None = None,
    ) -> InjectionContext:
        return InjectionContext(self, origin, scope, required, positional_args)

    @property
    def is_root_injector(self) -> bool:
        return len(self._instance_pool) == 1

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

    def _get_instance[InstanceT](self, twrap: TWrap[InstanceT]) -> InstanceT:
        return self._instance_pool.get_instance(twrap)

    def _make_instantiated_resolver[T](
        self,
        interface: TWrap[T],
        implementation: TWrap[Any] | None = None,
    ) -> TypeResolverMetadata[..., Any]:
        resolver = InstantiatedServiceResolver(
            self._instance_pool,
            implementation if implementation is not None else interface,
        )
        return TypeResolverMetadata(
            InjectionScope.IMMEDIATE,
            InstantiatedServiceResolver.get_empty_signature(),
            InstantiatedServiceResolver.get_empty_func(),
            resolver,
            interface,
            implementation if implementation is not None else interface,
        )

    def _get_service_metadata(self, interface: TWrap[Any]) -> TypeResolverMetadata[..., Any]:
        if self._services.is_registered(interface):
            metadata = self._services.get_metadata(interface)
            interface = metadata.interface
            implementation = metadata.implementation
            if self._has_instance(implementation):
                return self._make_instantiated_resolver(interface, implementation)
            return metadata
        if self._has_instance(interface):
            return self._make_instantiated_resolver(interface)
        raise ServiceNotFoundError(str(interface))

    def _build_dependency_tree(
        self,
        context: InjectionContext,
        metadata: ResolverMetadata[..., Any] | TypeResolverMetadata[..., Any],
        *,
        required: TWrap[Any] | None = None,
    ) -> ResolverCallArgs[..., Any]:
        args: list[ResolverCallArgs[..., Any]] = []
        kwargs: dict[str, ResolverCallArgs[..., Any]] = {}
        hints = metadata.fwrap.get_signature_hints(belongs_to=context.origin)

        if context.positional_args is not None:
            skip = len(context.positional_args)
        else:
            skip = 0

        for param_name, param in metadata.signature.parameters.items():
            if skip > 0:
                skip -= 1
                continue
            if param_name not in hints:
                raise MissingTypeHintError(param_name, str(metadata.fwrap))
            hint = hints[param_name]
            hint_metadata = self._get_service_metadata(hint)
            resolver_args = self._build_dependency_tree(context, hint_metadata, required=hint)
            if param.kind in (param.POSITIONAL_ONLY, param.POSITIONAL_OR_KEYWORD):
                args.append(resolver_args)
            elif param.kind == param.KEYWORD_ONLY:
                kwargs[param_name] = resolver_args

        return ResolverCallArgs(
            metadata.scope,
            args,
            kwargs,
            metadata.resolver,
            required,
            metadata.implementation if isinstance(metadata, TypeResolverMetadata) else None,
        )

    def _get_resolver_from_call_args(
        self,
        context: InjectionContext,
        call_args: ResolverCallArgs[..., Any],
    ) -> ServiceResolver[..., Any]:
        if isinstance(call_args.resolver, ServiceResolverFactory):
            return call_args.resolver.__with_context__(context)
        return call_args.resolver

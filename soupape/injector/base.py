from typing import Any, Self

from peritype import TWrap

from soupape import ServiceCollection
from soupape.errors import MissingTypeHintError, ScopedServiceNotAvailableError, ServiceNotFoundError
from soupape.instances import InstancePoolStack
from soupape.resolver import ServiceResolverFactory
from soupape.types import (
    InjectionScope,
    Injector,
    InjectorCallArgs,
    ResolverCallArgs,
    ResolverMetadata,
    ServiceResolver,
    TypeResolverMetadata,
)


class BaseInjector(Injector):
    def __init__(self, services: ServiceCollection, instance_pool: InstancePoolStack | None = None) -> None:
        self._services = services.copy()
        self._instance_pool = instance_pool if instance_pool is not None else InstancePoolStack()

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

    def _get_service_metadata(self, interface: TWrap[Any]) -> TypeResolverMetadata[..., Any]:
        if not self._services.is_registered(interface):
            raise ServiceNotFoundError(str(interface))
        return self._services.get_metadata(interface)

    def _build_resolve_tree(
        self,
        metadata: ResolverMetadata[..., Any] | TypeResolverMetadata[..., Any],
        *,
        injector_args: InjectorCallArgs | None = None,
    ) -> ResolverCallArgs[..., Any]:
        args: list[ResolverCallArgs[..., Any]] = []
        kwargs: dict[str, ResolverCallArgs[..., Any]] = {}
        hints = metadata.fwrap.get_signature_hints()

        if injector_args is not None and "positional_args" in injector_args:
            skip = len(injector_args["positional_args"])
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
            resolver_args = self._build_resolve_tree(hint_metadata)
            if param.kind in (param.POSITIONAL_ONLY, param.POSITIONAL_OR_KEYWORD):
                args.append(resolver_args)
            elif param.kind == param.KEYWORD_ONLY:
                kwargs[param_name] = resolver_args

        return ResolverCallArgs(
            metadata.scope,
            args,
            kwargs,
            metadata.resolver,
            metadata.interface if isinstance(metadata, TypeResolverMetadata) else None,
        )

    def _get_resolver_from_call_args(self, call_args: ResolverCallArgs[..., Any]) -> ServiceResolver[..., Any]:
        if isinstance(call_args.resolver, ServiceResolverFactory):
            return call_args.resolver(self)  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        return call_args.resolver

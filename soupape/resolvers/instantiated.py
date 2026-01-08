import inspect

from peritype import FWrap, TWrap, wrap_func

from soupape.errors import ServiceNotFoundError
from soupape.instances import InstancePoolStack


def _empty_func() -> None: ...


_empty_func_w = wrap_func(_empty_func)


class InstantiatedServiceResolver[T]:
    def __init__(self, instances: InstancePoolStack, tw: TWrap[T]) -> None:
        self._instances = instances
        self._type = tw

    def __call__(self) -> T:
        if self._type not in self._instances:
            raise ServiceNotFoundError(str(self._type))
        return self._instances.get_instance(self._type)

    @staticmethod
    def get_empty_signature() -> inspect.Signature:
        return _empty_func_w.signature

    @staticmethod
    def get_empty_func() -> FWrap[[], None]:
        return _empty_func_w

from collections.abc import Iterator
from typing import Any

from peritype import TWrap
from peritype.collections import TypeMap


class InstancePool:
    def __init__(self) -> None:
        self._instances = TypeMap[Any, Any]()

    def __len__(self) -> int:
        return len(self._instances)

    def __contains__(self, twrap: TWrap[Any], /) -> bool:
        return twrap in self._instances

    def __iter__(self) -> Iterator[tuple[TWrap[Any], Any]]:
        yield from self._instances

    def set_instance(self, twrap: TWrap[Any], instance: Any) -> None:
        self._instances[twrap] = instance

    def get_instance[InstanceT](self, twrap: TWrap[InstanceT]) -> InstanceT:
        return self._instances[twrap]


class InstancePoolStack:
    def __init__(self, stack: list[InstancePool] | None = None) -> None:
        self._stack = stack if stack is not None else [InstancePool()]

    def __len__(self) -> int:
        return len(self._stack)

    def __iter__(self) -> Iterator[InstancePool]:
        return reversed(self._stack)

    @property
    def empty(self) -> bool:
        return len(self._stack) == 0

    def stack(self) -> "InstancePoolStack":
        return InstancePoolStack([*self._stack, InstancePool()])

    def __contains__(self, twrap: TWrap[Any], /) -> bool:
        for pool in self:
            if twrap in pool:
                return True
        return False

    def set_instance(self, twrap: TWrap[Any], instance: Any, root: bool = False) -> None:
        if self.empty:
            raise RuntimeError("No instance pool in stack to set instance.")
        self._stack[0 if root else -1].set_instance(twrap, instance)

    def get_instance[InstanceT](self, twrap: TWrap[InstanceT]) -> InstanceT:
        for pool in self:
            if twrap in pool:
                return pool.get_instance(twrap)
        raise KeyError(f"No instance found for type {twrap}.")

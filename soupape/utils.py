from typing import Any, TypeGuard, get_origin

from hafersack import Hafersack


def is_type_like(obj: Any) -> TypeGuard[type[Any]]:
    return isinstance(obj, type) or get_origin(obj) is not None


meta = Hafersack("soupape")

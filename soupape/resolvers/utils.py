from typing import Any

from peritype import TWrap, wrap_func, wrap_type


def _empty_func() -> None: ...


empty_func_w = wrap_func(_empty_func)
type_any_w = wrap_type(type[Any])
type_any_w_w = wrap_type(TWrap[Any])

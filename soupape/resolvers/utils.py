from typing import Any

from peritype import TWrap, wrap_type

type_any_w = wrap_type(type[Any])
type_any_w_w = wrap_type(TWrap[Any])
list_any_w = wrap_type(list[Any])
dict_str_any_w = wrap_type(dict[str, Any])

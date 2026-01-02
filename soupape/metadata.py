from typing import Any, Protocol, TypeGuard


class WithMetadata(Protocol):
    __soupape__: dict[str, Any]


class Matadata:
    @staticmethod
    def has_metadata(obj: object) -> TypeGuard[WithMetadata]:
        return hasattr(obj, "__soupape__")

    @staticmethod
    def set_metadata(obj: object) -> None:
        obj.__soupape__ = {}  # pyright: ignore[reportAttributeAccessIssue]

    @classmethod
    def has(cls, obj: object, key: str) -> bool:
        return cls.has_metadata(obj) and key in obj.__soupape__

    @classmethod
    def get(cls, obj: object, key: str) -> Any:
        if not cls.has_metadata(obj) or key not in obj.__soupape__:
            raise KeyError(f"Metadata key '{key}' not found in object {obj}.")
        return obj.__soupape__[key]

    @classmethod
    def set(cls, obj: object, key: str, value: Any) -> None:
        if not cls.has_metadata(obj):
            cls.set_metadata(obj)
        assert cls.has_metadata(obj)
        obj.__soupape__[key] = value


meta = Matadata()

__all__ = ["meta"]

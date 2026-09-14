from typing import Any, Protocol

from soupape._types import ResolutionContext


class FallbackResolver(Protocol):
    def supports(self, context: ResolutionContext) -> bool: ...

    def resolve(self, *args: Any, **kwargs: Any) -> Any: ...

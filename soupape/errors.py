class SoupapeError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message


class ServiceNotFoundError(SoupapeError):
    def __init__(self, interface: str) -> None:
        super().__init__(
            "soupape.service.not_found",
            f"Service for interface '{interface}' not found.",
        )


class MissingTypeHintError(SoupapeError):
    def __init__(self, parameter: str, fwrap: str) -> None:
        super().__init__(
            "soupape.type_hint.missing",
            f"Missing type hint for parameter '{parameter}' of '{fwrap}'.",
        )

"""Error types and canonical backend error codes.

Codes mirror the live NGX API v2 (authoritative sources: Cinder FC driver
api.py and the NFS CSI driver).
"""

from __future__ import annotations

import typing


class APIError(Exception):
    """A semantic backend error returned by the NGX API v2."""

    def __init__(
        self,
        status_code: int = 0,
        code: int = 0,
        message: str = "",
        method: str = "",
        endpoint: str = "",
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.method = method
        self.endpoint = endpoint
        super().__init__(self._format())

    def _format(self) -> str:
        if self.code:
            return (
                f"ngx api error: method={self.method} endpoint={self.endpoint} "
                f"http_status={self.status_code} code={self.code} message={self.message!r}"
            )
        return (
            f"ngx api error: method={self.method} endpoint={self.endpoint} "
            f"http_status={self.status_code} message={self.message!r}"
        )


class TransportError(Exception):
    """A network-level failure reaching the backend."""


class PoolNotFound(Exception):
    """The configured pool is absent on every required pool list."""


class ClusterNotReady(Exception):
    """Controller roles do not form a serviceable work mode."""


# Canonical backend error codes.
CODE_BUSY = 725
CODE_NOT_FOUND = 5011
CODE_ALREADY_EXISTS = 710
CODE_ATTACHED_BUSY = 534
CODE_IQN_NOT_FOUND = 521
CODE_IQN_EXISTS = 522
CODE_TARGET_DELETED = 611
CODE_UNAUTHORIZED = 5000


def classify_code(code: int) -> str:
    """Map a canonical NGX error code to a stable kind string."""
    if code == CODE_BUSY:
        return "busy"
    if code in (CODE_NOT_FOUND, CODE_IQN_NOT_FOUND, CODE_TARGET_DELETED):
        return "not_found"
    if code in (CODE_ALREADY_EXISTS, CODE_IQN_EXISTS):
        return "already_exists"
    if code == CODE_ATTACHED_BUSY:
        return "attached_busy"
    if code == CODE_UNAUTHORIZED:
        return "unauthorized"
    return "unknown"


def classify(err: Exception) -> typing.Optional[str]:
    """Return the stable kind for an APIError, or None for other errors."""
    if isinstance(err, APIError):
        return classify_code(err.code)
    return None


def is_not_found(err: Exception) -> bool:
    return classify(err) == "not_found"


def is_already_exists(err: Exception) -> bool:
    return classify(err) == "already_exists"


def is_busy(err: Exception) -> bool:
    return classify(err) == "busy"

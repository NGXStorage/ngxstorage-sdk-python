"""Error types and canonical backend error codes.

Codes mirror the live NGX API v2.
"""

from __future__ import annotations

import re
import typing


def _redact(text: str, secret: str) -> str:
    """Replace every occurrence of a configured secret with a marker."""
    if not secret:
        return text
    return text.replace(secret, "[REDACTED]")


_URL_USERINFO = re.compile(r"(?P<head>\b[a-z][a-z0-9+.-]*://)(?P<userinfo>[^/\s@]+)@")
_HOST_USERINFO = re.compile(r"(?P<userinfo>\b[^/\s@:]+:[^/\s@]+)@(?P<host>[^/\s]+)")


def _safe_endpoint(value: str) -> str:
    """Scrub URL userinfo (``user:pass@``) so credentials never reach a log.

    Handles both absolute URLs and bare ``user:pass@host`` controller
    spellings. Values without ``user:pass@`` credentials are returned
    unchanged (``john@doe.com`` is not a credential).
    """
    text = _URL_USERINFO.sub(r"\g<head>***@", str(value))
    return _HOST_USERINFO.sub(r"***@\g<host>", text)


def _redact_urls(text: str) -> str:
    """Scrub URL credentials inside free-form text (exception messages)."""
    return _safe_endpoint(text)


class APIError(Exception):
    """A semantic backend error returned by the NGX API v2.

    Raw response bodies are deliberately never retained: a server or proxy
    can echo request material (including the API key) in its error payload.
    """

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
        self.message = _redact_urls(message)
        self.method = method
        self.endpoint = _safe_endpoint(endpoint)
        super().__init__(self._format())

    def _format(self) -> str:
        if self.code:
            return (
                f"ngxstorage api error: method={self.method} endpoint={self.endpoint} "
                f"http_status={self.status_code} code={self.code} message={self.message!r}"
            )
        return (
            f"ngxstorage api error: method={self.method} endpoint={self.endpoint} "
            f"http_status={self.status_code} message={self.message!r}"
        )


class TransportError(Exception):
    """A network-level failure reaching the backend."""

    def __init__(self, message: str, method: str = "", endpoint: str = "") -> None:
        self.method = method
        self.endpoint = _safe_endpoint(endpoint)
        super().__init__(_redact_urls(message))


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

"""Pool service."""

from __future__ import annotations


def _bytes_to_int(value) -> int:
    """Convert a canonical NGX byte value (decimal string or number) to int.

    The backend declares capacity fields as strings; the SDK returns integers.
    """
    if value is None:
        return 0
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip()
    if not text:
        return 0
    try:
        return int(text)
    except (ValueError, TypeError):
        return 0


class PoolService:
    """Pool inventory and capacity reads."""

    def __init__(self, client) -> None:
        self._c = client

    def list(self) -> list:
        """Return the lightweight pool list."""
        return self._c.get("pool", None)

    def list_detail(self) -> list:
        """Return detailed pool records."""
        return self._c.get("pool", ["list"])

    def get(self, pool_id: str) -> dict:
        """Return one pool by id."""
        return self._c.get("pool", [pool_id])

    def overview(self) -> list:
        """Return the pool overview records (a bare array with a reduced
        field whitelist; entries lack the pool ``id``/``name``)."""
        return self._c.get("pool", ["overview"])

    def get_configured_capacity(self) -> tuple:
        """Return (available, reserved) bytes for the configured pool.

        Raises LookupError when the pool is absent from the capacity report.
        """
        pools = self._c.get("status", ["capacity"])
        for pool in pools:
            if pool.get("name") == self._c.pool_name:
                logical = pool.get("logical", {})
                return (_bytes_to_int(logical.get("available")),
                        _bytes_to_int(logical.get("reserved")))
        raise LookupError(f"configured pool {self._c.pool_name!r} capacity not found")

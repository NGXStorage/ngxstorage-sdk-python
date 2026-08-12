"""Pool service."""

from __future__ import annotations


class PoolService:
    def __init__(self, client) -> None:
        self._c = client

    def list(self) -> list:
        return self._c.get("pool", ["list"])

    def get(self, pool_id: str) -> dict:
        return self._c.get("pool", [pool_id])

    def overview(self) -> dict:
        return self._c.get("pool", ["overview"])

    def get_configured_capacity(self) -> tuple:
        pools = self._c.get("status", ["capacity"])
        for pool in pools:
            if pool.get("name") == self._c.pool_name:
                logical = pool.get("logical", {})
                return logical.get("available", 0), logical.get("reserved", 0)
        raise LookupError(f"configured pool {self._c.pool_name!r} capacity not found")

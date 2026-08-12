"""LUN (block volume) service."""

from __future__ import annotations

import typing

from ngxstorage.errors import is_not_found


class LUNService:
    def __init__(self, client) -> None:
        self._c = client

    def create(self, name: str, size_gb: int, owner: str = "1") -> dict:
        body = {
            "pool_name": self._c.pool_name,
            "name": name,
            "size": size_gb,
            "sing": "G",
            "owner": owner,
        }
        return self._c.mutate("POST", "lun", None, body)

    def get(self, lun_id: str) -> dict:
        return self._c.get("lun", [lun_id])

    def list(self) -> list:
        return self._c.get("lun", ["list"])

    def delete(self, lun_id: str) -> None:
        try:
            self._c.mutate("DELETE", "lun", [lun_id], None)
        except Exception as exc:
            if is_not_found(exc):
                return
            raise

    def modify(self, lun_id: str, fields: dict) -> None:
        self._c.mutate("PATCH", "lun", [lun_id], fields)

    def expand(self, lun_id: str, size_gb: int) -> None:
        self.modify(lun_id, {"size": size_gb, "sing": "G"})

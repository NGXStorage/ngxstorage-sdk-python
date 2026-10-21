"""LUN (block volume) service."""

from __future__ import annotations

import typing

from ngxstorage.errors import is_not_found


class LUNService:
    """LUN (block volume) lifecycle on the configured pool."""

    def __init__(self, client) -> None:
        self._c = client

    def create(self, name: str, size_gb: int, *, blocksize: typing.Optional[str] = None,
               deduplication: typing.Optional[str] = None,
               compression: typing.Optional[str] = None,
               thin_provision: typing.Optional[str] = None,
               io_type: typing.Optional[str] = None,
               qos_priority: typing.Optional[int] = None,
               quantity: typing.Optional[int] = None) -> dict:
        """Create a LUN and return the created record from the response."""
        if not name:
            raise ValueError("ngxstorage: LUN name is required")
        if size_gb <= 0:
            raise ValueError("ngxstorage: LUN size must be positive")
        # The LUN create body is pool_name, name, size plus optional sing,
        # blocksize, deduplication, compression, thin_provision, io_type,
        # qos_priority, quantity; owner is not a create field.
        body = {
            "pool_name": self._c.pool_name,
            "name": name,
            "size": size_gb,
            "sing": "G",
        }
        optional = {
            "blocksize": blocksize,
            "deduplication": deduplication,
            "compression": compression,
            "thin_provision": thin_provision,
            "io_type": io_type,
            "qos_priority": qos_priority,
            "quantity": quantity,
        }
        for key, value in optional.items():
            if value is not None:
                body[key] = value
        data = self._c.mutate("POST", "lun", None, body)
        # The create response carries the created LUN in a "luns" array.
        if isinstance(data, dict):
            luns = data.get("luns") or []
            if luns:
                return luns[0]
        raise LookupError("ngxstorage: create LUN returned no LUN")

    def get(self, lun_id: str) -> dict:
        """Return one LUN by id."""
        return self._c.get("lun", [lun_id])

    def list(self) -> list:
        """Return the lightweight LUN list."""
        return self._c.get("lun", ["list"])

    def delete(self, lun_id: str) -> None:
        """Delete a LUN; not-found is a no-op."""
        try:
            self._c.mutate("DELETE", "lun", [lun_id], None)
        except Exception as exc:
            if is_not_found(exc):
                return
            raise

    def modify(self, lun_id: str, fields: dict) -> None:
        """Patch selected fields of an existing LUN."""
        self._c.mutate("PATCH", "lun", [lun_id], fields)

    def expand(self, lun_id: str, increment_gb: int) -> None:
        """Grow a LUN by ``increment_gb`` GiB.

        The backend LUN modify contract interprets ``size`` as an additive
        increment over the current capacity, not an absolute target. Callers
        with an absolute desired size must pass target-minus-current.
        """
        self.modify(lun_id, {"size": increment_gb, "sing": "G"})

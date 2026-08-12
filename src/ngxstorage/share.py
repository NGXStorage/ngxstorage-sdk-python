"""Share (NFS file volume) service."""

from __future__ import annotations

from ngxstorage.errors import is_not_found


class ShareService:
    def __init__(self, client) -> None:
        self._c = client

    def create(self, name: str, size_bytes: int, owner: str = "1") -> dict:
        body = {
            "pool_name": self._c.pool_name,
            "name": name,
            "size": size_bytes,
            "owner": owner,
        }
        return self._c.mutate("POST", "share", None, body)

    def get(self, share_id: str) -> dict:
        return self._c.get("share", [share_id])

    def list(self) -> list:
        return self._c.get("share", ["list"])

    def delete(self, share_id: str) -> None:
        try:
            self._c.mutate("DELETE", "share", [share_id], None)
        except Exception as exc:
            if is_not_found(exc):
                return
            raise

    def modify(self, share_id: str, fields: dict) -> None:
        self._c.mutate("PATCH", "share", [share_id], fields)

    def expand(self, share_id: str, size_bytes: int) -> None:
        self.modify(share_id, {"size": size_bytes})

    def set_export_enabled(self, share_id: str, enabled: bool) -> None:
        self.modify(share_id, {"nfs_export": enabled})

    def set_read_only(self, share_id: str, read_only: bool) -> None:
        self.modify(share_id, {"read_only": read_only})

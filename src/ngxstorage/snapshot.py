"""Snapshot service."""

from __future__ import annotations

from ngxstorage.errors import is_not_found


class SnapshotService:
    def __init__(self, client) -> None:
        self._c = client

    def create(self, volume_id: str, name: str) -> dict:
        return self._c.mutate("POST", "snapshot", None, {"name": name, "volume_id": volume_id})

    def get(self, snap_id: str) -> dict:
        return self._c.get("snapshot", [snap_id])

    def list(self) -> list:
        return self._c.get("snapshot", None)

    def list_detail(self, volume_id: typing.Optional[str] = None) -> list:
        """Detailed snapshots from /api/v2/snapshot/list, optionally filtered
        by one source volume ID (NFS CSI / Cinder NFS snapshot restore)."""
        query = {"volume_id": volume_id} if volume_id else None
        return self._c.get("snapshot", ["list"], query)

    def delete(self, snap_id: str) -> None:
        try:
            self._c.mutate("DELETE", "snapshot", [snap_id], None)
        except Exception as exc:
            if is_not_found(exc):
                return
            raise

    def clone(self, snap_id: str, new_name: str) -> str:
        data = self._c.mutate("POST", "snapshot/clone", [snap_id], {"name": new_name})
        return data["volume_id"]

    def restore(self, snap_id: str) -> None:
        self._c.mutate("POST", "snapshot/restore", [snap_id], {"confirm": "true"})

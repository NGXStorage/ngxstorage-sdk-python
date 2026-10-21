"""Snapshot service."""

from __future__ import annotations

import typing

from ngxstorage.errors import is_not_found


class SnapshotService:
    """Snapshot lifecycle, clone/restore, and schedules."""

    def __init__(self, client) -> None:
        self._c = client

    def create(self, volume_id: str, name: str) -> dict:
        """Create a snapshot of a volume."""
        return self._c.mutate("POST", "snapshot", None, {"name": name, "volume_id": volume_id})

    def get(self, snap_id: str) -> dict:
        """Return one snapshot by id."""
        return self._c.get("snapshot", [snap_id])

    def list(self) -> list:
        """Return the lightweight snapshot list."""
        return self._c.get("snapshot", None)

    def list_detail(self, volume_id: typing.Optional[str] = None) -> list:
        """Detailed snapshots from /api/v2/snapshot/list, optionally filtered
        by one source volume ID."""
        query = {"volume_id": volume_id} if volume_id else None
        return self._c.get("snapshot", ["list"], query)

    def delete(self, snap_id: str) -> None:
        """Delete a snapshot; not-found is a no-op."""
        try:
            self._c.mutate("DELETE", "snapshot", [snap_id], None)
        except Exception as exc:
            if is_not_found(exc):
                return
            raise

    def clone(self, snap_id: str, new_name: str) -> str:
        """Clone a snapshot into a new volume; returns the new volume id."""
        data = self._c.mutate("POST", "snapshot/clone", [snap_id], {"name": new_name})
        return data["volume_id"]

    def restore(self, snap_id: str) -> None:
        """Restore a snapshot over its source volume (requires confirmation)."""
        self._c.mutate("POST", "snapshot/restore", [snap_id], {"confirm": "true"})

    def delete_all(self, volume_id: str) -> None:
        """Delete every snapshot of a volume; not-found is a no-op."""
        try:
            self._c.mutate("DELETE", "snapshot/all", [volume_id], None)
        except Exception as exc:
            if is_not_found(exc):
                return
            raise

    def get_schedule(self, volume_id: str) -> dict:
        """Return the snapshot schedule of a volume."""
        return self._c.get("snapshot", ["schedule", volume_id])

    def create_schedule(self, volume_id: str, schedule: dict) -> dict:
        """Create or replace a volume's snapshot schedule."""
        return self._c.mutate("POST", "snapshot/schedule", [volume_id], schedule)

    def delete_schedule(self, volume_id: str) -> None:
        """Delete a volume's snapshot schedule; not-found is a no-op."""
        try:
            self._c.mutate("DELETE", "snapshot/schedule", [volume_id], None)
        except Exception as exc:
            if is_not_found(exc):
                return
            raise

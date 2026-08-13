"""Share (NFS file volume) service.

Field names mirror the canonical NFS contract (NFS CSI driver CODE_RULES
section 11): reads use nested ``capacity.soft_quota`` and
``exports.nfs.enabled``/``read_only``, while writes use flat ``soft_quota``,
``nfs_export``, and ``nfs_read_only``.
"""

from __future__ import annotations

from ngxstorage.errors import is_not_found


class ShareService:
    def __init__(self, client) -> None:
        self._c = client

    def create(self, name: str, soft_quota_bytes: int, **attrs) -> dict:
        """Provision a share with its NFS export disabled.

        SHARE_CREATE acknowledges success without returning the canonical id,
        so the created share ID is resolved from the lightweight list.
        """
        body = {
            "pool_name": self._c.pool_name,
            "name": name,
            "soft_quota": soft_quota_bytes,
            "nfs_export": False,
        }
        body.update(attrs)
        self._c.mutate("POST", "share", None, body)

        for ref in self.list_names():
            if ref.get("name") == name:
                return ref
        raise LookupError(f"created share {name!r} is missing from the canonical list")

    def get(self, share_id: str) -> dict:
        return self._c.get("share", [share_id])

    def list(self) -> list:
        """Detailed share records (GET /api/v2/share/list)."""
        return self._c.get("share", ["list"])

    def list_names(self) -> list:
        """Lightweight share records (GET /api/v2/share) for ID resolution."""
        return self._c.get("share", None)

    def delete(self, share_id: str) -> None:
        try:
            self._c.mutate("DELETE", "share", [share_id], None)
        except Exception as exc:
            if is_not_found(exc):
                return
            raise

    def modify(self, share_id: str, fields: dict) -> None:
        self._c.mutate("PATCH", "share", [share_id], fields)

    def expand(self, share_id: str, soft_quota_bytes: int) -> None:
        """Grow a share through the canonical flat soft_quota byte field."""
        self.modify(share_id, {"soft_quota": soft_quota_bytes})

    def set_export_enabled(self, share_id: str, enabled: bool) -> None:
        self.modify(share_id, {"nfs_export": enabled})

    def set_read_only(self, share_id: str, read_only: bool) -> None:
        self.modify(share_id, {"nfs_read_only": read_only})

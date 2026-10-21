"""Share (NFS file volume) service.

Reads use nested ``capacity.soft_quota`` and ``exports.nfs.enabled`` /
``read_only``, while writes use flat ``soft_quota``, ``nfs_export``, and
``nfs_read_only``.
"""

from __future__ import annotations

from ngxstorage.errors import is_not_found


class ShareService:
    """NFS share lifecycle; reads use nested capacity/export fields."""

    def __init__(self, client) -> None:
        self._c = client

    def create(self, name: str, soft_quota_bytes: int, *, blocksize: str = "",
               flash_cache: bool = False, dram_cache: bool = False,
               deduplication: bool = False, compression: bool = False,
               flashtier_limit: str = "") -> dict:
        """Provision a share with its NFS export disabled.

        The backend acks with the canonical ``volume_id``, but the created
        share ID is still resolved from the lightweight list so a
        pre-existing same-name share resolves to its real identity. This
        method does not modify permissions; use ``modify`` separately.

        The create route only declares ``blocksize``, ``deduplication``, and
        ``compression``; an empty ``blocksize`` is omitted so the backend
        default (128k) applies, and the cache/flashtier attributes are applied
        with a follow-up modify using the canonical modify key names.
        """
        if not name:
            raise ValueError("ngxstorage: share name is required")
        if soft_quota_bytes <= 0:
            raise ValueError("ngxstorage: share soft quota must be a positive byte value")
        body = {
            "pool_name": self._c.pool_name,
            "name": name,
            "soft_quota": soft_quota_bytes,
            "deduplication": deduplication,
            "compression": compression,
            "nfs_export": False,
        }
        if blocksize:
            body["blocksize"] = blocksize
        self._c.mutate("POST", "share", None, body)

        share_id = ""
        for ref in self.list_names():
            if ref.get("name") == name:
                share_id = ref.get("id", "")
                break
        if not share_id:
            raise LookupError(f"created share {name!r} is missing from the canonical list")

        modify_fields = {}
        if flash_cache:
            modify_fields["flash_cache"] = True
        if dram_cache:
            modify_fields["dram_cache"] = True
        if flashtier_limit:
            modify_fields["flashtier_blocksize_limit"] = flashtier_limit
        if modify_fields:
            self.modify(share_id, modify_fields)

        return {
            "id": share_id,
            "name": name,
            "pool_name": self._c.pool_name,
            "blocksize": blocksize,
            "deduplication": "1" if deduplication else "",
            "compression": "1" if compression else "",
            "flash_cache": "1" if flash_cache else "",
            "dram_cache": "1" if dram_cache else "",
            "flashtier_limit": flashtier_limit,
        }

    def get(self, share_id: str) -> dict:
        """Return one share by id."""
        return self._c.get("share", [share_id])

    def list(self) -> list:
        """Detailed share records (GET /api/v2/share/list)."""
        return self._c.get("share", ["list"])

    def list_names(self) -> list:
        """Lightweight share records (GET /api/v2/share) for ID resolution."""
        return self._c.get("share", None)

    def delete(self, share_id: str) -> None:
        """Delete a share; not-found is a no-op."""
        try:
            self._c.mutate("DELETE", "share", [share_id], None)
        except Exception as exc:
            if is_not_found(exc):
                return
            raise

    def modify(self, share_id: str, fields: dict) -> None:
        """Patch selected fields of an existing share."""
        self._c.mutate("PATCH", "share", [share_id], fields)

    def expand(self, share_id: str, soft_quota_bytes: int) -> None:
        """Grow a share through the canonical flat soft_quota byte field."""
        self.modify(share_id, {"soft_quota": soft_quota_bytes})

    def set_export_enabled(self, share_id: str, enabled: bool) -> None:
        """Enable or disable the share's NFS export."""
        self.modify(share_id, {"nfs_export": enabled})

    def set_read_only(self, share_id: str, read_only: bool) -> None:
        """Set the share's NFS export to read-only or read-write."""
        self.modify(share_id, {"nfs_read_only": read_only})

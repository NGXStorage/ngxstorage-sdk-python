"""iSCSI target service.

Field values are returned exactly as the backend produces them (IQNs and LUN
numbers are strings). Interpretation is the driver's job.
"""

from __future__ import annotations

from ngxstorage.errors import is_already_exists, is_not_found


class ISCSITargetService:
    def __init__(self, client) -> None:
        self._c = client

    def list(self) -> list:
        return self._c.get("target/iscsi", ["list"])

    def get(self, target_id: str) -> dict:
        return self._c.get("target/iscsi", [target_id])

    def create(self, name: str, owner: str) -> dict:
        return self._c.mutate("POST", "target/iscsi", None, {"name": name, "owner": owner})

    def delete(self, target_id: str) -> None:
        try:
            self._c.mutate("DELETE", "target/iscsi", [target_id], None)
        except Exception as exc:
            if is_not_found(exc):
                return
            raise

    def add_lun(self, target_id: str, lun_id: str, owner: str) -> None:
        body = {"owner": owner, "lun_ids": [lun_id]}
        try:
            self._c.mutate("PUT", "target/iscsi/lun", [target_id], body)
        except Exception as exc:
            if is_already_exists(exc):
                return
            raise

    def remove_lun(self, target_id: str, lun_id: str, owner: str) -> None:
        body = {"owner": owner, "lun_ids": [lun_id]}
        try:
            self._c.mutate("PATCH", "target/iscsi/lun", [target_id], body)
        except Exception as exc:
            if is_not_found(exc):
                return
            raise

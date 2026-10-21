"""iSCSI target service.

Field values are returned exactly as the backend produces them (IQNs and LUN
numbers are strings). Interpretation is the driver's job.
"""

from __future__ import annotations

from ngxstorage.errors import is_already_exists, is_not_found


class ISCSITargetService:
    """iSCSI target lifecycle and configuration changes."""

    def __init__(self, client) -> None:
        self._c = client

    def list(self) -> list:
        """Return the lightweight target identity list."""
        return self._c.get("target/iscsi", None)

    def list_names(self) -> list:
        """Return the lightweight target identity list."""
        return self.list()

    def list_detail(self) -> list:
        """Return targets with their full configuration."""
        return self._c.get("target/iscsi", ["list"])

    def get(self, target_id: str) -> dict:
        """Return one iSCSI target by id."""
        return self._c.get("target/iscsi", [target_id])

    def create(self, name: str, auth_group_id: str, portal_group_id: str,
               owner: str = "") -> dict:
        """Create an iSCSI target and return the backend response."""
        # The backend requires auth_group_id and portal_group_id in addition
        # to name and owner.
        body = {
            "name": name,
            "auth_group_id": auth_group_id,
            "portal_group_id": portal_group_id,
            "owner": owner,
        }
        return self._c.mutate("POST", "target/iscsi", None, body)

    def delete(self, target_id: str) -> None:
        """Delete an iSCSI target; not-found is a no-op."""
        try:
            self._c.mutate("DELETE", "target/iscsi", [target_id], None)
        except Exception as exc:
            if is_not_found(exc):
                return
            raise

    def add_lun(self, target_id: str, lun_id: str, owner: str) -> None:
        """Map LUNs to an iSCSI target; already-mapped LUNs are ignored."""
        body = {"owner": owner, "lun_ids": [lun_id]}
        try:
            self._c.mutate("PUT", "target/iscsi/lun", [target_id], body)
        except Exception as exc:
            if is_already_exists(exc):
                return
            raise

    def remove_lun(self, target_id: str, lun_id: str, owner: str) -> None:
        """Unmap a LUN from an iSCSI target; not-found is a no-op."""
        body = {"owner": owner, "lun_ids": [lun_id]}
        try:
            self._c.mutate("PATCH", "target/iscsi/lun", [target_id], body)
        except Exception as exc:
            if is_not_found(exc):
                return
            raise

    def change_name(self, target_id: str, name: str, owner: str) -> None:
        """Rename an iSCSI target."""
        self._c.mutate("PATCH", "target/iscsi", [target_id], {"name": name, "owner": owner})

    def change_auth_group(self, target_id: str, auth_group_id: str, owner: str) -> None:
        """Rebind an iSCSI target to another auth group."""
        self._c.mutate(
            "PATCH", "target/iscsi/auth_group", [target_id],
            {"auth_group_id": auth_group_id, "owner": owner},
        )

    def change_portal_group(self, target_id: str, portal_group_id: str, owner: str) -> None:
        """Rebind an iSCSI target to another portal group."""
        self._c.mutate(
            "PATCH", "target/iscsi/portal_group", [target_id],
            {"portal_group_id": portal_group_id, "owner": owner},
        )

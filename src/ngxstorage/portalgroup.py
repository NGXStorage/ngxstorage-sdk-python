"""Portal group (iSCSI) service."""

from __future__ import annotations

from ngxstorage.errors import is_not_found


class PortalGroupService:
    def __init__(self, client) -> None:
        self._c = client

    def list(self) -> list:
        return self._c.get("portal_group", None)

    def get(self, group_id: str) -> dict:
        return self._c.get("portal_group", [group_id])

    def create(self, name: str, owner: str) -> None:
        self._c.mutate("POST", "portal_group", None, {"name": name, "owner": owner})

    def delete(self, group_id: str) -> None:
        try:
            self._c.mutate("DELETE", "portal_group", [group_id], None)
        except Exception as exc:
            if is_not_found(exc):
                return
            raise

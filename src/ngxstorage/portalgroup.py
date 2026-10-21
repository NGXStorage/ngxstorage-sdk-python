"""Portal group (iSCSI) service.

Portal groups are read-only in API v2: the backend exposes only the list,
detail list, and detail routes.
"""

from __future__ import annotations

from ngxstorage.errors import is_not_found


class PortalGroupService:
    """Portal group access for iSCSI targets.

    Portal groups are read-only in API v2: the backend exposes only the list,
    detail list, and detail routes. ``create`` and ``delete`` are retained for
    released v1.0.0 compatibility but always fail with 5012.
    """

    def __init__(self, client) -> None:
        self._c = client

    def list(self) -> list:
        """Return the lightweight portal group list (id, name, owner)."""
        return self._c.get("portal_group", None)

    def list_detail(self) -> list:
        """Return portal groups with their listen_ips documents."""
        return self._c.get("portal_group", ["list"])

    def get(self, group_id: str) -> dict:
        """Return one portal group by id."""
        return self._c.get("portal_group", [group_id])

    def create(self, name: str, owner: str) -> None:
        """Create a portal group.

        .. deprecated:: The deployed API has no portal-group create route;
        the request returns 5012 (unknown operation). Retained unchanged for
        released v1.0.0 runtime compatibility only.
        """
        self._c.mutate("POST", "portal_group", None, {"name": name, "owner": owner})

    def delete(self, group_id: str) -> None:
        """Delete a portal group.

        .. deprecated:: The deployed API has no portal-group delete route;
        the request returns 5012 (unknown operation). Retained unchanged for
        released v1.0.0 runtime compatibility only.
        """
        try:
            self._c.mutate("DELETE", "portal_group", [group_id], None)
        except Exception as exc:
            if is_not_found(exc):
                return
            raise

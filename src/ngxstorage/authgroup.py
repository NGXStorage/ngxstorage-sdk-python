"""Auth group (iSCSI CHAP) service."""

from __future__ import annotations

from ngxstorage.errors import is_already_exists, is_not_found


class AuthGroupService:
    """Auth group lifecycle plus CHAP and IQN membership."""

    def __init__(self, client) -> None:
        self._c = client

    def create(self, name: str, owner: str) -> str:
        """Create an auth group and return its numeric id as a string."""
        data = self._c.mutate("POST", "auth_group", None, {"name": name, "owner": owner})
        return str(data.get("id", ""))

    def get(self, group_id: str) -> dict:
        """Return one auth group by id."""
        return self._c.get("auth_group", [group_id])

    def list(self) -> list:
        """Return the lightweight auth group list."""
        return self._c.get("auth_group", None)

    def list_detail(self) -> list:
        """Return detailed auth group records."""
        return self._c.get("auth_group", ["list"])

    def delete(self, group_id: str) -> None:
        """Delete an auth group; a not-found response means it is already gone."""
        try:
            self._c.mutate("DELETE", "auth_group", [group_id], None)
        except Exception as exc:
            if is_not_found(exc):
                return
            raise

    def add_chap(self, group_id: str, username: str, password: str) -> None:
        """Set the CHAP username/password on an auth group (password never logged)."""
        # The password is never logged by the SDK.
        self._c.mutate("PATCH", "auth_group/chap", [group_id], {"username": username, "password": password})

    def delete_chap(self, group_id: str) -> None:
        """Clear the CHAP credentials of an auth group; not-found is a no-op."""
        try:
            self._c.mutate("DELETE", "auth_group/chap", [group_id], None)
        except Exception as exc:
            if is_not_found(exc):
                return
            raise

    def add_iqn(self, group_id: str, iqn: str, alias: str, owner: str) -> dict:
        """Authorize an IQN for iSCSI login and return the created record.

        Returns an empty dict when the IQN is already registered.
        """
        # The backend authorizes iSCSI logins only for registered IQNs; without
        # this, login fails with error 24 (authorization failure). The alias
        # is required by the backend. Returns the created IQN record so the
        # caller can track the IQN ID for later removal.
        try:
            return self._c.mutate(
                "PATCH", "auth_group/iqn", [group_id],
                {"owner": owner, "iqn": iqn, "alias": alias},
            )
        except Exception as exc:
            if is_already_exists(exc):
                return {}
            raise

    def delete_iqn(self, iqn_id: str) -> None:
        """Remove an authorized IQN; not-found is a no-op."""
        try:
            self._c.mutate("DELETE", "auth_group/iqn", [iqn_id], None)
        except Exception as exc:
            if is_not_found(exc):
                return
            raise

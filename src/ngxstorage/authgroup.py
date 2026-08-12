"""Auth group (iSCSI CHAP) service."""

from __future__ import annotations

from ngxstorage.errors import is_not_found


class AuthGroupService:
    def __init__(self, client) -> None:
        self._c = client

    def create(self, name: str, owner: str) -> str:
        data = self._c.mutate("POST", "auth_group", None, {"name": name, "owner": owner})
        return data.get("id", "")

    def get(self, group_id: str) -> dict:
        return self._c.get("auth_group", [group_id])

    def list(self) -> list:
        return self._c.get("auth_group", None)

    def delete(self, group_id: str) -> None:
        try:
            self._c.mutate("DELETE", "auth_group", [group_id], None)
        except Exception as exc:
            if is_not_found(exc):
                return
            raise

    def add_chap(self, group_id: str, username: str, password: str) -> None:
        # The password is never logged by the SDK.
        self._c.mutate("PATCH", "auth_group/chap", [group_id], {"username": username, "password": password})

    def delete_chap(self, group_id: str) -> None:
        try:
            self._c.mutate("DELETE", "auth_group/chap", [group_id], None)
        except Exception as exc:
            if is_not_found(exc):
                return
            raise

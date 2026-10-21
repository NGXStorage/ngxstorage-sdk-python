"""Fibre Channel target service.

Field values are returned exactly as the backend produces them (WWPNs retain
the "naa." prefix; LUN numbers are strings). Interpretation is the driver's
job.
"""

from __future__ import annotations

from ngxstorage.errors import is_already_exists, is_not_found


class FCTargetService:
    """Fibre Channel target management (raw backend field values)."""

    def __init__(self, client) -> None:
        self._c = client

    def list(self) -> list:
        """Return the lightweight target identity list."""
        return self._c.get("target/fc", None)

    def list_names(self) -> list:
        """Return the lightweight target identity list."""
        return self.list()

    def list_detail(self) -> list:
        """Return targets including ports and LUN mappings."""
        return self._c.get("target/fc", ["list"])

    def get(self, target_id: str) -> dict:
        """Return one FC target with ports and LUN mappings."""
        return self._c.get("target/fc", [target_id])

    def add_lun(self, target_id: str, lun_id: str, owner: str) -> None:
        """Map LUNs to an FC target; already-mapped LUNs are ignored."""
        body = {"owner": owner, "lun_ids": [lun_id]}
        try:
            self._c.mutate("PUT", "target/fc/lun", [target_id], body)
        except Exception as exc:
            if is_already_exists(exc):
                return
            raise

    def remove_lun(self, target_id: str, lun_id: str, owner: str) -> None:
        """Unmap a LUN from an FC target; not-found is a no-op."""
        body = {"owner": owner, "lun_ids": [lun_id]}
        try:
            self._c.mutate("PATCH", "target/fc/lun", [target_id], body)
        except Exception as exc:
            if is_not_found(exc):
                return
            raise

    def list_initiator_tags(self) -> list:
        """Return the FC initiator tag list."""
        return self._c.get("target/fc", ["initiator", "tag"])

    def create_initiator_tag(self, initiator_naa: str, tag: str) -> dict:
        """Create an FC initiator tag for one initiator NAA (zoning alias).

        The backend contract is ``initiator_naa`` (16 hex chars, no prefix)
        plus ``tag`` (the alias name); it returns ``{id, initiator_naa, tag}``.
        """
        return self._c.mutate(
            "POST", "target/fc/initiator", ["tag"],
            {"initiator_naa": initiator_naa, "tag": tag},
        )

    def get_initiator_tag(self, tag_id: str) -> dict:
        """Return one initiator tag by id."""
        return self._c.get("target/fc", ["initiator", "tag", tag_id])

    def delete_initiator_tag(self, tag_id: str) -> None:
        """Delete an initiator tag; not-found is a no-op."""
        try:
            self._c.mutate("DELETE", "target/fc/initiator", ["tag", tag_id], None)
        except Exception as exc:
            if is_not_found(exc):
                return
            raise

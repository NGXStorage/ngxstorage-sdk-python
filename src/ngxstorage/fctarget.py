"""Fibre Channel target service."""

from __future__ import annotations

from ngxstorage.errors import is_already_exists, is_not_found


class FCTargetService:
    def __init__(self, client) -> None:
        self._c = client

    def list(self) -> list:
        return self._c.get("target/fc", ["list"])

    def get(self, target_id: str) -> dict:
        return self._c.get("target/fc", [target_id])

    def _strip_naa(self, wwpn: str) -> str:
        return wwpn[4:] if wwpn.startswith("naa.") else wwpn

    def get_wwpns(self, target_id: str) -> list:
        """Return deduplicated target WWPNs with the 'naa.' prefix stripped."""
        target = self.get(target_id)
        seen = set()
        wwpns = []
        for port in target.get("ports", []):
            for w in port.get("wwpns", []):
                clean = self._strip_naa(w.get("wwpn", ""))
                if clean and clean not in seen:
                    seen.add(clean)
                    wwpns.append(clean)
        return wwpns

    def get_lun_number(self, target_id: str, lun_id: str) -> int:
        target = self.get(target_id)
        for lun in target.get("luns", []):
            if lun.get("id") == lun_id:
                return int(lun["number"])
        raise LookupError(f"LUN {lun_id} not mapped to target {target_id}")

    def add_lun(self, target_id: str, lun_id: str, owner: str) -> None:
        body = {"owner": owner, "lun_ids": [lun_id]}
        try:
            self._c.mutate("PUT", "target/fc/lun", [target_id], body)
        except Exception as exc:
            if is_already_exists(exc):
                return
            raise

    def remove_lun(self, target_id: str, lun_id: str, owner: str) -> None:
        body = {"owner": owner, "lun_ids": [lun_id]}
        try:
            self._c.mutate("PATCH", "target/fc/lun", [target_id], body)
        except Exception as exc:
            if is_not_found(exc):
                return
            raise

    def select_by_name(self, name: str) -> str:
        for target in self.list():
            if target.get("name") == name:
                return target["id"]
        raise LookupError(f"FC target {name!r} not found")

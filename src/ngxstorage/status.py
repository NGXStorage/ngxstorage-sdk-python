"""Status service (cluster, services, capacity, iops, bandwidth)."""

from __future__ import annotations


class StatusService:
    def __init__(self, client) -> None:
        self._c = client

    def cluster(self) -> dict:
        return self._c.get("status", ["cluster"])

    def services(self) -> dict:
        return self._c.get("status", ["services"])

    def capacity(self) -> list:
        return self._c.get("status", ["capacity"])

    def iops(self) -> dict:
        return self._c.get("status", ["iops"])

    def bandwidth(self) -> dict:
        return self._c.get("status", ["bandwidth"])

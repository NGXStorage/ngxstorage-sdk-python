"""Status service (cluster, services, capacity, iops, bandwidth, cache, cpu,
enclosures, license, overloaded volumes)."""

from __future__ import annotations


class StatusService:
    """Read-only status documents for cluster, services, and capacity."""

    def __init__(self, client) -> None:
        self._c = client

    def cluster(self) -> dict:
        """Return the cluster status document."""
        return self._c.get("status", ["cluster"])

    def services(self) -> dict:
        """Return the services status document."""
        return self._c.get("status", ["services"])

    def capacity(self) -> list:
        """Return per-pool capacity records."""
        return self._c.get("status", ["capacity"])

    def iops(self) -> dict:
        """Return the IOPS status document."""
        return self._c.get("status", ["iops"])

    def bandwidth(self) -> dict:
        """Return the bandwidth status document."""
        return self._c.get("status", ["bandwidth"])

    def cache(self) -> dict:
        """Return the cache status document."""
        return self._c.get("status", ["cache"])

    def cpu(self) -> dict:
        """Return the CPU status document."""
        return self._c.get("status", ["cpu"])

    def enclosures(self) -> list:
        """Return enclosure status records."""
        return self._c.get("status", ["enclosures"])

    def license(self) -> dict:
        """Return the license status document."""
        return self._c.get("status", ["license"])

    def overloaded_volumes(self) -> dict:
        """Return the overloaded-volumes document.

        The backend wraps the report: ``{"overloaded_volumes": [...],
        "last_check_time": <epoch>}``.
        """
        return self._c.get("status", ["overloaded_volumes"])

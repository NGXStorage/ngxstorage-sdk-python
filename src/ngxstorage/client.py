"""The NGX API v2 client: auth, TLS, retry, failover, middleware.

A single Client owns controller selection, bounded 725-busy retry, and
transport failover. TLS verification is optional and skips by default because
NGX Storage Arrays use self-signed certificates and most customers have no
private CA/DNS; pass ca_bundle to enforce a customer trust chain.
"""

from __future__ import annotations

import logging
import threading
import time
import typing
from dataclasses import dataclass, field

import requests

from ngxstorage.errors import (
    APIError,
    ClusterNotReady,
    CODE_BUSY,
    PoolNotFound,
    TransportError,
    _redact,
    _safe_endpoint,
)

logger = logging.getLogger("ngxstorage")


class BaseMiddleware:
    """Driver middleware hook. SDK composes a chain, outermost-first.

    A middleware overrides :meth:`send` and calls ``self.inner(request)`` to
    delegate to the next hop. ``inner`` is bound to the next middleware (or the
    SDK's ``session.send`` at the bottom of the chain).
    """

    def __init__(self, inner: typing.Optional[typing.Callable] = None) -> None:
        self.inner = inner

    def send(self, request: requests.PreparedRequest):
        """Forward a prepared request to the next hop in the chain."""
        if self.inner is None:
            raise RuntimeError("middleware has no inner hop")
        return self.inner(request)


@dataclass
class ClientConfig:
    """Configuration for NGXClient."""

    controllers: typing.List[str]
    api_key: str
    pool_name: str = ""
    insecure_skip_verify: bool = True  # NGX Storage Arrays are self-signed
    ca_bundle: typing.Optional[str] = None  # path to a customer CA bundle
    verify_hostname: bool = True
    middlewares: typing.List[BaseMiddleware] = field(default_factory=list)
    timeout: float = 60.0
    # max_retries bounds 725-busy attempts only. Transport failures are never
    # retried by the SDK: retry/backoff belongs to the caller or driver, and
    # safe GET/DELETE get at most one cross-controller replay.
    max_retries: int = 6
    base_delay: float = 10.0
    max_delay: float = 30.0

    def __repr__(self) -> str:  # pragma: no cover - safety guard
        return (
            f"ClientConfig(controllers={self.controllers!r}, api_key=[REDACTED], "
            f"pool_name={self.pool_name!r}, insecure_skip_verify={self.insecure_skip_verify})"
        )


class NGXClient:
    """Thread-safe entry point for the API v2 operations with current consumers
    and verified contracts."""

    API_VERSION = "api/v2"

    def __init__(self, config: ClientConfig, *, logger: typing.Optional[logging.Logger] = None) -> None:
        controllers = [controller.strip() for controller in config.controllers]
        if not controllers:
            raise ValueError("ngxstorage: at least one controller is required")
        if any(not controller for controller in controllers):
            raise ValueError("ngxstorage: controller must not be empty")
        if len(controllers) > 2:
            raise ValueError("ngxstorage: at most 2 controllers supported")
        if len(set(controllers)) != len(controllers):
            raise ValueError("ngxstorage: controllers must be unique")
        if not config.api_key:
            raise ValueError("ngxstorage: api key is required")

        self.config = config
        self.api_key = config.api_key
        self.logger = logger if logger is not None else logging.getLogger("ngxstorage")
        self.pool_name = config.pool_name
        self.controllers = controllers
        self.controller_index = 0
        self._refresh_lock = threading.RLock()

        # Timestamp of the last successful controller selection.
        self._last_refresh: float = 0.0

        self.session = requests.Session()
        # Optional TLS verification: default skip (self-signed NGX Storage
        # Arrays); a
        # ca_bundle enables verification against a customer trust chain.
        self.session.verify = bool(config.ca_bundle) if config.ca_bundle else not config.insecure_skip_verify
        if config.ca_bundle:
            self.session.verify = config.ca_bundle

        self._middlewares = config.middlewares
        self._lazy_services: typing.Dict[str, typing.Any] = {}
        self._send_chain = self._build_chain()

    def _build_chain(self):
        """Compose middleware into a single send callable, outermost-first."""
        def send(request):
            return self.session.send(request, timeout=self.config.timeout)

        chain = send
        for mw in reversed(self._middlewares):
            mw.inner = chain
            chain = mw.send
        return chain

    # -- internal request plumbing -------------------------------------------

    def current_controller(self) -> str:
        """Return the currently selected controller host."""
        with self._refresh_lock:
            return self.controllers[self.controller_index]

    def _publish_controller_selection(self, index: int) -> None:
        with self._refresh_lock:
            self.controller_index = index
            self._last_refresh = time.time()

    def _ensure_refresh(self) -> None:
        """Refresh a stale controller selection (5-minute TTL).

        A recovered controller or a pool that moved between controllers is
        picked up without waiting for an explicit failure. A failed refresh
        retains the previous selection.
        """
        with self._refresh_lock:
            now = time.time()
            if self._last_refresh and now - self._last_refresh < 300:
                return
            try:
                self.refresh_controller()
            except Exception as exc:  # retain previous selection on failure
                self.logger.warning("ngxstorage: periodic refresh failed (retaining selection): %s", exc)

    def _url(
        self,
        group: str,
        segments: typing.Optional[typing.List[str]] = None,
        query: typing.Optional[typing.Dict[str, str]] = None,
        controller: typing.Optional[str] = None,
    ) -> str:
        parts = ["https://", controller or self.current_controller(), "/", self.API_VERSION, "/", group]
        for seg in segments or []:
            parts.append("/")
            parts.append(str(seg))
        url = "".join(parts)
        if query:
            import urllib.parse

            url += "?" + urllib.parse.urlencode(query)
        return url

    def _request(
        self,
        method: str,
        group: str,
        segments: typing.Optional[typing.List[str]] = None,
        body: typing.Optional[dict] = None,
        query: typing.Optional[typing.Dict[str, str]] = None,
        controller: typing.Optional[str] = None,
    ) -> typing.Tuple[typing.Any, int]:
        """Perform a request with per-request selection refresh and a single
        transport-failover replay for safe methods (GET/DELETE).

        ``controller`` pins the request to a specific controller (used by
        controller probes); it never mutates the shared selection state, so
        concurrent requests cannot be misrouted while a probe is in flight.
        """
        self._ensure_refresh()
        url = self._url(group, segments, query, controller=controller)
        try:
            return self._request_once(method, url, body)
        except TransportError as transport_error:
            # Mutations are never replayed after an ambiguous transport
            # failure. Only GET/DELETE fail over once to the other controller.
            if controller is not None or method.upper() not in ("GET", "DELETE"):
                raise
            try:
                self.refresh_controller()
            except Exception as refresh_error:
                raise TransportError(
                    f"ngxstorage: refresh after transport failure: {refresh_error}",
                    method,
                    url,
                ) from transport_error
            url = self._url(group, segments, query, controller=controller)
            return self._request_once(method, url, body)

    def _request_once(
        self,
        method: str,
        url: str,
        body: typing.Optional[dict] = None,
    ) -> typing.Tuple[typing.Any, int]:
        # Connection: close -- NGX Storage Arrays close idle keep-alive connections
        # after a few seconds; a pooled session would replay the stale socket
        # and POST mutations would die with RemoteDisconnected. A fresh
        # connection per request removes that race entirely.
        headers = {"Authorization": "Bearer " + self.api_key, "Connection": "close"}

        response = None
        for attempt in range(1, self.config.max_retries + 1):
            req = requests.Request(method, url, json=body, headers=headers)
            prepared = self.session.prepare_request(req)
            try:
                response = self._send_chain(prepared)
            except requests.RequestException as exc:
                raise TransportError(str(exc), method, url) from exc

            body_text = response.text
            code, message = _response_error(body_text)
            # A server/proxy can echo request material in its error payload.
            message = _redact(message, self.api_key)

            if code == CODE_BUSY and attempt < self.config.max_retries:
                self.logger.warning("ngxstorage: pool busy (725), attempt %d/%d", attempt, self.config.max_retries)
                delay = min(self.config.base_delay * (2 ** (attempt - 1)), self.config.max_delay)
                time.sleep(delay)
                continue

            if response.status_code >= 400 or code != 0:
                raise APIError(response.status_code, code, message, method, url)

            try:
                return response.json(), response.status_code
            except ValueError as exc:
                raise APIError(
                    response.status_code, 0, "malformed response", method, url
                ) from exc

        raise APIError(0, CODE_BUSY, "retries exhausted", method, url)

    def get(
        self,
        group: str,
        segments: typing.Optional[typing.List[str]] = None,
        query: typing.Optional[typing.Dict[str, str]] = None,
        controller: typing.Optional[str] = None,
    ) -> typing.Any:
        """GET a resource and return the decoded JSON body."""
        data, _ = self._request("GET", group, segments, query=query, controller=controller)
        return data

    def mutate(
        self,
        method: str,
        group: str,
        segments: typing.Optional[typing.List[str]],
        body: typing.Optional[dict],
        query: typing.Optional[typing.Dict[str, str]] = None,
        controller: typing.Optional[str] = None,
    ) -> typing.Any:
        """Send a mutating request (POST/PUT/PATCH/DELETE) with an optional body."""
        data, _ = self._request(method, group, segments, body, query, controller=controller)
        return data

    # -- lazy service accessors ---------------------------------------------

    def _service(self, name: str, factory):
        if name not in self._lazy_services:
            self._lazy_services[name] = factory(self)
        return self._lazy_services[name]

    @property
    def luns(self):
        """Lazy LUN service accessor."""
        from ngxstorage.lun import LUNService
        return self._service("luns", LUNService)

    @property
    def shares(self):
        """Lazy share service accessor."""
        from ngxstorage.share import ShareService
        return self._service("shares", ShareService)

    @property
    def fc_targets(self):
        """Lazy Fibre Channel target service accessor."""
        from ngxstorage.fctarget import FCTargetService
        return self._service("fc_targets", FCTargetService)

    @property
    def iscsi_targets(self):
        """Lazy iSCSI target service accessor."""
        from ngxstorage.iscsitarget import ISCSITargetService
        return self._service("iscsi_targets", ISCSITargetService)

    @property
    def snapshots(self):
        """Lazy snapshot service accessor."""
        from ngxstorage.snapshot import SnapshotService
        return self._service("snapshots", SnapshotService)

    @property
    def pools(self):
        """Lazy pool service accessor."""
        from ngxstorage.pool import PoolService
        return self._service("pools", PoolService)

    @property
    def status(self):
        """Lazy status service accessor."""
        from ngxstorage.status import StatusService
        return self._service("status", StatusService)

    @property
    def auth_groups(self):
        """Lazy auth group service accessor."""
        from ngxstorage.authgroup import AuthGroupService
        return self._service("auth_groups", AuthGroupService)

    @property
    def portal_groups(self):
        """Lazy portal group service accessor."""
        from ngxstorage.portalgroup import PortalGroupService
        return self._service("portal_groups", PortalGroupService)

    def refresh_controller(self) -> None:
        """Serialize and run one controller discovery campaign."""
        with self._refresh_lock:
            self._discover_controller()

    def _discover_controller(self) -> None:
        """Resolve the NGX work mode and select the serving controller.

        Single-master, master-ready, and cluster modes are recognized; with a
        configured pool the controller whose pool list contains the pool is
        selected. A failed refresh preserves the previous selection. Raises
        PoolNotFound or ClusterNotReady on unusable state.
        """
        observations = []
        for index, ip in enumerate(self.controllers):
            observation = {"index": index, "ip": ip, "connected": False, "status": ""}
            try:
                cluster = self._cluster_status_for(ip)
                observation["status"] = cluster.get("status", "")
                if cluster.get("connected", 0) == 1:
                    observation["connected"] = True
            except Exception as exc:  # probe failure: controller not usable
                self.logger.warning("ngxstorage: cluster lookup failed for %s: %s", ip, exc)
            observations.append(observation)

        candidates = []
        mode = ""
        if len(observations) == 1:
            obs = observations[0]
            if obs["connected"] and obs["status"] == "Master":
                mode = "single-master"
                candidates = [obs["index"]]
        elif len(observations) == 2:
            a, b = observations
            if a["connected"] and b["connected"] and a["status"] == "Master" and b["status"] == "Ready":
                mode = "master-ready"
                candidates = [a["index"]]
            elif a["connected"] and b["connected"] and a["status"] == "Ready" and b["status"] == "Master":
                mode = "master-ready"
                candidates = [b["index"]]
            elif a["connected"] and b["connected"] and a["status"] == "Cluster" and b["status"] == "Cluster":
                mode = "cluster"
                candidates = [a["index"], b["index"]]

        if not candidates:
            raise ClusterNotReady("controllers do not form a serviceable work mode")

        if not self.pool_name:
            self._publish_controller_selection(candidates[0])
            self.logger.info(
                "ngxstorage: controller selected (%s): %s", mode, _safe_endpoint(self.current_controller())
            )
            return

        selected = -1
        for index in candidates:
            try:
                pools = self._pool_list_for(self.controllers[index])
            except Exception as exc:  # pool lookup failure: skip candidate
                self.logger.warning(
                    "ngxstorage: pool lookup failed for %s: %s", _safe_endpoint(self.controllers[index]), exc
                )
                continue
            for pool in pools:
                if pool.get("name") == self.pool_name or pool.get("id") == self.pool_name:
                    selected = index
                    break
            if selected != -1:
                break

        if selected == -1:
            raise PoolNotFound(f"configured pool {self.pool_name!r} not found")

        self._publish_controller_selection(selected)
        self.logger.info(
            "ngxstorage: controller selected (%s): %s", mode, _safe_endpoint(self.controllers[selected])
        )

    def _cluster_status_for(self, ip: str) -> dict:
        """Read the cluster status document from a specific controller IP.

        The request is pinned to ``ip`` without touching the shared
        controller selection, so concurrent requests keep using the selected
        controller while the probe is in flight.
        """
        data, _ = self._request_once("GET", self._url("status", ["cluster"], controller=ip))
        return data

    def _pool_list_for(self, ip: str) -> list:
        """Read the lightweight pool list from a specific controller IP."""
        data, _ = self._request_once("GET", self._url("pool", controller=ip))
        return data


def _response_error(body_text: str) -> typing.Tuple[int, str]:
    import json as _json

    if not body_text:
        return 0, ""
    try:
        parsed = _json.loads(body_text)
    except ValueError:
        return 0, ""
    if isinstance(parsed, dict):
        code = parsed.get("code", 0)
        msg = parsed.get("error", "")
        try:
            code = int(code)
        except (TypeError, ValueError):
            code = 0
        return code, str(msg)
    return 0, ""

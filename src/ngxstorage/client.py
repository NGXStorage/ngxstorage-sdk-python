"""The NGX API v2 client: auth, TLS, retry, failover, middleware.

Design mirrors the Go SDK (ngx-sdk-go): a single Client owns controller
selection, bounded 725-busy retry, and transport failover. TLS verification
is optional and skips by default because NGX appliances use self-signed
certificates and most customers have no private CA/DNS; pass ca_bundle to
enforce a customer trust chain.
"""

from __future__ import annotations

import logging
import time
import typing
from dataclasses import dataclass, field
from urllib.parse import urljoin

import requests

from ngxstorage.errors import (
    APIError,
    ClusterNotReady,
    CODE_BUSY,
    PoolNotFound,
    TransportError,
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
        if self.inner is None:
            raise RuntimeError("middleware has no inner hop")
        return self.inner(request)


@dataclass
class ClientConfig:
    """Configuration for NGXClient."""

    controllers: typing.List[str]
    api_key: str
    pool_name: str = ""
    insecure_skip_verify: bool = True  # NGX appliances are self-signed
    ca_bundle: typing.Optional[str] = None  # path to a customer CA bundle
    verify_hostname: bool = True
    middlewares: typing.List[BaseMiddleware] = field(default_factory=list)
    timeout: float = 60.0
    max_retries: int = 6
    base_delay: float = 10.0
    max_delay: float = 30.0

    def __repr__(self) -> str:  # pragma: no cover - safety guard
        return (
            f"ClientConfig(controllers={self.controllers!r}, api_key=[REDACTED], "
            f"pool_name={self.pool_name!r}, insecure_skip_verify={self.insecure_skip_verify})"
        )


class NGXClient:
    """Thread-safe entry point for all NGX API v2 operations."""

    API_VERSION = "api/v2"

    def __init__(self, config: ClientConfig) -> None:
        if not config.controllers:
            raise ValueError("ngx sdk: at least one controller is required")
        if len(config.controllers) > 2:
            raise ValueError("ngx sdk: at most 2 controllers supported")
        if not config.api_key:
            raise ValueError("ngx sdk: api key is required")

        self.config = config
        self.api_key = config.api_key
        self.pool_name = config.pool_name
        self.controllers = list(config.controllers)
        self.node_index = 0

        self.session = requests.Session()
        # Optional TLS verification: default skip (self-signed NGX); a
        # ca_bundle enables verification against a customer trust chain.
        self.session.verify = bool(config.ca_bundle) if config.ca_bundle else not config.insecure_skip_verify
        if config.ca_bundle:
            self.session.verify = config.ca_bundle

        self._middlewares = config.middlewares
        self._lazy_services: typing.Dict[str, typing.Any] = {}
        self._send_chain = self._build_chain()

    def _build_chain(self):
        """Compose middleware into a single send callable, outermost-first."""
        chain = self.session.send
        for mw in reversed(self._middlewares):
            mw.inner = chain
            chain = mw.send
        return chain

    # -- internal request plumbing -------------------------------------------

    def current_controller(self) -> str:
        return self.controllers[self.node_index]

    def _url(
        self,
        group: str,
        segments: typing.Optional[typing.List[str]] = None,
        query: typing.Optional[typing.Dict[str, str]] = None,
    ) -> str:
        parts = ["https://", self.current_controller(), "/", self.API_VERSION, "/", group]
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
        url: str,
        body: typing.Optional[dict] = None,
    ) -> typing.Tuple[typing.Any, int]:
        headers = {"Authorization": "Bearer " + self.api_key}

        response = None
        for attempt in range(1, self.config.max_retries + 1):
            req = requests.Request(method, url, json=body, headers=headers)
            prepared = self.session.prepare_request(req)
            try:
                response = self._send_chain(prepared)
            except requests.RequestException as exc:
                raise TransportError(str(exc)) from exc

            body_text = response.text
            code, message = _response_error(body_text)

            if code == CODE_BUSY and attempt < self.config.max_retries:
                logger.warning("ngx sdk: pool busy (725), attempt %d/%d", attempt, self.config.max_retries)
                delay = min(self.config.base_delay * (2 ** (attempt - 1)), self.config.max_delay)
                time.sleep(delay)
                continue

            if response.status_code >= 400 or code != 0:
                raise APIError(response.status_code, code, message, method, url)

            try:
                return response.json(), response.status_code
            except ValueError as exc:
                raise APIError(response.status_code, 0, "malformed response", method, url) from exc

        raise APIError(0, CODE_BUSY, "retries exhausted", method, url)

    def get(
        self,
        group: str,
        segments: typing.Optional[typing.List[str]] = None,
        query: typing.Optional[typing.Dict[str, str]] = None,
    ) -> typing.Any:
        data, _ = self._request("GET", self._url(group, segments, query))
        return data

    def mutate(
        self,
        method: str,
        group: str,
        segments: typing.Optional[typing.List[str]],
        body: typing.Optional[dict],
        query: typing.Optional[typing.Dict[str, str]] = None,
    ) -> typing.Any:
        data, _ = self._request(method, self._url(group, segments, query), body)
        return data

    # -- lazy service accessors ---------------------------------------------

    def _service(self, name: str, factory):
        if name not in self._lazy_services:
            self._lazy_services[name] = factory(self)
        return self._lazy_services[name]

    @property
    def luns(self):
        from ngxstorage.lun import LUNService
        return self._service("luns", LUNService)

    @property
    def shares(self):
        from ngxstorage.share import ShareService
        return self._service("shares", ShareService)

    @property
    def fc_targets(self):
        from ngxstorage.fctarget import FCTargetService
        return self._service("fc_targets", FCTargetService)

    @property
    def iscsi_targets(self):
        from ngxstorage.iscsitarget import ISCSITargetService
        return self._service("iscsi_targets", ISCSITargetService)

    @property
    def snapshots(self):
        from ngxstorage.snapshot import SnapshotService
        return self._service("snapshots", SnapshotService)

    @property
    def pools(self):
        from ngxstorage.pool import PoolService
        return self._service("pools", PoolService)

    @property
    def status(self):
        from ngxstorage.status import StatusService
        return self._service("status", StatusService)

    @property
    def auth_groups(self):
        from ngxstorage.authgroup import AuthGroupService
        return self._service("auth_groups", AuthGroupService)

    @property
    def portal_groups(self):
        from ngxstorage.portalgroup import PortalGroupService
        return self._service("portal_groups", PortalGroupService)

    def refresh_controller(self) -> None:
        """Resolve the NGX work mode and select the serving controller.

        Mirrors the Go SDK: single-master, master-ready, and cluster modes are
        recognized; with a configured pool the controller whose pool list
        contains the pool is selected. A failed refresh preserves the previous
        selection. Raises PoolNotFound or ClusterNotReady on unusable state.
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
                logger.warning("ngx sdk: cluster lookup failed for %s: %s", ip, exc)
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
            self.node_index = candidates[0]
            logger.info(
                "ngx sdk: controller selected (%s): %s", mode, self.controllers[self.node_index]
            )
            return

        selected = -1
        for index in candidates:
            try:
                pools = self._pool_list_for(self.controllers[index])
            except Exception as exc:  # pool lookup failure: skip candidate
                logger.warning("ngx sdk: pool lookup failed for %s: %s", self.controllers[index], exc)
                continue
            for pool in pools:
                if pool.get("name") == self.pool_name or pool.get("id") == self.pool_name:
                    selected = index
                    break
            if selected != -1:
                break

        if selected == -1:
            raise PoolNotFound(f"configured pool {self.pool_name!r} not found")

        self.node_index = selected
        logger.info("ngx sdk: controller selected (%s): %s", mode, self.controllers[selected])

    def _cluster_status_for(self, ip: str) -> dict:
        """Read the cluster status document from a specific controller IP."""
        saved = self.node_index
        try:
            index = self.controllers.index(ip)
            self.node_index = index
            return self.get("status", ["cluster"])
        finally:
            self.node_index = saved

    def _pool_list_for(self, ip: str) -> list:
        """Read the lightweight pool list from a specific controller IP."""
        saved = self.node_index
        try:
            index = self.controllers.index(ip)
            self.node_index = index
            return self.get("pool", None)
        finally:
            self.node_index = saved


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

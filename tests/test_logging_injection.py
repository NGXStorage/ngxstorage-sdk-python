"""Faz 2: logger= injection, endpoint scrubbing and secret-free SDK logs."""

import logging

import pytest
import responses

from ngxstorage import ClientConfig, NGXClient
from ngxstorage.errors import _safe_endpoint


class CaptureHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.lines = []

    def emit(self, record):
        self.lines.append(record.getMessage())


def make_capture(name):
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    handler = CaptureHandler()
    logger.addHandler(handler)
    return logger, handler


def test_logger_injection_used_for_sdk_events():
    logger, handler = make_capture("ngxstorage.test.inject")
    c = NGXClient(
        ClientConfig(controllers=["10.0.0.1"], api_key="test-key", pool_name="pool1", max_retries=2),
        logger=logger,
    )
    c.config.base_delay = 0.0
    with responses.RequestsMock() as rsps:
        url = "https://10.0.0.1/api/v2/lun/list"
        rsps.add(responses.GET, url, json={"code": 725, "error": "busy"}, status=200)
        rsps.add(responses.GET, url, json=[{"id": "l1"}], status=200)
        c._last_refresh = 10**12
        assert c.luns.list() == [{"id": "l1"}]
    assert any("pool busy (725)" in line for line in handler.lines), handler.lines


def test_logger_defaults_to_ngxstorage_namespace():
    c = NGXClient(ClientConfig(controllers=["10.0.0.1"], api_key="k"))
    assert c.logger is not None
    assert c.logger.name == "ngxstorage"


def test_safe_endpoint_scrubs_url_credentials():
    assert _safe_endpoint("https://admin:passw0rd@10.0.0.1:8443/api/v2/x") == "https://***@10.0.0.1:8443/api/v2/x"
    assert _safe_endpoint("admin:passw0rd@10.0.0.1") == "***@10.0.0.1"
    assert _safe_endpoint("https://10.0.0.1:8443/api/v2/x") == "https://10.0.0.1:8443/api/v2/x"
    assert _safe_endpoint("10.0.0.1") == "10.0.0.1"
    assert _safe_endpoint("john@doe.com") == "john@doe.com"


def test_client_config_repr_never_shows_api_key():
    config = ClientConfig(controllers=["10.0.0.1"], api_key="super-secret-key")
    assert "super-secret-key" not in repr(config)
    assert "[REDACTED]" in repr(config)


def test_controller_selection_logs_scrub_endpoints(monkeypatch):
    logger, handler = make_capture("ngxstorage.test.selection")
    c = NGXClient(ClientConfig(controllers=["admin:passw0rd@10.0.0.1"], api_key="k"), logger=logger)
    monkeypatch.setattr(c, "_cluster_status_for", lambda ip: {"status": "Master", "connected": 1})
    c.refresh_controller()
    joined = "\n".join(handler.lines)
    assert joined, handler.lines
    assert "passw0rd" not in joined
    assert "admin:passw0rd" not in joined
    assert "***@10.0.0.1" in joined


def test_emitted_logs_never_contain_api_key():
    logger, handler = make_capture("ngxstorage.test.scan")
    c = NGXClient(
        ClientConfig(controllers=["10.0.0.1"], api_key="s3cr3tValue1", pool_name="pool1", max_retries=2),
        logger=logger,
    )
    c.config.base_delay = 0.0
    with responses.RequestsMock() as rsps:
        url = "https://10.0.0.1/api/v2/lun/list"
        rsps.add(responses.GET, url, json={"code": 725, "error": "echo s3cr3tValue1"}, status=200)
        rsps.add(responses.GET, url, json=[{"id": "l1"}], status=200)
        c._last_refresh = 10**12
        c.luns.list()
    for line in handler.lines:
        assert "s3cr3tValue1" not in line, handler.lines


def test_api_error_and_transport_error_scrub_endpoints():
    from ngxstorage.errors import APIError, TransportError

    err = APIError(400, 4, "boom", "GET", "https://admin:passw0rd@10.0.0.1/api/v2/status")
    assert "passw0rd" not in str(err)
    assert err.endpoint == "https://***@10.0.0.1/api/v2/status"
    terr = TransportError("connect to https://admin:passw0rd@10.0.0.1 failed", "GET", "admin:passw0rd@10.0.0.1/api")
    assert "passw0rd" not in str(terr)
    assert "passw0rd" not in terr.endpoint

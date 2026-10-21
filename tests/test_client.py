"""Python SDK tests using responses to mock HTTP."""

import json
import logging
import threading
import time

import pytest
import requests
import responses

from ngxstorage import NGXClient, ClientConfig, APIError
from ngxstorage.errors import (
    APIError as SDKAPIError,
    CODE_ALREADY_EXISTS,
    CODE_BUSY,
    CODE_NOT_FOUND,
    TransportError,
    is_already_exists,
    is_busy,
    is_not_found,
)


@responses.activate
def test_lun_create(client):
    responses.add(
        responses.POST,
        "https://10.0.0.1/api/v2/lun",
        # Spec: LUN_CREATE response luns items are id, scsi_id, used.
        json={"success": True, "luns": [{"id": "lun-1", "scsi_id": "s1", "used": "0"}]},
        status=200,
    )
    lun = client.luns.create("vol1", 100)
    # The SDK unwraps the "luns" array and returns the LUN.
    assert lun["id"] == "lun-1"
    # Request body: spec declares pool_name, name, size (no owner).
    req = responses.calls[0].request
    import json as _json
    body = _json.loads(req.body)
    assert body == {"pool_name": "pool1", "name": "vol1", "size": 100, "sing": "G"}
    assert req.headers["Authorization"] == "Bearer test-key"


def test_lun_create_validation(client):
    with pytest.raises(ValueError):
        client.luns.create("", 1)
    with pytest.raises(ValueError):
        client.luns.create("vol1", 0)


@responses.activate
def test_share_create_matches_go_contract(client):
    responses.add(
        responses.POST,
        "https://10.0.0.1/api/v2/share",
        json={"success": True},
        status=200,
    )
    responses.add(
        responses.GET,
        "https://10.0.0.1/api/v2/share",
        json=[{"id": "share-1", "name": "share1"}],
        status=200,
    )

    share = client.shares.create(
        "share1", 1024, blocksize="4k", deduplication=True
    )
    assert share["id"] == "share-1"
    assert share["deduplication"] == "1"

    # The create route only declares blocksize, deduplication, compression,
    # the export flags, and the quota fields; undeclared keys would be
    # ignored and an empty blocksize would fail validation (400/5008).
    body = json.loads(responses.calls[0].request.body)
    assert body == {
        "pool_name": "pool1",
        "name": "share1",
        "soft_quota": 1024,
        "blocksize": "4k",
        "deduplication": True,
        "compression": False,
        "nfs_export": False,
    }


@responses.activate
def test_share_create_omits_empty_blocksize(client):
    responses.add(responses.POST, "https://10.0.0.1/api/v2/share", json={"success": True}, status=200)
    responses.add(responses.GET, "https://10.0.0.1/api/v2/share", json=[{"id": "share-2", "name": "s2"}], status=200)

    client.shares.create("s2", 1024)
    body = json.loads(responses.calls[0].request.body)
    assert "blocksize" not in body


@responses.activate
def test_share_create_applies_modify_only_attributes(client):
    responses.add(responses.POST, "https://10.0.0.1/api/v2/share", json={"success": True}, status=200)
    responses.add(responses.GET, "https://10.0.0.1/api/v2/share", json=[{"id": "share-3", "name": "s3"}], status=200)
    responses.add(responses.PATCH, "https://10.0.0.1/api/v2/share/share-3", json={"success": True}, status=200)

    share = client.shares.create("s3", 1024, flash_cache=True, flashtier_limit="16k")
    assert share["flash_cache"] == "1"
    body = json.loads(responses.calls[2].request.body)
    assert body == {"flash_cache": True, "flashtier_blocksize_limit": "16k"}


def test_share_create_validation(client):
    with pytest.raises(ValueError):
        client.shares.create("", 1)
    with pytest.raises(ValueError):
        client.shares.create("share1", 0)


@responses.activate
def test_get_configured_capacity_converts_bytes(client):
    responses.add(
        responses.GET,
        "https://10.0.0.1/api/v2/status/capacity",
        json=[{"name": "pool1", "logical": {"available": "3455", "reserved": "1"}}],
        status=200,
    )
    avail, reserved = client.pools.get_configured_capacity()
    # Spec declares these as strings; the SDK returns ints (Go parity).
    assert avail == 3455
    assert reserved == 1


@responses.activate
def test_lun_delete_idempotent(client):
    responses.add(
        responses.DELETE,
        "https://10.0.0.1/api/v2/lun/lun-1",
        json={"code": CODE_NOT_FOUND, "error": "not found"},
        status=200,
    )
    # Should not raise (idempotent not-found).
    client.luns.delete("lun-1")


@responses.activate
def test_api_error_classification():
    err = APIError(status_code=401, code=5000, message="bad key")
    assert not is_not_found(err)
    err2 = APIError(code=CODE_NOT_FOUND)
    assert is_not_found(err2)
    err3 = APIError(code=CODE_BUSY)
    assert is_busy(err3)
    assert is_already_exists(SDKAPIError(code=CODE_ALREADY_EXISTS))


@responses.activate
def test_fc_target_get_raw(client):
    responses.add(
        responses.GET,
        "https://10.0.0.1/api/v2/target/fc/t1",
        json={
            "id": "t1",
            "name": "tgt-a",
            "owner": "o1",
            "ports": [
                {
                    "id": "p1",
                    "name": "fc0/1",
                    "wwpns": [{"wwpn": "naa.2002a", "owner": "o", "target_id": "t1"}],
                    "initiators": [],
                }
            ],
            "luns": [{"id": "lun-1", "name": "v", "number": "6", "pool_name": "pool1", "scsi_id": "3600"}],
        },
        status=200,
    )
    target = client.fc_targets.get("t1")
    # Raw backend values: WWPN keeps naa. prefix, LUN number stays a string.
    assert target["ports"][0]["wwpns"][0]["wwpn"] == "naa.2002a"
    assert target["luns"][0]["number"] == "6"


@responses.activate
def test_snapshot_clone(client):
    responses.add(
        responses.POST,
        "https://10.0.0.1/api/v2/snapshot/clone/snap-1",
        json={"volume_id": "new-lun-1"},
        status=200,
    )
    vol_id = client.snapshots.clone("snap-1", "clone-1")
    assert vol_id == "new-lun-1"


@responses.activate
def test_repr_redacts_api_key(client):
    rep = repr(client.config)
    assert "test-key" not in rep
    assert "REDACTED" in rep


@responses.activate
def test_logger_never_emits_api_key_on_retry(client, caplog):
    """The SDK logger emits retry diagnostics without the bearer credential."""
    client.config.base_delay = 0.0  # no sleep between the busy retry
    url = "https://10.0.0.1/api/v2/status/cluster"
    responses.add(responses.GET, url, json={"code": CODE_BUSY, "error": "busy"}, status=200)
    responses.add(responses.GET, url, json={"id": "sys"}, status=200)

    with caplog.at_level(logging.DEBUG, logger="ngxstorage"):
        assert client.status.cluster() == {"id": "sys"}

    assert "busy" in caplog.text  # the SDK logger really emitted during the retry
    assert client.api_key not in caplog.text
    assert responses.calls[0].request.headers["Authorization"] == "Bearer " + client.api_key


@responses.activate
def test_logger_and_api_error_never_emit_api_key_on_failure(client, caplog):
    """A failed refresh plus a failed request leak neither logs nor errors."""
    client._last_refresh = 0.0  # force a refresh attempt; no cluster mock, so it fails
    url = "https://10.0.0.1/api/v2/status/cluster"
    responses.add(responses.GET, url, json={"code": CODE_NOT_FOUND, "error": "missing"}, status=404)

    with caplog.at_level(logging.DEBUG, logger="ngxstorage"):
        with pytest.raises(APIError) as excinfo:
            client.status.cluster()

    assert "periodic refresh failed" in caplog.text  # SDK logger emitted on the failure path
    assert client.api_key not in caplog.text
    assert responses.calls[-1].request.headers["Authorization"] == "Bearer " + client.api_key
    assert client.api_key not in str(excinfo.value)
    assert client.api_key not in repr(excinfo.value)


def test_client_validation():
    with pytest.raises(ValueError):
        NGXClient(ClientConfig(controllers=[], api_key="k"))
    with pytest.raises(ValueError):
        NGXClient(ClientConfig(controllers=["a"], api_key=""))
    with pytest.raises(ValueError):
        NGXClient(ClientConfig(controllers=["a", " a "], api_key="k"))
    with pytest.raises(ValueError):
        NGXClient(ClientConfig(controllers=["a", " "], api_key="k"))

    normalized = NGXClient(ClientConfig(controllers=[" 10.0.0.1 "], api_key="k"))
    assert normalized.controllers == ["10.0.0.1"]


def test_configured_timeout_reaches_transport(client, monkeypatch):
    seen = {}

    class Response:
        text = "{}"
        status_code = 200

        @staticmethod
        def json():
            return {}

    def send(request, **kwargs):
        seen.update(kwargs)
        return Response()

    monkeypatch.setattr(client.session, "send", send)
    client.get("info", ["system"])
    assert seen["timeout"] == client.config.timeout


def test_failed_refresh_does_not_replay_transport_failure(client, monkeypatch):
    calls = 0

    def request_once(method, url, body=None):
        nonlocal calls
        calls += 1
        raise TransportError("offline", method, url)

    def refresh():
        raise RuntimeError("cluster unavailable")

    monkeypatch.setattr(client, "_request_once", request_once)
    monkeypatch.setattr(client, "refresh_controller", refresh)

    with pytest.raises(TransportError, match="refresh after transport failure"):
        client.get("pool")
    assert calls == 1


@responses.activate
def test_target_and_pool_list_endpoints(client):
    for path in (
        "target/fc/list", "target/fc", "target/iscsi/list",
        "target/iscsi", "pool", "pool/list",
    ):
        responses.add(
            responses.GET,
            f"https://10.0.0.1/api/v2/{path}",
            json=[],
            status=200,
        )

    assert client.fc_targets.list() == []
    assert client.fc_targets.list_detail() == []
    assert client.iscsi_targets.list() == []
    assert client.iscsi_targets.list_detail() == []
    assert client.pools.list() == []
    assert client.pools.list_detail() == []


@responses.activate
def test_refresh_controller_probes_each_controller_without_switching():
    client = NGXClient(ClientConfig(controllers=["10.0.0.1", "10.0.0.2"], api_key="test-key", pool_name="pool1"))
    responses.add(
        responses.GET,
        "https://10.0.0.1/api/v2/status/cluster",
        json={"connected": 1, "status": "Ready"},
        status=200,
    )
    responses.add(
        responses.GET,
        "https://10.0.0.2/api/v2/status/cluster",
        json={"connected": 1, "status": "Master"},
        status=200,
    )
    responses.add(responses.GET, "https://10.0.0.2/api/v2/pool", json=[{"id": "pool-1", "name": "pool1"}], status=200)

    statuses = [client._cluster_status_for(ip)["status"] for ip in client.controllers]
    client.refresh_controller()

    assert statuses == ["Ready", "Master"]
    assert client.current_controller() == "10.0.0.2"
    assert client.controller_index == 1
    assert client._last_refresh > 0


@responses.activate
def test_first_request_triggers_initial_refresh_before_http(client, monkeypatch):
    """An unrefreshed client refreshes once, before the first resource call."""
    client._last_refresh = 0.0
    events = []

    monkeypatch.setattr(client, "refresh_controller", lambda: events.append("refresh"))

    def pool_response(request):
        events.append("http")
        return (200, {}, "[]")

    responses.add_callback(
        responses.GET, "https://10.0.0.1/api/v2/pool", callback=pool_response
    )

    assert client.pools.list() == []
    assert events == ["refresh", "http"]


@responses.activate
def test_stale_selection_refreshes_after_ttl(client, monkeypatch):
    """A selection older than the 300s TTL is refreshed on the next request."""
    refreshes = []
    monkeypatch.setattr(client, "refresh_controller", lambda: refreshes.append("refresh"))
    client._last_refresh = time.time() - 301
    responses.add(responses.GET, "https://10.0.0.1/api/v2/pool", json=[], status=200)

    assert client.pools.list() == []
    assert refreshes == ["refresh"]


@responses.activate
def test_fresh_selection_skips_refresh(client, monkeypatch):
    """A selection within the TTL is reused without another refresh campaign."""
    refreshes = []
    monkeypatch.setattr(client, "refresh_controller", lambda: refreshes.append("refresh"))
    client._last_refresh = time.time() - 10
    responses.add(responses.GET, "https://10.0.0.1/api/v2/pool", json=[], status=200)

    assert client.pools.list() == []
    assert refreshes == []


@responses.activate
def test_get_transport_failover_replays_once(monkeypatch):
    """A safe GET replays exactly once on the other controller."""
    client = NGXClient(
        ClientConfig(controllers=["10.0.0.1", "10.0.0.2"], api_key="test-key", pool_name="pool1")
    )
    client._last_refresh = time.time()

    def refresh():
        client._publish_controller_selection(1)

    monkeypatch.setattr(client, "refresh_controller", refresh)
    responses.add(
        responses.GET, "https://10.0.0.2/api/v2/pool", json=[{"id": "pool-1"}], status=200
    )

    assert client.pools.list() == [{"id": "pool-1"}]
    assert [call.request.url for call in responses.calls] == [
        "https://10.0.0.1/api/v2/pool",
        "https://10.0.0.2/api/v2/pool",
    ]


@responses.activate
def test_delete_transport_failover_replays_once(monkeypatch):
    """A DELETE is replay-safe and fails over exactly once."""
    client = NGXClient(
        ClientConfig(controllers=["10.0.0.1", "10.0.0.2"], api_key="test-key")
    )
    client._last_refresh = time.time()
    refreshes = []

    def refresh():
        refreshes.append("refresh")
        client._publish_controller_selection(1)

    monkeypatch.setattr(client, "refresh_controller", refresh)
    responses.add(
        responses.DELETE, "https://10.0.0.2/api/v2/lun/lun-1", json={"success": True}, status=200
    )

    client.luns.delete("lun-1")

    assert refreshes == ["refresh"]
    assert [call.request.method for call in responses.calls] == ["DELETE", "DELETE"]


@responses.activate
def test_post_mutation_is_never_replayed(monkeypatch):
    """An ambiguous mutation (POST) transport failure is never replayed."""
    client = NGXClient(
        ClientConfig(controllers=["10.0.0.1", "10.0.0.2"], api_key="test-key", pool_name="pool1")
    )
    client._last_refresh = time.time()
    refreshes = []
    monkeypatch.setattr(client, "refresh_controller", lambda: refreshes.append("refresh"))

    with pytest.raises(TransportError):
        client.luns.create("vol1", 100)

    assert len(responses.calls) == 1
    assert responses.calls[0].request.method == "POST"
    assert refreshes == []


@responses.activate
def test_error_redacts_echoed_api_key(client, caplog):
    """A server echoing the configured key cannot leak it via errors or logs."""
    client._last_refresh = 0.0
    echo = {"code": 1234, "error": "server echoed test-key and Authorization"}
    responses.add(
        responses.GET, "https://10.0.0.1/api/v2/status/cluster", json=echo, status=200
    )
    responses.add(responses.GET, "https://10.0.0.1/api/v2/pool", json=echo, status=200)

    with caplog.at_level(logging.DEBUG, logger="ngxstorage"):
        with pytest.raises(APIError) as excinfo:
            client.pools.list()

    err = excinfo.value
    assert not hasattr(err, "body")
    assert "body" not in err.__dict__
    assert "[REDACTED]" in str(err)
    assert "test-key" not in str(err)
    assert "test-key" not in repr(err)
    assert "test-key" not in str(err.__dict__)
    assert "test-key" not in caplog.text
    assert "cluster lookup failed" in caplog.text  # the logger path really ran


def test_refresh_controller_serializes_concurrent_callers(monkeypatch):
    client = NGXClient(ClientConfig(controllers=["10.0.0.1"], api_key="test-key"))
    state_lock = threading.Lock()
    active = 0
    max_active = 0

    def discover():
        nonlocal active, max_active
        with state_lock:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.01)
        client._publish_controller_selection(0)
        with state_lock:
            active -= 1

    monkeypatch.setattr(client, "_discover_controller", discover)
    threads = [threading.Thread(target=client.refresh_controller) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert max_active == 1
    assert client.current_controller() == "10.0.0.1"


# -- caller-owned retry contract -----------------------------------------------


@responses.activate
def test_busy_retries_respect_max_retries_budget(client):
    client.config.base_delay = 0.0
    client.config.max_retries = 3
    url = "https://10.0.0.1/api/v2/lun/list"
    responses.add(responses.GET, url, json={"code": CODE_BUSY, "error": "busy"}, status=200)
    responses.add(responses.GET, url, json={"code": CODE_BUSY, "error": "busy"}, status=200)
    responses.add(responses.GET, url, json=[{"id": "l1"}], status=200)

    assert client.luns.list() == [{"id": "l1"}]
    assert len(responses.calls) == 3


@responses.activate
def test_busy_budget_stops_at_max_retries(client):
    client.config.base_delay = 0.0
    client.config.max_retries = 2
    url = "https://10.0.0.1/api/v2/lun/list"
    responses.add(responses.GET, url, json={"code": CODE_BUSY, "error": "busy"}, status=200)

    with pytest.raises(APIError) as excinfo:
        client.luns.list()
    assert excinfo.value.code == CODE_BUSY
    assert len(responses.calls) == 2


@responses.activate
def test_transport_failure_spends_single_attempt_get(client):
    client.config.max_retries = 5
    url = "https://10.0.0.1/api/v2/lun/list"
    responses.add(responses.GET, url, body=requests.ConnectionError("EOF"))

    with pytest.raises(TransportError):
        client.luns.list()
    # Exactly one wire attempt for the operation; the failover refresh probe
    # may run afterwards but never re-runs the operation here.
    assert len(_calls_to(url)) == 1


@responses.activate
def test_transport_failure_spends_single_attempt_post(client):
    client.config.max_retries = 5
    responses.add(responses.POST, "https://10.0.0.1/api/v2/lun", body=requests.ConnectionError("refused"))

    with pytest.raises(TransportError):
        client.luns.create("v1", 10)
    assert len(responses.calls) == 1


def _two_controller_client():
    """Real two-controller client; the refresh path runs unpatched."""
    c = NGXClient(ClientConfig(
        controllers=["10.0.0.1", "10.0.0.2"], api_key="test-key", pool_name="",
        max_retries=3, base_delay=0.0, max_delay=0.0,
    ))
    c._last_refresh = time.time()
    return c


def _calls_to(prefix):
    return [call for call in responses.calls if call.request.url.startswith(prefix)]


def _register_master_ready_probes():
    responses.add(responses.GET, "https://10.0.0.1/api/v2/status/cluster",
                  json={"connected": 1, "status": "Ready"}, status=200)
    responses.add(responses.GET, "https://10.0.0.2/api/v2/status/cluster",
                  json={"connected": 1, "status": "Master"}, status=200)


@responses.activate
def test_get_failover_replays_once_then_succeeds():
    c = _two_controller_client()
    _register_master_ready_probes()
    responses.add(responses.GET, "https://10.0.0.1/api/v2/lun/list", body=requests.ConnectionError("EOF"))
    responses.add(responses.GET, "https://10.0.0.2/api/v2/lun/list", json=[{"id": "l1"}], status=200)

    assert c.luns.list() == [{"id": "l1"}]
    assert len(_calls_to("https://10.0.0.1/api/v2/lun/list")) == 1
    assert len(_calls_to("https://10.0.0.2/api/v2/lun/list")) == 1


@responses.activate
def test_safe_failover_propagates_second_failure():
    c = _two_controller_client()
    _register_master_ready_probes()
    responses.add(responses.GET, "https://10.0.0.1/api/v2/lun/list", body=requests.ConnectionError("EOF"))
    responses.add(responses.GET, "https://10.0.0.2/api/v2/lun/list", body=requests.ConnectionError("EOF"))

    with pytest.raises(TransportError):
        c.luns.list()
    assert len(_calls_to("https://10.0.0.1/api/v2/lun/list")) == 1
    assert len(_calls_to("https://10.0.0.2/api/v2/lun/list")) == 1


@responses.activate
def test_delete_failover_replays_once():
    c = _two_controller_client()
    _register_master_ready_probes()
    responses.add(responses.DELETE, "https://10.0.0.1/api/v2/lun/lun-1", body=requests.ConnectionError("EOF"))
    responses.add(responses.DELETE, "https://10.0.0.2/api/v2/lun/lun-1", json={"success": True}, status=200)

    c.luns.delete("lun-1")
    assert len(_calls_to("https://10.0.0.1/api/v2/lun/lun-1")) == 1
    assert len(_calls_to("https://10.0.0.2/api/v2/lun/lun-1")) == 1


@responses.activate
def test_put_and_patch_mutations_never_replayed():
    c = _two_controller_client()
    responses.add(responses.PUT, "https://10.0.0.1/api/v2/target/fc/lun/t1",
                  body=requests.ConnectionError("refused"))
    responses.add(responses.PATCH, "https://10.0.0.1/api/v2/lun/lun-1",
                  body=requests.ConnectionError("refused"))

    with pytest.raises(TransportError):
        c.fc_targets.add_lun("t1", "lun-1", "owner-1")
    with pytest.raises(TransportError):
        c.luns.modify("lun-1", {"name": "x"})
    # No refresh, no replay: exactly one wire call per mutation.
    assert len(responses.calls) == 2


# -- wire contracts verified against the deployed API v2 -------------------------


@responses.activate
def test_fc_initiator_tag_uses_backend_contract(client):
    responses.add(
        responses.POST,
        "https://10.0.0.1/api/v2/target/fc/initiator/tag",
        json={"id": "tag-1", "initiator_naa": "5006016000000000", "tag": "tag-a"},
        status=200,
    )
    tag = client.fc_targets.create_initiator_tag("5006016000000000", "tag-a")
    assert tag["id"] == "tag-1"
    body = json.loads(responses.calls[0].request.body)
    assert body == {"initiator_naa": "5006016000000000", "tag": "tag-a"}


@responses.activate
def test_portal_group_backend_is_read_only(client):
    # The deployed backend has no portal-group create/delete routes; the
    # calls reach the server and come back as the unknown-operation error.
    responses.add(
        responses.POST,
        "https://10.0.0.1/api/v2/portal_group",
        json={"code": 5012, "error": "The requested operation does not exist."},
        status=500,
    )
    with pytest.raises(APIError) as excinfo:
        client.portal_groups.create("pg", "owner-1")
    assert excinfo.value.code == 5012


@responses.activate
def test_portal_group_list_detail(client):
    responses.add(
        responses.GET,
        "https://10.0.0.1/api/v2/portal_group/list",
        json=[{"id": "7", "name": "DefaultPortalGroup", "listen_ips": [{"ip_address": "192.0.2.10"}]}],
        status=200,
    )
    groups = client.portal_groups.list_detail()
    assert groups[0]["listen_ips"][0]["ip_address"] == "192.0.2.10"


@responses.activate
def test_pool_overview_returns_array(client):
    responses.add(
        responses.GET,
        "https://10.0.0.1/api/v2/pool/overview",
        json=[{"blocksize": "32k", "pool_name": "p1", "state": "ONLINE"}],
        status=200,
    )
    overview = client.pools.overview()
    assert isinstance(overview, list)
    assert overview[0]["pool_name"] == "p1"


@responses.activate
def test_overloaded_volumes_returns_wrapped_document(client):
    responses.add(
        responses.GET,
        "https://10.0.0.1/api/v2/status/overloaded_volumes",
        json={"last_check_time": 1756716344.5, "overloaded_volumes": [{"id": "v1"}]},
        status=200,
    )
    document = client.status.overloaded_volumes()
    assert document["overloaded_volumes"] == [{"id": "v1"}]


@responses.activate
def test_auth_group_create_returns_string_id(client):
    responses.add(
        responses.POST,
        "https://10.0.0.1/api/v2/auth_group",
        json={"id": 4, "success": True},
        status=200,
    )
    assert client.auth_groups.create("group1", "owner-1") == "4"


# -- pinned compatibility and redaction boundaries ------------------------------


def test_api_error_str_format_pinned():
    err = APIError(status_code=500, code=5000, message="bad", method="GET", endpoint="/api/v2/x")
    assert str(err) == (
        "ngxstorage api error: method=GET endpoint=/api/v2/x "
        "http_status=500 code=5000 message='bad'"
    )
    err2 = APIError(status_code=404, message="missing", method="DELETE", endpoint="/api/v2/y")
    assert str(err2) == (
        "ngxstorage api error: method=DELETE endpoint=/api/v2/y "
        "http_status=404 message='missing'"
    )


@responses.activate
def test_malformed_response_cause_chain_has_no_secret(client):
    responses.add(responses.GET, "https://10.0.0.1/api/v2/lun/list",
                  body="oops test-key {", content_type="text/plain", status=200)

    with pytest.raises(APIError) as excinfo:
        client.luns.list()
    err = excinfo.value
    assert "test-key" not in str(err)
    assert "test-key" not in repr(err)
    assert err.__cause__ is not None
    assert "test-key" not in str(err.__cause__)
    assert "test-key" not in repr(err.__cause__)


@responses.activate
def test_cli_error_output_redacts_key(capsys):
    from ngxstorage.cli import main as cli_main

    url = "https://10.0.0.1/api/v2/status/cluster"
    payload = {"code": 5000, "error": "server echoed test-key and Authorization"}
    # One registration for the initial refresh probe, one for the operation.
    responses.add(responses.GET, url, json=payload, status=200)
    responses.add(responses.GET, url, json=payload, status=200)

    rc = cli_main(["--controllers", "10.0.0.1", "--api-key", "test-key", "status"])
    assert rc == 1
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "test-key" not in combined
    assert "[REDACTED]" in combined

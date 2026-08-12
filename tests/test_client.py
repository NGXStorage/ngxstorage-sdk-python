"""Python SDK tests using responses to mock HTTP."""

import pytest
import responses

from ngxstorage import NGXClient, ClientConfig, APIError
from ngxstorage.errors import is_not_found, is_busy, CODE_NOT_FOUND, CODE_BUSY


@pytest.fixture
def client():
    return NGXClient(ClientConfig(controllers=["10.0.0.1"], api_key="test-key", pool_name="pool1"))


@responses.activate
def test_lun_create(client):
    responses.add(
        responses.POST,
        "https://10.0.0.1/api/v2/lun",
        json={"luns": [{"id": "lun-1", "name": "vol1"}]},
        status=200,
    )
    lun = client.luns.create("vol1", 100)
    assert lun["luns"][0]["id"] == "lun-1"
    # Authorization header must be Bearer.
    req = responses.calls[0].request
    assert req.headers["Authorization"] == "Bearer test-key"


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


def test_client_validation():
    with pytest.raises(ValueError):
        NGXClient(ClientConfig(controllers=[], api_key="k"))
    with pytest.raises(ValueError):
        NGXClient(ClientConfig(controllers=["a"], api_key=""))

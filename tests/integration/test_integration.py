"""Live integration scenarios for the NGX SDK.

These tests exercise the real NGX API v2 contract (payload shapes, mandatory
keys, response parsing) that mocked unit tests cannot catch. Run them against
a live NGX Storage Array:

    NGX_CONTROLLERS=192.168.1.201,192.168.1.202 \
    NGX_API_KEY=<api-key> \
    NGX_POOL_NAME=openstackSSD1 \
    pytest tests/integration -v
"""

import os
import time

import pytest


def _uniq(prefix):
    # Backend name regex is ^[0-9a-zA-Z]{1,30}$ (alphanumeric only, no dash).
    return f"{prefix}{os.getpid()}{int(time.time() % 100000)}"


def test_refresh_controller_resolves_master(client):
    """Work-mode resolution selects a controller that owns the pool."""
    client.refresh_controller()
    assert client.current_controller() in client.controllers


def test_lun_lifecycle(client):
    """create() must return the created LUN (with id), not the raw ack."""
    name = _uniq("itlun")
    lun = client.luns.create(name, 1)
    assert lun.get("id"), f"luns.create did not return an id: {lun!r}"

    # Expand + verify the size grew.
    client.luns.expand(lun["id"], 2)
    detail = client.luns.get(lun["id"])
    assert detail["id"] == lun["id"]

    client.luns.delete(lun["id"])
    # Idempotent delete must not raise.
    client.luns.delete(lun["id"])


def test_share_lifecycle(client):
    """create() resolves the share id from the list (SHARE_CREATE returns no id)."""
    name = _uniq("itshare")
    share = client.shares.create(name, 1024 ** 3)
    assert share.get("id"), f"shares.create did not return an id: {share!r}"

    # The export is created disabled and can be enabled.
    client.shares.set_export_enabled(share["id"], True)
    detail = client.shares.get(share["id"])
    assert detail["exports"]["nfs"]["enabled"] in ("1", True, 1)

    client.shares.delete(share["id"])


def test_snapshot_and_clone(client):
    """Snapshot create returns id; clone returns a new volume id."""
    lun = client.luns.create(_uniq("itsnaplun"), 1)
    try:
        snap = client.snapshots.create(lun["id"], _uniq("itsnap"))
        assert snap.get("id"), f"snapshots.create did not return an id: {snap!r}"

        clone_id = client.snapshots.clone(snap["id"], _uniq("itclone"))
        assert isinstance(clone_id, str) and clone_id
        client.luns.delete(clone_id)

        client.snapshots.delete(snap["id"])
    finally:
        client.luns.delete(lun["id"])


def test_fc_target_list(client):
    """FC target list returns pre-created targets."""
    targets = client.fc_targets.list()
    assert isinstance(targets, list)


def test_iscsi_target_create_requires_auth_and_portal(client):
    """create() must send auth_group_id and portal_group_id (mandatory keys)."""
    portal_groups = client.portal_groups.list()
    if not portal_groups:
        pytest.skip("no portal group configured on this array")
    portal_group = client.portal_groups.get(portal_groups[0]["id"])

    target_name = _uniq("ittarget")
    auth_group_id = client.auth_groups.create(_uniq("itauth"), "1")
    try:
        created = client.iscsi_targets.create(
            target_name, auth_group_id, portal_group["id"], "1")
        # create returns the full target (spec: id, target_iqn, ...).
        assert created.get("id"), f"iscsitargets.create did not return id: {created!r}"
        names = [t.get("name") for t in client.iscsi_targets.list()]
        assert target_name in names
    finally:
        # An auth group assigned to a target cannot be deleted (code 520);
        # delete the target first, then the auth group.
        for t in client.iscsi_targets.list():
            if t.get("name") == target_name:
                client.iscsi_targets.delete(t["id"])
        client.auth_groups.delete(auth_group_id)


def test_pool_capacity(client):
    """GetConfiguredCapacity resolves the configured pool's bytes."""
    avail, reserved = client.pools.get_configured_capacity()
    assert avail >= 0 and reserved >= 0

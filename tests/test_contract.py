"""Wire-contract tests for the Python SDK services.

Each test pins the request path, method, body, and the response shape the
service returns, against the deployed API contract.
"""

import json

import pytest
import responses


def _body(call):
    return json.loads(call.request.body) if call.request.body else {}


# -- LUN ---------------------------------------------------------------------

@responses.activate
def test_lun_get_and_list_pass_through_wire_shape(client):
    detail = {
        "id": "lun-1", "name": "vol1", "owner": "ctrl-a", "pool_name": "pool1",
        "size": "1073741824", "used": "1048576", "blocksize": "32k",
        "thin_provision": True, "compression": True, "deduplication": False,
        "dram_cache": True, "flash_cache": False, "compress_ratio": "1.01",
        "clone": "", "sizebysnapshots": "0", "scsi_id": "3600",
        "io_type": "transactional", "qos_priority": 4,
        "protocols": {"fc": None, "iscsi": None},
        "created": "2025-11-24T08:50:44Z",
    }
    responses.add(responses.GET, "https://10.0.0.1/api/v2/lun/lun-1", json=detail, status=200)
    responses.add(responses.GET, "https://10.0.0.1/api/v2/lun/list", json=[detail], status=200)

    assert client.luns.get("lun-1")["protocols"] == {"fc": None, "iscsi": None}
    assert client.luns.list()[0]["created"] == "2025-11-24T08:50:44Z"


@responses.activate
def test_lun_modify_passes_fields_verbatim(client):
    responses.add(responses.PATCH, "https://10.0.0.1/api/v2/lun/lun-1",
                  json={"success": True, "size": "2147483648"}, status=200)
    client.luns.modify("lun-1", {"deduplication": "off", "force": "true"})
    assert _body(responses.calls[0]) == {"deduplication": "off", "force": "true"}


@responses.activate
def test_lun_expand_sends_additive_increment(client):
    responses.add(responses.PATCH, "https://10.0.0.1/api/v2/lun/lun-1", json={"success": True}, status=200)
    client.luns.expand("lun-1", 50)
    assert _body(responses.calls[0]) == {"size": 50, "sing": "G"}


@responses.activate
def test_lun_delete_idempotent_on_semantic_not_found(client):
    responses.add(responses.DELETE, "https://10.0.0.1/api/v2/lun/lun-gone",
                  json={"code": 5011, "error": "no lun"}, status=200)
    client.luns.delete("lun-gone")  # must not raise


# -- Share -------------------------------------------------------------------

@responses.activate
def test_share_modify_helpers_send_canonical_keys(client):
    responses.add(responses.PATCH, "https://10.0.0.1/api/v2/share/sh-1",
                  json={"success": True}, status=200)
    client.shares.set_export_enabled("sh-1", True)
    client.shares.set_read_only("sh-1", True)
    client.shares.expand("sh-1", 2 * 1024 ** 3)

    assert _body(responses.calls[0]) == {"nfs_export": True}
    assert _body(responses.calls[1]) == {"nfs_read_only": True}
    assert _body(responses.calls[2]) == {"soft_quota": 2 * 1024 ** 3}


@responses.activate
def test_share_list_endpoints(client):
    responses.add(responses.GET, "https://10.0.0.1/api/v2/share",
                  json=[{"id": "sh-1", "name": "s1", "owner": "ctrl-a", "pool_name": "pool1"}], status=200)
    responses.add(responses.GET, "https://10.0.0.1/api/v2/share/list",
                  json=[{"id": "sh-1", "name": "s1", "pool_name": "pool1",
                         "capacity": {"soft_quota": 10},
                         "storage": {"blocksize": "128k", "deduplication": True}}], status=200)
    assert client.shares.list_names()[0]["id"] == "sh-1"
    assert client.shares.list()[0]["storage"]["blocksize"] == "128k"


@responses.activate
def test_share_delete_idempotent_on_semantic_not_found(client):
    responses.add(responses.DELETE, "https://10.0.0.1/api/v2/share/sh-gone",
                  json={"code": 5011, "error": "no share"}, status=200)
    client.shares.delete("sh-gone")  # must not raise


# -- Snapshot ----------------------------------------------------------------

@responses.activate
def test_snapshot_create_sends_name_and_volume_id(client):
    responses.add(responses.POST, "https://10.0.0.1/api/v2/snapshot",
                  json={"id": "snap-1", "path": "pool1/vol1@snap1", "name": "snap1",
                        "volume_id": "vol-1", "volume_name": "vol1", "pool_name": "pool1"},
                  status=200)
    snap = client.snapshots.create("vol-1", "snap1")
    assert _body(responses.calls[0]) == {"name": "snap1", "volume_id": "vol-1"}
    assert snap["id"] == "snap-1"


@responses.activate
def test_snapshot_list_detail_sends_volume_id_query(client):
    responses.add(responses.GET,
                  "https://10.0.0.1/api/v2/snapshot/list?volume_id=vol-1",
                  json=[], status=200)
    client.snapshots.list_detail("vol-1")
    assert "volume_id=vol-1" in responses.calls[0].request.url


@responses.activate
def test_snapshot_clone_reads_volume_id_ack(client):
    responses.add(responses.POST, "https://10.0.0.1/api/v2/snapshot/clone/snap-1",
                  json={"success": True, "volume_id": "new-vol-1"}, status=200)
    assert client.snapshots.clone("snap-1", "clone-1") == "new-vol-1"
    assert _body(responses.calls[0]) == {"name": "clone-1"}


@responses.activate
def test_snapshot_restore_sends_confirm(client):
    responses.add(responses.POST, "https://10.0.0.1/api/v2/snapshot/restore/snap-1",
                  json={"success": True}, status=200)
    client.snapshots.restore("snap-1")
    assert _body(responses.calls[0]) == {"confirm": "true"}


@responses.activate
def test_snapshot_delete_and_delete_all_idempotent(client):
    responses.add(responses.DELETE, "https://10.0.0.1/api/v2/snapshot/snap-gone",
                  json={"code": 5011, "error": "no snapshot"}, status=200)
    responses.add(responses.DELETE, "https://10.0.0.1/api/v2/snapshot/all/vol-gone",
                  json={"code": 5011, "error": "no snapshots"}, status=200)
    client.snapshots.delete("snap-gone")
    client.snapshots.delete_all("vol-gone")


@responses.activate
def test_snapshot_schedule_roundtrip(client):
    responses.add(responses.POST, "https://10.0.0.1/api/v2/snapshot/schedule/vol-1",
                  json={"success": True, "h_read": "Every 10 minutes"}, status=200)
    responses.add(responses.GET, "https://10.0.0.1/api/v2/snapshot/schedule/vol-1",
                  json={"id": "sch-1", "owner": "ctrl-a", "h_read": "Every 10 minutes",
                        "c_time": "*/10 * * * *", "keep_max": "32",
                        "volume_id": "vol-1", "volume_type": "lun"}, status=200)
    responses.add(responses.DELETE, "https://10.0.0.1/api/v2/snapshot/schedule/vol-1",
                  json={"code": 5011, "error": "no schedule"}, status=200)

    created = client.snapshots.create_schedule("vol-1", {"cron_time": "*/10 * * * *", "keep_max": 32})
    assert created["h_read"] == "Every 10 minutes"
    assert _body(responses.calls[0]) == {"cron_time": "*/10 * * * *", "keep_max": 32}
    schedule = client.snapshots.get_schedule("vol-1")
    assert schedule["c_time"] == "*/10 * * * *" and schedule["keep_max"] == "32"
    client.snapshots.delete_schedule("vol-1")  # idempotent


# -- FC target ----------------------------------------------------------------

@responses.activate
def test_fc_target_add_remove_lun_bodies(client):
    responses.add(responses.PUT, "https://10.0.0.1/api/v2/target/fc/lun/tgt-1",
                  json={"success": True, "luns": [{"id": "l1", "name": "v", "number": 6,
                                                   "pool_name": "p", "scsi_id": "s"}]}, status=200)
    responses.add(responses.PATCH, "https://10.0.0.1/api/v2/target/fc/lun/tgt-1",
                  json={"success": True, "luns": []}, status=200)
    client.fc_targets.add_lun("tgt-1", "lun-1", "ctrl-a")
    client.fc_targets.remove_lun("tgt-1", "lun-1", "ctrl-a")
    for call in responses.calls:
        assert _body(call) == {"owner": "ctrl-a", "lun_ids": ["lun-1"]}


@responses.activate
def test_fc_target_list_endpoints(client):
    responses.add(responses.GET, "https://10.0.0.1/api/v2/target/fc",
                  json=[{"id": "t1", "name": "tgt-a", "owner": "ctrl-a"}], status=200)
    responses.add(responses.GET, "https://10.0.0.1/api/v2/target/fc/list",
                  json=[{"id": "t1", "name": "tgt-a", "owner": "ctrl-a", "ports": [], "luns": []}], status=200)
    assert client.fc_targets.list_names()[0]["name"] == "tgt-a"
    assert client.fc_targets.list_detail()[0]["luns"] == []


@responses.activate
def test_fc_initiator_tag_roundtrip(client):
    responses.add(responses.GET, "https://10.0.0.1/api/v2/target/fc/initiator/tag",
                  json=[{"id": "tag-1", "initiator_naa": "5006016000000000", "tag": "tag-a", "owner": "ctrl-a"}], status=200)
    responses.add(responses.POST, "https://10.0.0.1/api/v2/target/fc/initiator/tag",
                  json={"id": "tag-2", "initiator_naa": "5006016000000001", "tag": "tag-b"}, status=200)
    responses.add(responses.GET, "https://10.0.0.1/api/v2/target/fc/initiator/tag/tag-1",
                  json={"id": "tag-1", "initiator_naa": "5006016000000000", "tag": "tag-a"}, status=200)
    responses.add(responses.DELETE, "https://10.0.0.1/api/v2/target/fc/initiator/tag/tag-1",
                  json={"code": 5011, "error": "no tag"}, status=200)

    assert client.fc_targets.list_initiator_tags()[0]["tag"] == "tag-a"
    assert client.fc_targets.create_initiator_tag("5006016000000001", "tag-b")["id"] == "tag-2"
    assert _body(responses.calls[1]) == {"initiator_naa": "5006016000000001", "tag": "tag-b"}
    assert client.fc_targets.get_initiator_tag("tag-1")["initiator_naa"] == "5006016000000000"
    client.fc_targets.delete_initiator_tag("tag-1")  # idempotent


# -- iSCSI target --------------------------------------------------------------

@responses.activate
def test_iscsi_target_get_decodes_full_shape(client):
    responses.add(responses.GET, "https://10.0.0.1/api/v2/target/iscsi/tgt-1",
                  json={
                      "id": "tgt-1", "name": "csi-target", "owner": "ctrl-a",
                      "target_iqn": "iqn.2026-01.com.ngx:csi-target",
                      "auth_group_id": "2", "auth_group_name": "group1",
                      "portal_group_id": "7", "portal_group_name": "DefaultPortalGroup",
                      "initiators": [{"id": "11", "iqn": "iqn.1994-05.com.redhat:node1",
                                      "alias": "host-a", "ip": "192.0.2.10"}],
                      "luns": [{"id": "lun-1", "name": "vol1", "number": "6",
                                "pool_name": "pool1", "scsi_id": "3600"}],
                  }, status=200)
    target = client.iscsi_targets.get("tgt-1")
    assert target["initiators"][0]["ip"] == "192.0.2.10"
    assert target["luns"][0]["scsi_id"] == "3600"


@responses.activate
def test_iscsi_target_change_operations_hit_dedicated_routes(client):
    responses.add(responses.PATCH, "https://10.0.0.1/api/v2/target/iscsi/tgt-1",
                  json={"success": True}, status=200)
    responses.add(responses.PATCH, "https://10.0.0.1/api/v2/target/iscsi/auth_group/tgt-1",
                  json={"success": True}, status=200)
    responses.add(responses.PATCH, "https://10.0.0.1/api/v2/target/iscsi/portal_group/tgt-1",
                  json={"success": True}, status=200)
    client.iscsi_targets.change_name("tgt-1", "new-name", "ctrl-a")
    client.iscsi_targets.change_auth_group("tgt-1", "3", "ctrl-a")
    client.iscsi_targets.change_portal_group("tgt-1", "7", "ctrl-a")

    assert _body(responses.calls[0]) == {"name": "new-name", "owner": "ctrl-a"}
    assert _body(responses.calls[1]) == {"auth_group_id": "3", "owner": "ctrl-a"}
    assert _body(responses.calls[2]) == {"portal_group_id": "7", "owner": "ctrl-a"}


@responses.activate
def test_iscsi_target_add_remove_lun_and_delete_idempotent(client):
    responses.add(responses.PUT, "https://10.0.0.1/api/v2/target/iscsi/lun/tgt-1",
                  json={"success": True}, status=200)
    responses.add(responses.PATCH, "https://10.0.0.1/api/v2/target/iscsi/lun/tgt-1",
                  json={"success": True}, status=200)
    responses.add(responses.DELETE, "https://10.0.0.1/api/v2/target/iscsi/tgt-gone",
                  json={"code": 5011, "error": "no target"}, status=200)
    client.iscsi_targets.add_lun("tgt-1", "lun-1", "ctrl-a")
    client.iscsi_targets.remove_lun("tgt-1", "lun-1", "ctrl-a")
    for call in responses.calls[:2]:
        assert _body(call) == {"owner": "ctrl-a", "lun_ids": ["lun-1"]}
    client.iscsi_targets.delete("tgt-gone")  # must not raise


# -- Auth group ----------------------------------------------------------------

@responses.activate
def test_authgroup_chap_roundtrip(client):
    responses.add(responses.PATCH, "https://10.0.0.1/api/v2/auth_group/chap/4",
                  json={"success": True}, status=200)
    responses.add(responses.DELETE, "https://10.0.0.1/api/v2/auth_group/chap/4",
                  json={"code": 5011, "error": "no chap"}, status=200)
    client.auth_groups.add_chap("4", "chapuser", "password123456")
    assert _body(responses.calls[0]) == {"username": "chapuser", "password": "password123456"}
    client.auth_groups.delete_chap("4")


@responses.activate
def test_authgroup_iqn_roundtrip(client):
    responses.add(responses.PATCH, "https://10.0.0.1/api/v2/auth_group/iqn/4",
                  json={"success": True, "id": 12}, status=200)
    responses.add(responses.PATCH, "https://10.0.0.1/api/v2/auth_group/iqn/4",
                  json={"code": 522, "error": "IQN already registered"}, status=200)
    responses.add(responses.DELETE, "https://10.0.0.1/api/v2/auth_group/iqn/12",
                  json={"code": 5011, "error": "no iqns"}, status=200)

    record = client.auth_groups.add_iqn("4", "iqn.1994-05.com.redhat:node1", "host-a", "ctrl-a")
    assert record["id"] == 12
    assert _body(responses.calls[0]) == {
        "owner": "ctrl-a", "iqn": "iqn.1994-05.com.redhat:node1", "alias": "host-a"}
    # A duplicate IQN is reported as already registered, not as an error.
    assert client.auth_groups.add_iqn("4", "iqn.1994-05.com.redhat:node1", "host-a", "ctrl-a") == {}
    client.auth_groups.delete_iqn("12")  # idempotent


@responses.activate
def test_authgroup_detail_shape(client):
    responses.add(responses.GET, "https://10.0.0.1/api/v2/auth_group/4",
                  json={"id": "4", "name": "group1", "owner": "ctrl-a", "chap_status": 1,
                        "chap_username": "chapuser",
                        "initiator": [{"id": "11", "iqn": "iqn.1994-05.com.redhat:node1",
                                       "alias": "host-a"}]}, status=200)
    responses.add(responses.GET, "https://10.0.0.1/api/v2/auth_group/list",
                  json=[{"id": "4", "name": "group1", "owner": "ctrl-a",
                         "chap_status": 1, "initiator": []}], status=200)
    group = client.auth_groups.get("4")
    assert group["chap_status"] == 1 and group["initiator"][0]["alias"] == "host-a"
    assert client.auth_groups.list_detail()[0]["id"] == "4"


# -- Portal group ----------------------------------------------------------------

@responses.activate
def test_portal_group_read_only_endpoints(client):
    responses.add(responses.GET, "https://10.0.0.1/api/v2/portal_group",
                  json=[{"id": "7", "name": "DefaultPortalGroup", "owner": "ctrl-a"}], status=200)
    responses.add(responses.GET, "https://10.0.0.1/api/v2/portal_group/list",
                  json=[{"id": "7", "name": "DefaultPortalGroup", "owner": "ctrl-a",
                         "listen_ips": [{"id": "1", "interface_name": "em1",
                                         "ip_address": "192.0.2.10", "owner": "ctrl-a"}]}], status=200)
    responses.add(responses.GET, "https://10.0.0.1/api/v2/portal_group/7",
                  json={"id": "7", "name": "DefaultPortalGroup", "owner": "ctrl-a",
                        "listen_ips": []}, status=200)
    assert client.portal_groups.list()[0]["name"] == "DefaultPortalGroup"
    assert client.portal_groups.list_detail()[0]["listen_ips"][0]["ip_address"] == "192.0.2.10"
    assert client.portal_groups.get("7")["id"] == "7"


# -- Pool ------------------------------------------------------------------------

@responses.activate
def test_pool_read_endpoints(client):
    responses.add(responses.GET, "https://10.0.0.1/api/v2/pool",
                  json=[{"id": "12", "name": "pool1", "owner": "ctrl-a"}], status=200)
    responses.add(responses.GET, "https://10.0.0.1/api/v2/pool/12",
                  json={"id": "12", "name": "pool1", "owner": "ctrl-a", "blocksize": "32k"}, status=200)
    responses.add(responses.GET, "https://10.0.0.1/api/v2/pool/overview",
                  json=[{"blocksize": "32k", "pool_name": "pool1", "state": "ONLINE"}], status=200)
    assert client.pools.list()[0]["id"] == "12"
    assert client.pools.get("12")["blocksize"] == "32k"
    assert isinstance(client.pools.overview(), list)


# -- Status -----------------------------------------------------------------------

@responses.activate
def test_status_documents(client):
    responses.add(responses.GET, "https://10.0.0.1/api/v2/status/cluster",
                  json={"peers": [{"id": "192.0.2.10"}], "connected": 1, "status": "Master",
                        "interconnects": {"ethernet": 1, "hbactive": 0, "hbdrive": 0, "serial": 0}},
                  status=200)
    responses.add(responses.GET, "https://10.0.0.1/api/v2/status/services",
                  json={"san": "running", "nfs": "stopped"}, status=200)
    responses.add(responses.GET, "https://10.0.0.1/api/v2/status/iops",
                  json={"read": 10, "write": 20, "total": 30}, status=200)
    responses.add(responses.GET, "https://10.0.0.1/api/v2/status/bandwidth",
                  json={"read": 100, "write": 200, "total": 300}, status=200)
    responses.add(responses.GET, "https://10.0.0.1/api/v2/status/cache",
                  json={"dram": {"Current_Size": "10"}, "flash": {"Cache_Size": "5"}}, status=200)
    responses.add(responses.GET, "https://10.0.0.1/api/v2/status/cpu",
                  json={"load_1_min": "0.5", "current_utilization": 10}, status=200)
    responses.add(responses.GET, "https://10.0.0.1/api/v2/status/enclosures",
                  json=[{"model": "ES1000", "no": 1, "owner": "ctrl-a", "serial": "SN1"}], status=200)

    assert client.status.cluster()["connected"] == 1
    assert client.status.services()["san"] == "running"
    assert client.status.iops()["total"] == 30
    assert client.status.bandwidth()["read"] == 100
    assert client.status.cache()["dram"]["Current_Size"] == "10"
    assert client.status.cpu()["current_utilization"] == 10
    assert client.status.enclosures()[0]["serial"] == "SN1"

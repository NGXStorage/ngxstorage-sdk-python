# NGX Storage Manager API v2 SDK — Python

Unified Python client for the NGX Storage Manager API v2.
One client owns **auth, TLS, bounded 725-busy retry, controller failover, and
work-mode selection**; every driver (Cinder FC, Cinder iSCSI, Cinder NFS)
imports this SDK instead of writing its own NGX HTTP client.

Mirrors the Go SDK (`ngxstorage-sdk-go`) with the same architecture and
canonical backend fields.

## Features

- API-key auth (Bearer) — never logged
- Controller failover with work-mode resolution (`single-master`, `master-ready`, `cluster`)
- Bounded 725-busy retry (6 attempts, 10–30s exponential backoff)
- Transport failover replays safe methods (GET/DELETE) only — **POST never replayed**
- Optional TLS verification (skipped by default — NGX Storage Arrays are self-signed)
- Pluggable `BaseMiddleware` chain
- Per-resource services for the API v2 groups with current consumers and
  verified contracts

## Install

```bash
pip install -e .
```

## Quick start

```python
from ngxstorage import NGXClient, ClientConfig

client = NGXClient(ClientConfig(
    controllers=["192.168.1.201", "192.168.1.202"],
    api_key="your-api-key",
    pool_name="pool1",
    # NGX Storage Arrays are self-signed; verification is skipped by default.
    # Provide ca_bundle to enforce a customer trust chain.
    insecure_skip_verify=True,
))

# Resolve the serving controller + pool once before serving traffic.
client.refresh_controller()

# LUN (block)
lun = client.luns.create("vol1", 100)
client.luns.expand(lun["id"], 200)  # additive: grow by 200 GiB
client.luns.delete(lun["id"])

# NFS share (created with export disabled)
share = client.shares.create("share1", 100 * 1024**3)
client.shares.set_export_enabled(share["id"], True)

# Snapshot + clone
snap = client.snapshots.create(lun["id"], "snap1")
clone_id = client.snapshots.clone(snap["id"], "clone1")

# iSCSI target + CHAP
client.iscsi_targets.add_lun(target_id, lun["id"], owner)
client.auth_groups.add_chap(group_id, "user", "pass")

# Pool capacity / cluster status
available, reserved = client.pools.get_configured_capacity()
cluster = client.status.cluster()
```

## Configuration

`ClientConfig` fields:

| Field | Description |
|-------|-------------|
| `controllers` | 1–2 controller IPs/hostnames (required) |
| `api_key` | Bearer token (required, never logged) |
| `pool_name` | Canonical pool name; empty skips pool ownership checks |
| `insecure_skip_verify` | Skip TLS verification (default `True` for self-signed NGX Storage Arrays) |
| `ca_bundle` | Optional path to a customer CA bundle |
| `middlewares` | `BaseMiddleware` chain, outermost-first |
| `timeout` | Per-request timeout (default 60s) |
| `max_retries` / `base_delay` / `max_delay` | 725-busy retry bounds only (transport failures are never retried by the SDK) |

`ClientConfig.__repr__` redacts the API key.

## Services

| Service | Accessor | Operations |
|---------|----------|------------|
| LUN | `client.luns` | `create`, `get`, `list`, `delete`, `modify`, `expand` |
| Share (NFS) | `client.shares` | `create`, `get`, `list`, `list_names`, `delete`, `modify`, `expand`, `set_export_enabled`, `set_read_only` |
| Snapshot | `client.snapshots` | `create`, `get`, `list`, `list_detail`, `delete`, `delete_all`, `clone`, `restore`, `get_schedule`, `create_schedule`, `delete_schedule` |
| FC target | `client.fc_targets` | `list`, `list_names`, `list_detail`, `get`, `add_lun`, `remove_lun`, `list_initiator_tags`, `create_initiator_tag`, `get_initiator_tag`, `delete_initiator_tag` |
| iSCSI target | `client.iscsi_targets` | `list`, `list_names`, `list_detail`, `get`, `create`, `delete`, `add_lun`, `remove_lun`, `change_name`, `change_auth_group`, `change_portal_group` |
| Auth group | `client.auth_groups` | `create`, `get`, `list`, `list_detail`, `delete`, `add_chap`, `delete_chap`, `add_iqn`, `delete_iqn` |
| Portal group | `client.portal_groups` | `list`, `list_detail`, `get` (`create`/`delete` deprecated — the backend has no such routes) |
| Pool | `client.pools` | `list`, `list_detail`, `get`, `overview`, `get_configured_capacity` |
| Status | `client.status` | `cluster`, `services`, `capacity`, `iops`, `bandwidth`, `cache`, `cpu`, `enclosures`, `license`, `overloaded_volumes` |

## Error handling

The SDK raises typed exceptions; classify without string matching:

```python
from ngxstorage import APIError
from ngxstorage.errors import is_not_found, is_busy, is_already_exists

try:
    client.luns.delete(lun_id)
except APIError as exc:
    if is_not_found(exc):
        pass  # idempotent success
    elif is_busy(exc):
        pass  # 725, already retried
```

`APIError` carries `status_code`, `code`, `message`, `method`, `endpoint`.
Sentinels: `PoolNotFound`, `ClusterNotReady`, `TransportError`.

## Security

- The API key, CHAP passwords, and S3 secret keys are never logged.
- TLS verification is optional: skipped by default because NGX Storage Arrays use
  self-signed certificates and most customers have no private CA/DNS. Pass
  `ca_bundle` to enforce a customer trust chain.
- POST mutations are never replayed after an ambiguous transport failure.

## Canonical backend fields

Reads use the live backend JSON contract (nested `capacity.soft_quota`,
`exports.nfs.enabled`/`read_only`); writes use the canonical flat fields
(`soft_quota`, `nfs_export`, `nfs_read_only`). The SDK does not probe
alternate names.

## Test

```bash
pip install -e ".[test]"
PYTHONPATH=src pytest
```

## License

Apache-2.0

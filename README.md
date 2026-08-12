# NGX Storage Manager API v2 SDK (Python)

Unified Python SDK for the NGX Storage Manager API v2. Mirrors the Go SDK
(`ngx-sdk-go`) — one client, one auth/retry/failover implementation, and
per-resource services covering every API v2 group.

## Install

```bash
pip install -e .
```

## Usage

```python
from ngxstorage import NGXClient, ClientConfig

client = NGXClient(ClientConfig(
    controllers=["192.168.1.201", "192.168.1.202"],
    api_key="<redacted>",
    pool_name="pool1",
    # NGX appliances are self-signed; verify is skipped by default.
    # Provide ca_bundle to enforce a customer trust chain.
    insecure_skip_verify=True,
))

# LUN (block)
lun = client.luns.create("vol1", 100)
client.luns.expand(lun_id, 200)
client.luns.delete(lun_id)

# FC target
wwpns = client.fc_targets.get_wwpns(target_id)
client.fc_targets.add_lun(target_id, lun_id, owner)

# Snapshot
snap = client.snapshots.create(volume_id, "snap1")
clone_id = client.snapshots.clone(snap_id, "clone1")

# Pool / status
pools = client.pools.list()
cluster = client.status.cluster()
```

## Security

- The API key, CHAP passwords, and S3 secret keys are never logged.
- TLS verification is optional: skipped by default (self-signed NGX
  appliances); set `ca_bundle` to enforce a customer trust chain.

## Test

```bash
pip install -e ".[test]"
pytest
```

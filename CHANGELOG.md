# Changelog

## Unreleased

### Added

- `portal_groups.list_detail` reads GET /api/v2/portal_group/list
  (listen_ips documents).

### Contract fixes (verified against the deployed API v2)

The following operations sent or decoded fields the backend rejects or never
returns; each is pinned by a mocked wire-contract test:

- `shares.create`: an empty `blocksize` is now omitted (the create route
  rejects `""` with 400/5008; backend default 128k applies), and
  `flash_cache`/`dram_cache`/`flashtier_limit` — which the create route does
  not declare — are applied with a follow-up modify using the canonical
  modify keys (`dram_cache`, `flash_cache`, `flashtier_blocksize_limit`).
- `fc_targets.create_initiator_tag(initiator_naa, tag)` sends the fields the
  backend requires (`initiator_naa`, 16 hex chars; `tag`, alias name) and
  returns the `{id, initiator_naa, tag}` document. The previous
  `(name, initiator_ids)` signature was rejected with 400/5008.
- `pools.overview` is typed as `list` (the backend replies with a bare array
  whose entries lack the pool id/name) and
  `status.overloaded_volumes` as `dict` (the backend wraps the report in
  `{overloaded_volumes, last_check_time}`).
- `auth_groups.create` returns the numeric group id as a string.
- `luns.expand` documents the additive-increment size contract (the backend
  grows the LUN by `size` on top of the current capacity).

### Changed

- Breaking: `fc_targets.create_initiator_tag` signature and the
  `pools.overview` / `status.overloaded_volumes` return types now match the
  deployed wire contract; the previous calls were rejected or returned the
  wrong shape.

### Deprecated

- `portal_groups.create` / `portal_groups.delete` — the deployed API has no
  portal-group create/delete routes; the calls return 5012. Retained for
  released v1.0.0 runtime compatibility only.

### Removed (never released)

- The unshipped, consumerless public surface introduced after the `v1.0.0`
  tag: the `hardware`, `info`, `initiator`, `log`, `network`,
  `services`/NFS-control and `user` service modules with their lazy client
  accessors and tests, plus `CODE_AUTH_GROUP_EXISTS` (with its 519
  `is_already_exists` extension) and the consumerless helpers
  `is_unauthorized`, `is_transport_error`, `http_status_from_error`.
  None of this ever shipped in a release.

### Changed

- Retry is caller-owned: `max_retries` bounds 725-busy attempts only;
  transport failures are never retried by the SDK. Safe GET/DELETE keep at
  most one cross-controller replay after a transport failure;
  POST/PUT/PATCH are never replayed. Driver/caller code owns any
  operation-specific retry or backoff.
- `str(APIError)` now starts with `ngxstorage api error:` — this changes the
  released `v1.0.0` prefix (`ngx api error:`) and aligns it with the Go SDK.
  The format is pinned by `test_api_error_str_format_pinned`.
- Stricter `ClientConfig` controller validation: trimmed, non-empty, unique
  controllers (configs like `["a", " a "]` that `v1.0.0` accepted are now
  rejected).
- Raw response bodies are never retained and server-derived error messages
  are redacted of the configured API key (`APIError.body` only ever existed
  in the unreleased line and is gone).

### Compatibility debt (recorded, not repaired)

- Cross-repo: the Go SDK's `AuthGroup.ChapStatus` changed from `bool` to
  `FlexBool` after `v1.0.0`; see the Go changelog. No Python surface is
  affected.

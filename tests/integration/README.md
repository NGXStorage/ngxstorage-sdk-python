# NGX SDK — Canlı Integration Testleri

Bu testler **gerçek NGX Storage Array**'e karşı çalışır ve mocked unit
testlerin yakalayamadığı API contract'larını doğrular:

- `luns.create` response'unu (`{"luns":[...]}`) parse edip LUN döndürdüğünü
- `iscsitarget.create`'in mandatory key'leri (`auth_group_id` +
  `portal_group_id`) gönderdiğini
- `refresh_controller` work-mode çözümlemesini
- share/snapshot create'in ID çözümlemesini

## Ön Koşul

Bir NGX Storage Array'e erişim. Test stack'leri için
`Integrations/Openstack/Cinder/Driver/Unified/../` — hayır, genel test
altyapısı `.opencode/plans/05.5-test/INFRASTRUCTURE.md`'de.

## Nasıl Çalıştırılır

```bash
NGX_CONTROLLERS=192.168.1.201,192.168.1.202 \
NGX_API_KEY=<api-key> \
NGX_POOL_NAME=openstackSSD1 \
pytest tests/integration -v
```

## Davranış

- `NGX_CONTROLLERS` / `NGX_API_KEY` **set edilmemişse** tüm testler **skip** eder
  (normal CI'da güvenli).
- Her test kendi kaynağını oluşturur ve `finally` ile temizler (LUN, share,
  snapshot, auth group, iSCSI target).
- Testler **yazılabilir** backend işlemleri yapar — production array'inde
  çalıştırma, test pool'u kullan.

## Test Senaryoları

| Test | Doğruladığı |
|------|-------------|
| `test_refresh_controller_resolves_master` | work-mode (master-ready) |
| `test_lun_lifecycle` | create → id, expand, idempotent delete |
| `test_share_lifecycle` | create → id resolution, export enable |
| `test_snapshot_and_clone` | snapshot id, clone → volume id |
| `test_fc_target_list` | pre-created FC target listesi |
| `test_iscsi_target_create_requires_auth_and_portal` | mandatory keys payload |
| `test_pool_capacity` | configured pool capacity |

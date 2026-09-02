# Sprint 18 — Early-Life Surveillance & Release Promotion Evidence

Versi 0.25.0 menambahkan observasi terstruktur setelah limited rollout selesai.
Workflow ini mencatat bukti dan keputusan; tidak mengaktifkan fitur, memasang
software, atau mengubah workstation secara otomatis.

## Binding dan snapshot

Sesi hanya dapat dibuat dari rollout `COMPLETED` yang cocok dengan versi/schema
aktif dan memiliki ledger go-live serta rollout valid. Snapshot memakai data
agregat non-MOCK sejak sesi dibuat:

- total resep dan CRITICAL;
- alert CRITICAL belum diakui;
- intervensi apoteker terbuka;
- polling run dengan error/kegagalan;
- health state dan validitas audit chain.

Tidak ada nomor resep, RM, nama pasien, message alert, atau catatan klinis yang
disalin ke tabel surveillance.

## Promotion gate

Default minimum adalah dua snapshot, rentang observasi 24 jam, dan snapshot
terbaru maksimal berumur 24 jam. Promotion ditahan jika:

- versi/schema atau ledger upstream berubah/rusak;
- sesi kedaluwarsa;
- snapshot kurang, rentang terlalu pendek, atau snapshot basi;
- belum ada resep non-MOCK;
- health/audit tidak READY;
- alert CRITICAL belum diakui, intervensi terbuka, atau kegagalan polling ada;
- masih ada isu WARNING/CRITICAL terbuka.

## Isu, attestation, dan keputusan

Ringkasan isu/remediasi wajib 10-300 karakter tetapi hanya hash SHA-256 yang
disimpan. Isu atau snapshot baru mencabut attestation sebelumnya.

Setelah evidence bersih, petugas klinis dan IT yang berbeda memberi attestation.
Direktur/Super Admin independen kemudian dapat menetapkan `PROMOTE`. Keputusan
`ROLLBACK` dapat diambil sebagai fail-safe tanpa memenuhi promotion gate.
Keduanya final dan immutable.

## Rollback schema

```powershell
alembic downgrade 0020_limited_rollout
alembic upgrade 0021_early_life_surveillance
```

Downgrade menghapus data Sprint 18 saja dan mempertahankan seluruh go-live serta
limited rollout. Backup terverifikasi tetap wajib sebelum rollback nyata.

## Batas eksternal

Snapshot otomatis tidak menggantikan review klinis, change approval, incident
review, clean-host evidence, Authenticode/waiver, atau keputusan produksi oleh
akun individual. Data operasional aktual tidak disimulasikan dalam qualification
lokal.

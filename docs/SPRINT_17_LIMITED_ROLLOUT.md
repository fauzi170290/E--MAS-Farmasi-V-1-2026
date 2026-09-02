# Sprint 17 — Limited Production Rollout & Operational Guardrails

Versi 0.24.0 menambahkan workflow rollout produksi terbatas setelah go-live
acceptance. Workflow ini adalah control plane dan ledger keputusan; aplikasi
tidak memasang software, mengubah konfigurasi workstation, atau membuka mode
Advisory secara otomatis.

## Kontrak fail-closed

Rollout hanya dapat dibuat jika acceptance:

- berstatus `GO`;
- belum kedaluwarsa;
- menggunakan versi aplikasi dan Alembic head yang sedang berjalan;
- memiliki rantai ledger keputusan yang valid.

Rollout mempunyai expiry sendiri yang tidak pernah melampaui expiry acceptance.
`operational_allowed` hanya bernilai benar saat rollout dan tepat satu wave
berstatus `ACTIVE`, kedua ledger valid, serta seluruh binding masih berlaku.

## Wave dan scope

IT Admin/Super Admin menetapkan maksimum workstation dan satu atau lebih wave.
Jumlah workstation seluruh wave tidak boleh melampaui batas sesi. Wave diproses
berurutan dan hanya satu wave boleh aktif. Perubahan definisi scope/wave diblokir
trigger database setelah dibuat.

## Guardrail insiden

Role klinis, teknis, atau pengambil keputusan dapat mencatat insiden WARNING atau
CRITICAL dan melakukan pause/emergency halt. Ringkasan bebas-teks diubah menjadi
SHA-256 sebelum disimpan; ledger tidak memuat identitas pasien atau teks mentah.

Default guardrail:

- total 3 insiden memicu `AUTO_HALT`;
- 1 insiden CRITICAL memicu `AUTO_HALT`;
- acceptance/rollout kedaluwarsa atau binding invalid menahan operasi.

Resume hanya dapat dilakukan IT Admin/Super Admin setelah alasan mitigasi
dicatat. Auto-halt tidak dianggap sebagai bukti bahwa insiden sudah selesai.

## Closeout tiga pihak

Setelah seluruh wave `COMPLETED`:

1. pemilik klinis memberi attestation closeout;
2. IT Admin/Super Admin yang berbeda memberi attestation teknis;
3. Direktur/Super Admin yang independen menetapkan `COMPLETE`.

Perubahan wave atau insiden baru mencabut attestation closeout terkait. Keputusan
`ROLLBACK` dapat ditetapkan pada status non-final sebagai jalur fail-safe.
`COMPLETE` dan `ROLLED_BACK` bersifat immutable.

## Ledger dan rollback schema

`limited_rollout_ledger` adalah rantai SHA-256 global append-only. Trigger
database menolak update/delete ledger, penghapusan sesi/wave, perubahan binding,
dan perubahan keputusan final.

Rollback schema yang didukung:

```powershell
alembic downgrade 0019_go_live_acceptance
alembic upgrade 0020_limited_rollout
```

Downgrade menghapus tabel Sprint 17 saja. Tabel acceptance dan data Sprint 16
tetap dipertahankan. Backup terverifikasi tetap wajib sebelum rollback nyata.

## Batas penerimaan produksi

Status software `QUALIFIED` tidak sama dengan persetujuan produksi. Clean-host,
upgrade/uninstall preservation, Authenticode atau waiver formal, UAT klinis,
alert-fatigue review, SOP/pelatihan, akun individual tiga pihak, dan keputusan
GO aktual tetap harus dilaksanakan di lingkungan rumah sakit.

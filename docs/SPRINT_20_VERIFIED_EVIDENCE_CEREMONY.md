# Sprint 20 — Verified Evidence Package & Manual Deployment Ceremony

Versi 0.27.0 memperkuat chain-of-custody evidence Production Release Sprint 19.
Fitur ini memverifikasi paket, mengaudit ceremony otorisasi, dan mengekspor
receipt. Fitur ini tidak membuat evidence `PASS`, tidak menandatangani artefak,
tidak memasang aplikasi, dan tidak mengubah sistem produksi.

## Evidence package

Verifier memilih ZIP lokal maksimal 12 MiB. Paket wajib memiliki
`manifest.json` dengan format `EMSS_PRODUCTION_EVIDENCE_PACKAGE_V1` dan binding
exact ke:

- `release_record_id`, versi aplikasi, dan Alembic schema;
- SHA-256 installer;
- set lengkap evidence Sprint 19 dan change approval;
- nama file dan SHA-256 isi setiap evidence;
- SHA-256 snapshot kanonik seluruh evidence dan approval.

ZIP ditolak bila memakai path absolut/traversal, backslash, directory, nama
duplikat, symlink, enkripsi, anggota terlalu besar, terlalu banyak anggota,
anggota yang tidak dideklarasikan, JSON invalid, binding/checksum tidak cocok,
atau key identitas pasien. Database menyimpan metadata hasil verifikasi, bukan
salinan isi paket.

Setiap attempt `VALID` maupun `INVALID` masuk ke audit dan production release
ledger. Riwayat verification append-only. Hanya attempt terbaru yang berlaku;
attempt invalid yang lebih baru sengaja membatalkan kelayakan attempt valid
sebelumnya.

Contoh manifest berikut hanya spesifikasi, bukan evidence produksi:

```json
{
  "format": "EMSS_PRODUCTION_EVIDENCE_PACKAGE_V1",
  "release_record_id": "<UUID>",
  "application_version": "0.27.0",
  "schema_revision": "0023_verified_evidence_ceremony",
  "installer_checksum_sha256": "<64 hex>",
  "evidence_snapshot_sha256": "<64 hex>",
  "evidence": [
    {
      "evidence_type": "CLEAN_INSTALL",
      "path": "evidence/clean-install.json",
      "filename": "clean-install.json",
      "checksum_sha256": "<64 hex>"
    }
  ],
  "change_approval": {
    "path": "approval/change-approval.json",
    "filename": "change-approval.json",
    "checksum_sha256": "<64 hex>"
  }
}
```

## Manual deployment ceremony

Ceremony hanya dapat dibuat untuk record `DRAFT`, latest package `VALID`,
snapshot yang belum stale, change approval tersedia, dan waktu berada di dalam
deployment window. Satu release hanya memiliki satu ceremony immutable.

Ceremony dimulai oleh `DIREKTUR`, lalu memerlukan:

- attestation teknis oleh `IT_ADMIN` atau `SUPER_ADMIN`;
- attestation klinis oleh `APOTEKER`, `CLINICAL_REVIEWER`, atau `KFT`;
- akun teknis dan klinis yang berbeda.

Setelah keduanya tersedia, state menjadi `ATTESTED` dan terminal. Selama masih
`OPEN`, IT/Direktur dapat melakukan abort dengan alasan 10–300 karakter yang
hanya disimpan sebagai SHA-256. Ceremony yang expired, stale, invalid, aborted,
atau tidak lengkap menutup authorization.

Pengambil keputusan `AUTHORIZE` wajib berbeda dari creator release, seluruh
recorder evidence, approver change, verifier package, creator ceremony, dan
kedua attestor. Keputusan tetap dilakukan akun individual rumah sakit.

## Authorization receipt dan batas otomasi

Receipt JSON hanya dapat diekspor setelah authorization aktif dan seluruh gate
masih valid. Receipt memuat release/installer binding, package/snapshot hash,
attestor, window, dan production ledger head. File dibuat exclusive agar tidak
menimpa receipt yang telah ada, dan ekspornya dicatat pada audit/ledger.

Field berikut selalu ada:

```json
"deployment_execution": "NOT_PERFORMED_BY_EMSS"
```

Receipt bukan bukti bahwa deployment telah dilakukan. Eksekusi install,
upgrade, uninstall, rollback, atau perubahan konfigurasi tetap manual di luar
aplikasi sesuai runbook dan kewenangan rumah sakit.

## Migrasi dan kompatibilitas

Migrasi `0023_verified_evidence_ceremony` menambah tabel verification dan
ceremony beserta trigger immutable. Downgrade hanya menghapus tabel Sprint 20;
record, evidence, approval, dan ledger Sprint 19 tetap dipertahankan.

```powershell
alembic downgrade 0022_production_release_authorization
alembic upgrade 0023_verified_evidence_ceremony
```

Setelah upgrade, authorization Sprint 19 yang belum mempunyai package dan
ceremony Sprint 20 otomatis menjadi tidak aktif. Ini adalah perilaku fail-closed
yang disengaja, bukan kehilangan data.

## Batas bukti lokal

Fixture test sintetis hanya membuktikan kontrol software. Fixture bukan
Authenticode/waiver, hasil clean-host, bukti preservasi/rollback, change
approval, deployment window, attestation, atau keputusan aktual rumah sakit.
Tanpa bukti eksternal aktual tersebut, aplikasi tidak boleh dinyatakan
Production Ready.

# Sprint 19 — Production Release Record & Deployment Authorization

Versi 0.26.0 menambahkan record otorisasi produksi setelah Early-Life
Surveillance berstatus `PROMOTED`. Workflow hanya mencatat, memvalidasi, dan
mengaudit evidence serta keputusan. Tidak ada kode yang memasang, meng-upgrade,
menghapus, menjalankan rollback, menghubungi endpoint produksi, atau mengubah
konfigurasi workstation otomatis.

## Binding dan state

Record dibuat oleh `IT_ADMIN`/`SUPER_ADMIN` dan terikat immutable ke:

- surveillance `PROMOTED`, limited rollout, dan acceptance upstream;
- versi aplikasi dan Alembic schema aktif;
- environment surveillance;
- nama serta SHA-256 installer dari release qualification;
- expiry record 1–30 hari.

State adalah `DRAFT`, `AUTHORIZED`, `REJECTED`, `REVOKED`, atau
`ROLLBACK_ORDERED`. State terminal tidak dapat diubah. `AUTHORIZED` hanya berarti
izin deployment manual selama seluruh gate dan window masih valid.

## Evidence wajib

Satu dari dua basis distribusi wajib tersedia:

- `AUTHENTICODE` dengan `signature_status: "Valid"`; atau
- `FORMAL_WAIVER` dengan referensi, approver eksternal, dan `valid_until`.

Lima evidence teknis berikut seluruhnya wajib:

- `CLEAN_INSTALL`;
- `CLEAN_UPGRADE`;
- `CLEAN_UNINSTALL`;
- `DATA_PRESERVATION`, dengan checksum sebelum/sesudah identik;
- `ROLLBACK_RESTORE`, dengan rollback dan restore terverifikasi.

Setiap file maksimal 5 MiB, JSON UTF-8, berstatus `PASS`, dan wajib mengikat
`application_version`, `schema_revision`, serta `installer_checksum_sha256`.
Database hanya menyimpan nama file, checksum, tipe, timestamp observasi/expiry,
dan akun recorder. Isi file tidak disalin. Evidence tidak boleh memuat nama,
nomor rekam medis, nomor resep, atau identitas pasien lain.

Contoh struktur minimum Authenticode (nilai di bawah hanya placeholder, bukan
bukti produksi):

```json
{
  "format": "EMSS_PRODUCTION_EVIDENCE_V1",
  "evidence_type": "AUTHENTICODE",
  "status": "PASS",
  "application_version": "0.26.0",
  "schema_revision": "0022_production_release_authorization",
  "installer_checksum_sha256": "<64 hex>",
  "observed_at": "<ISO-8601 dengan timezone>",
  "signature_status": "Valid"
}
```

## Change approval dan keputusan independen

Change approval memakai format `EMSS_PRODUCTION_CHANGE_APPROVAL_V1`, status
`APPROVED`, binding release yang sama, referensi approval, approver eksternal,
serta `deployment_window_start`/`deployment_window_end`. Referensi dan nama
approver disimpan hanya sebagai SHA-256. Window wajib berurutan, belum berakhir,
dan tidak melewati expiry record.

Akun `DIREKTUR` yang mencatat change approval harus berbeda dari pembuat record
dan recorder evidence. Akun `DIREKTUR` lain mengambil keputusan
`AUTHORIZE`/`REJECT`. Authorization ditolak bila decision maker sama dengan
salah satu pihak preparasi/approval atau waktu berada di luar window.

## Fail-closed, revocation, dan rollback

Authorization selalu tidak aktif bila:

- signature/waiver atau evidence teknis belum lengkap/kedaluwarsa;
- change approval/window belum tersedia, belum mulai, atau sudah berakhir;
- record, waiver, versi, schema, installer, atau surveillance tidak cocok;
- ledger go-live, rollout, surveillance, atau production release rusak;
- record `REJECTED`, `REVOKED`, atau `ROLLBACK_ORDERED`.

Direktur dapat mencabut authorization aktif dengan alasan yang disimpan sebagai
hash. IT/Direktur dapat mencatat `EMERGENCY_ROLLBACK_ORDERED` sebagai jalur
fail-safe. Order tersebut tetap harus dieksekusi manusia melalui runbook rumah
sakit; aplikasi sengaja tidak memiliki executor deployment/rollback.

## Ledger, audit, dan rollback schema

Seluruh create, evidence intake, change approval, keputusan, revocation, dan
rollback order masuk ke audit serta ledger SHA-256 append-only. Trigger SQLite
menolak UPDATE/DELETE evidence, approval, dan ledger.

```powershell
alembic downgrade 0021_early_life_surveillance
alembic upgrade 0022_production_release_authorization
```

Downgrade menghapus tabel Sprint 19 saja dan mempertahankan seluruh data serta
ledger go-live, rollout, dan surveillance. Backup terverifikasi tetap wajib
sebelum rollback nyata.

## Batas bukti lokal

Test otomatis memakai fixture JSON sintetis untuk membuktikan kontrol perangkat
lunak. Fixture tersebut bukan Authenticode, waiver, clean-host evidence, change
approval, deployment window, atau keputusan rumah sakit aktual. Selama bukti
eksternal itu belum di-intake oleh akun individual berwenang, status produksi
harus tetap blocked dan tidak boleh dinyatakan Production Ready.

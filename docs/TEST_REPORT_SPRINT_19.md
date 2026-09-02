# Test Report 0.26.0 — Production Release Authorization

## Status

**SPRINT 19 VERIFIED LOCALLY — NOT PRODUCTION READY**

Kontrol perangkat lunak, migrasi, regression, binary, dan installer telah
terverifikasi lokal. Evidence serta keputusan eksternal rumah sakit belum
tersedia dan tidak dibuat-buat dalam laporan ini.

## Gate dan hasil 2026-08-13

- Runtime: Python 3.13.15 64-bit.
- Test: **233 lulus**, 3 warning deprecation adapter SQLite, tanpa failure.
- Branch coverage keseluruhan: **88%** (baseline Sprint 18: 87%).
- Coverage service Production Release: **95%**.
- Coverage service Surveillance: **92%**.
- Alembic: single head `0022_production_release_authorization`.
- Lifecycle data: `PASS` untuk fixture 0020, backup verification, upgrade ke
  0022, restore dan forward migration, downgrade ke 0020, serta re-upgrade
  sehat ke 0022.
- Regression Sprint 18 dan seluruh ledger lama tetap lulus.

## Qualification binary dan installer

- Binary qualification: `QUALIFIED`; smoke health `READY`.
- Installer qualification lokal: `QUALIFIED` dengan policy signature opsional.
- Manifest: 249 file distribusi; report memuat 250 artefak termasuk installer.
- Installer: `e-MSS-Farmasi-RS-Setup-0.26.0-x64.exe`.
- Ukuran installer: 45.158.916 byte.
- SHA-256 installer:
  `EFE217D06D9D975E6BADAB1767E08CBDAF3E777CA782028515931B9503429DA8`.
- Executable: `e-MSS Farmasi RS.exe`.
- Ukuran executable: 11.312.662 byte.
- SHA-256 executable:
  `3F33CA8D3C7E8DC47AA8EA2C3FBC42D1E196F858C00D1C5AB0F85C9DF0303A5D`.
- Authenticode binary/installer: `NotSigned`.

Qualification normal tercatat pada
`outputs/qualification/release-qualification.json` dengan status `QUALIFIED`.
Negative gate `--require-signature` menghasilkan exit code 1 dan laporan
`outputs/qualification/release-qualification-signature-required.json` berstatus
`FAILED`; `AUTHENTICODE_BINARY` dan `AUTHENTICODE_INSTALLER` keduanya
`FAIL: NotSigned`. Gate bertanda tangan terbukti fail-closed.

## Kontrol Sprint 19 yang diuji

- record hanya dari surveillance `PROMOTED` dan binding versi/schema/installer;
- Authenticode `Valid` atau waiver formal ber-expiry sebagai alternatif wajib;
- clean-host install/upgrade/uninstall, data preservation, rollback/restore;
- format, status, checksum, binding, timestamp, timezone, dan expiry evidence;
- change approval ber-hash dan deployment window aktif;
- decision maker independen dari creator, evidence recorder, dan approver;
- state terminal immutable, evidence/approval immutable, ledger append-only;
- expiry, revocation, ledger tamper, reject, dan emergency rollback order;
- UI governance tanpa executor deployment/rollback;
- downgrade 0022→0021 dan re-upgrade tanpa kehilangan ledger upstream.

Fixture evidence pada test bersifat sintetis dan hanya membuktikan validasi
software. Fixture tersebut bukan evidence clean-host atau persetujuan nyata.

## Blocker eksternal tersisa

- Authenticode valid **atau** waiver formal aktual yang belum kedaluwarsa;
- evidence clean-host install, upgrade, dan uninstall pada host representatif;
- evidence preservasi data dan rollback/restore aktual;
- change approval aktual dan deployment window rumah sakit;
- review/attestation akun individual sesuai pemisahan tugas;
- keputusan produksi independen oleh otoritas rumah sakit;
- prosedur eksekusi dan rollback manual oleh tim operasional.

Selama salah satu blocker tersebut belum tersedia, authorization produksi harus
tetap fail-closed dan aplikasi **tidak boleh dinyatakan Production Ready**.

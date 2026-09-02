# Test Report 0.27.0 — Verified Evidence & Deployment Ceremony

## Status

**SPRINT 20 VERIFIED LOCALLY — NOT PRODUCTION READY**

Kontrol software, migrasi, regression, binary, dan installer telah
terverifikasi lokal pada 14 Agustus 2026. Evidence eksternal dan keputusan
rumah sakit tidak dibuat atau disimulasikan sebagai bukti produksi.

## Gate dan hasil

- Runtime: Python 3.13.15 64-bit.
- Test: **240 lulus**, 3 warning deprecation adapter SQLite, tanpa failure.
- Branch coverage keseluruhan: **88%** (gate minimum tetap 87%).
- Coverage service Production Evidence: **94%**.
- Coverage service Production Release: **94%**.
- Coverage service Surveillance: **92%**.
- Alembic: single head `0023_verified_evidence_ceremony`.
- Data lifecycle: `PASS` untuk fixture 0020, backup verification, upgrade ke
  0023, restore dan forward migration, downgrade ke 0020, serta re-upgrade
  sehat ke 0023.
- Rollback test Sprint 20 juga membuktikan downgrade 0023→0022 mempertahankan
  production release record dan ledger Sprint 19.

## Qualification binary dan installer

- Binary qualification: `QUALIFIED`; smoke health `READY`.
- Installer qualification lokal: `QUALIFIED` dengan signature policy opsional.
- Manifest: 250 file distribusi; report memuat 251 artefak termasuk installer.
- Installer: `e-MSS-Farmasi-RS-Setup-0.27.0-x64.exe`.
- Ukuran installer: 46.850.697 byte.
- SHA-256 installer:
  `9C8AA3DE600292DD24859EF9B8BAD24875818B5E9975380F2C2F4DF9DFFE96EC`.
- Executable: `e-MSS Farmasi RS.exe`.
- Ukuran executable: 11.333.764 byte.
- SHA-256 executable:
  `C4B70A1799D51EDF181CD6E3D470D19672331334039AC3E8E76814EDF7A046FB`.
- Authenticode binary/installer: `NotSigned`.

Qualification normal pada
`outputs/qualification/release-qualification.json` berstatus `QUALIFIED`.
Negative gate `--require-signature` menghasilkan exit code 1 dan laporan
`outputs/qualification/release-qualification-signature-required.json` berstatus
`FAILED`; `AUTHENTICODE_BINARY` dan `AUTHENTICODE_INSTALLER` sama-sama
`FAIL: NotSigned`. Gate signature terbukti fail-closed.

## Kontrol Sprint 20 yang diuji

- ZIP traversal, path absolut/backslash, symlink, duplicate, encryption,
  directory, size/member limit, dan undeclared member ditolak;
- manifest terikat exact ke release/version/schema/installer dan checksum
  evidence/change approval Sprint 19;
- checksum isi, set evidence, snapshot kanonik, struktur JSON, dan key identitas
  pasien diverifikasi;
- setiap result `VALID`/`INVALID` append-only dan latest invalid supersedes
  valid sebelumnya;
- ceremony hanya dalam window aktif, terikat latest valid package, dengan
  attestation teknis/klinis berbeda;
- abort ber-hash, state terminal immutable, stale evidence, expiry, dan ledger
  damage menutup gate;
- decision maker independen dari semua pihak preparasi, verifier, creator
  ceremony, dan attestor;
- receipt exclusive ber-checksum menyatakan `NOT_PERFORMED_BY_EMSS`;
- UI governance menyediakan intake/ceremony/receipt tanpa deployment executor;
- downgrade/re-upgrade mempertahankan seluruh data dan ledger lama.

Fixture test bersifat sintetis dan hanya membuktikan validasi software. Fixture
bukan evidence produksi atau persetujuan rumah sakit.

## Blocker eksternal tersisa

- Authenticode valid atau waiver formal aktual yang belum kedaluwarsa;
- clean-host install, upgrade, dan uninstall pada host representatif;
- preservasi data dan rollback/restore aktual;
- evidence package yang disusun dari bukti eksternal tersebut;
- change approval aktual dan deployment window rumah sakit;
- ceremony teknis/klinis oleh akun individual berwenang;
- keputusan produksi independen dan eksekusi manual sesuai runbook.

Selama salah satu blocker belum tersedia, authorization harus tetap fail-closed
dan aplikasi **tidak boleh dinyatakan Production Ready**.

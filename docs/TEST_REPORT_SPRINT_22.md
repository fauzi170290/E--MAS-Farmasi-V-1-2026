# Test Report 0.29.0 — UAT Execution & Independent Acceptance

## Status

**SOFTWARE READY FOR EXTERNAL UAT EXECUTION — UAT NOT YET PERFORMED**

Kontrol software, migrasi, regression, binary, installer, dan starter kit UAT
telah terverifikasi lokal pada 14 Agustus 2026. Tidak ada readiness evidence,
result PASS, sign-off, atau keputusan UAT rumah sakit yang dibuat-buat.

## Gate dan hasil final

- Runtime: Python 3.13.15 64-bit.
- Test: **248 lulus**, 3 warning deprecation adapter SQLite, tanpa failure.
- Branch coverage keseluruhan: **88%**.
- Coverage service UAT Release: **93%**.
- Coverage Production Evidence: **94%**.
- Coverage Production Release: **94%**.
- Coverage Surveillance: **92%**.
- Alembic: single head `0025_uat_execution_acceptance`.
- Lifecycle: `PASS` untuk fixture/backup 0020, upgrade ke 0025, restore dan
  forward migration, rollback ke 0020, serta re-upgrade sehat ke 0025.
- Test migrasi khusus: 0025→0024 mempertahankan dossier Sprint 21; 0024→0023
  mempertahankan seluruh user/data/ledger legacy; re-upgrade ke 0025 lulus.

## Binary dan installer

- Binary qualification: `QUALIFIED`; smoke health `READY`.
- Installer qualification: `QUALIFIED` dengan signature policy opsional.
- Manifest: 252 file distribusi; report memuat 253 artefak termasuk installer.
- Installer: `e-MSS-Farmasi-RS-Setup-0.29.0-x64.exe`.
- Ukuran installer: 46.899.118 byte.
- SHA-256 installer:
  `812CD0AE635E1CE1E4422E111AD758BA85FAAFCBA5D98A9C2A5C6B3FA6090E2F`.
- Executable: `e-MSS Farmasi RS.exe`.
- Ukuran executable: 11.381.811 byte.
- SHA-256 executable:
  `285BA1227351CD5368BC0BF5F071BCEF1F8E31DD9DC0DFD3DBB55D559C63425D`.
- Authenticode binary/installer: `NotSigned`.

Qualification normal berstatus `QUALIFIED`. Negative `--require-signature`
menghasilkan exit code 1 dan report `FAILED`; `AUTHENTICODE_BINARY` serta
`AUTHENTICODE_INSTALLER` sama-sama `FAIL: NotSigned`.

## Starter kit UAT

- File: `e-MSS-Farmasi-UAT-Starter-0.29.0.zip`.
- SHA-256:
  `0430690AA682C6E9833A7CF1B0953E9F90841EC3FA5ACA12B92154AB7CE4FCDA`.
- Format: `EMSS_UAT_EXECUTION_KIT_V1`.
- Candidate status: `DRAFT`.
- Execution status: `NOT_STARTED`.
- Scenario: 10; seluruh result `NOT_RECORDED`.
- Production authorization: `NOT_GRANTED_BY_UAT_KIT`.

## Kontrol yang diuji

- exact binding qualification/version/schema/installer;
- readiness evidence format, freshness, expiry, checksum, field kontrol, dan
  penolakan key identitas pasien;
- attestation dossier klinis/teknis independen dan snapshot binding;
- execution window, sepuluh scenario, owner-role, result attempt append-only;
- latest result fail-closed, issue/remediation ber-hash, sign-off revocation;
- signatory terpisah dari tester/creator dan decision maker pihak ketiga;
- ACCEPT/REJECT, expiry, revocation, receipt exclusive, dan ledger tamper;
- UI tanpa UAT/deployment executor;
- immutable trigger dan kompatibilitas seluruh data lama.

## Blocker eksternal

- site approval dan environment UAT rumah sakit;
- data uji de-identified yang disetujui;
- named user roster, training, dan SOP aktual;
- clean-host, backup/restore, dan Khanza read-only evidence aktual;
- pelaksanaan seluruh sepuluh scenario oleh tester berwenang;
- penyelesaian issue, dual sign-off, dan keputusan independen aktual;
- Authenticode valid atau waiver formal bila diwajibkan kebijakan RS.

Status **UAT PASSED** hanya boleh dinyatakan setelah seluruh blocker evidence
di atas dicatat oleh akun individual dan workflow menghasilkan `ACCEPTED`.
UAT acceptance pun tidak sama dengan Production Ready atau izin deployment.

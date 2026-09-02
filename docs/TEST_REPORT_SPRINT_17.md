# Test Report 0.24.0 — Limited Production Rollout

## Gate yang diverifikasi

- Alembic single head `0020_limited_rollout`.
- Upgrade dari `0019_go_live_acceptance`, downgrade, dan re-upgrade.
- Binding rollout ke acceptance GO, versi, schema, dan expiry.
- Batas workstation, urutan wave, dan larangan wave aktif ganda.
- Pause, resume eksplisit, emergency halt, dan rollback.
- Auto-halt pada ambang insiden CRITICAL/total.
- Attestation klinis/teknis berbeda dan keputusan independen.
- Immutability sesi, wave, keputusan final, dan ledger.
- Konstruksi UI Limited Rollout serta seluruh regresi aplikasi.

## Hasil 2026-08-11

- Runtime gate: Python 3.13.15 64-bit.
- Test: 218 lulus; 3 warning deprecation adapter SQLite, tanpa failure.
- Branch coverage: 87% (gate proyek 85%).
- Alembic: satu head `0020_limited_rollout`.
- Data lifecycle: PASS dari 0019 ke 0020, restore/forward migration,
  downgrade ke 0019, dan re-upgrade ke 0020.
- Binary qualification: `QUALIFIED`.
- Installer qualification: `QUALIFIED`, 248 artefak termanifest.
- Installer: `e-MSS-Farmasi-RS-Setup-0.24.0-x64.exe`, 46.774.081 byte.
- SHA-256 installer:
  `A3AFB3DC674E1F0D355735A3AA6F95ADDC9020BF5B281FBB3B5D492EC281488F`.
- SHA-256 executable:
  `8294C9028DA5AD142B8C1598939D76BC059813E3B170AAF0C99A1B96AF10397B`.
- Paket distribusi tidak memuat `.pyc`, `__pycache__`, PEM, atau private key.

Binary dan installer masih `NotSigned`. Qualification normal mencatat kebijakan
signature tidak diwajibkan oleh build. Negative gate dengan
`--require-signature` menghasilkan `FAILED` untuk `AUTHENTICODE_BINARY` dan
`AUTHENTICODE_INSTALLER`, sehingga kontrol signature terbukti fail-closed.

Bukti eksternal rumah sakit tidak disimulasikan dan tidak termasuk qualification
lokal: clean-host install/upgrade/uninstall, preservasi data staging, UAT klinis,
alert-fatigue review, waiver/signature formal, attestation akun individual, dan
keputusan GO produksi aktual tetap wajib.

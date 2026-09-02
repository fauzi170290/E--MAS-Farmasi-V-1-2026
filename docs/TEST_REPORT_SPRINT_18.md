# Test Report 0.25.0 — Early-Life Surveillance

Gate yang harus lulus:

- Alembic single head `0021_early_life_surveillance`;
- upgrade 0020→0021, downgrade, dan re-upgrade tanpa kehilangan data lama;
- binding rollout/version/schema dan verifikasi seluruh ledger upstream;
- snapshot agregat non-MOCK tanpa identitas pasien;
- minimum observation, freshness, empty-data, operational backlog, dan expiry;
- hashing isu/remediasi, attestation revocation, dan issue immutability;
- attestation klinis/teknis berbeda serta keputusan pihak ketiga;
- rollback fail-safe, ledger append-only, UI, full regression, dan coverage.

## Hasil 2026-08-12

- Runtime gate: Python 3.13.15 64-bit.
- Test: 225 lulus; 3 warning deprecation adapter SQLite, tanpa failure.
- Branch coverage keseluruhan: 87% (gate proyek 85%); service surveillance 92%.
- Alembic: satu head `0021_early_life_surveillance`.
- Data lifecycle: `PASS` untuk upgrade 0020→0021, backup/restore dan forward
  migration, downgrade ke 0020, serta re-upgrade sehat ke 0021.
- Binary qualification: `QUALIFIED`; binary smoke menghasilkan health `READY`.
- Installer qualification: `QUALIFIED`; 248 file distribusi dan satu installer
  (249 artefak total) dicatat beserta checksum.
- Installer: `e-MSS-Farmasi-RS-Setup-0.25.0-x64.exe`, 46.801.690 byte.
- SHA-256 installer:
  `1A7A60510FBE33AD3389D6C46ED2D44E21B4F86FCF224565DC5CA6183EF27E6A`.
- Executable: `e-MSS Farmasi RS.exe`, 11.281.395 byte.
- SHA-256 executable:
  `0B51CE1874221382091237B29A43DBA027D33F5592056325EE2F4F2B693870B5`.

Binary dan installer lokal masih `NotSigned`. Qualification normal lulus dengan
kebijakan signature opsional. Negative gate `--require-signature` menghasilkan
exit code 1 dan status `FAILED`; `AUTHENTICODE_BINARY` serta
`AUTHENTICODE_INSTALLER` keduanya `FAIL: NotSigned`. Kontrol distribusi bertanda
tangan dengan demikian terbukti fail-closed.

Qualification lokal tidak menggantikan bukti eksternal rumah sakit: signature
atau waiver formal, clean-host install/upgrade/uninstall, observasi operasional
aktual, review klinis, attestation akun individual, change approval, dan
keputusan produksi tetap wajib sebelum distribusi atau promosi produksi.

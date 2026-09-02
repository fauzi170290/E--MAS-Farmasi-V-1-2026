# Test Report 0.22.0 â€” Release Qualification & Deployment Evidence

## Hasil final â€” 2026-08-11

- Full regression: **199 test lulus** pada Python 3.13.15 64-bit.
- Branch coverage: **87%**; quality gate minimum 85% terpenuhi.
- Alembic head tetap `0018_evidence_verification`; Sprint 15 tidak mengubah
  schema atau data aplikasi.
- Preflight binary dan installer: `QUALIFIED`.
- Data-lifecycle drill: `PASS`, termasuk upgrade, verified backup, restore,
  downgrade, dan re-upgrade.
- Binary ONEDIR dan installer final: `QUALIFIED`; 246 artefak dicatat dalam
  manifest final.
- Dua peringatan deprecation adapter datetime SQLite tetap terbatas pada test
  kontrak MySQL dan tidak menggagalkan gate.

## Artefak final

- Installer: `e-MSS-Farmasi-RS-Setup-0.22.0-x64.exe`
- Ukuran installer: 46.711.822 byte
- SHA-256 installer:
  `DA2E9E3BCC393ED52AE9DF2B9771BAD3B166B18A7620992FF45022AF527B34B9`
- SHA-256 executable:
  `C5D9507B045383B39B98C9378C2EDF10B5DC547D8E462FCA4321A77A2DDA9B9C`
- Status Authenticode installer dan executable: `NotSigned`; artefak belum
  memenuhi kebijakan code-signing bila RS mewajibkannya.

## Skenario baru

- preflight lulus hanya pada Python 3.13 64-bit dengan toolchain lengkap;
- runtime/toolchain salah menghasilkan `BLOCKED`, bukan kelulusan palsu;
- kontrak versi berbeda atau multiple Alembic head menghasilkan `FAILED`;
- ONEDIR lengkap dan installer dicatat dengan SHA-256 per file;
- file secret/private key dan struktur artefak tidak lengkap ditolak;
- binary smoke memvalidasi health `READY` dan schema revision;
- laporan ditulis atomik dengan format dan kode hasil stabil;
- drill backup, verification, upgrade, restore, downgrade, dan re-upgrade
  mempertahankan pengguna sintetis serta audit chain.

## Gate yang masih wajib sebelum production

Build lokal menggunakan Python 3.13.15, PyInstaller 6.22.0, dan Inno Setup
6.7.3 serta telah menghasilkan laporan `QUALIFIED`. Yang belum dicakup adalah
clean-machine install/upgrade/uninstall test, code-signing, UAT klinis/IT,
drill pada salinan data staging representatif, dan persetujuan go-live.

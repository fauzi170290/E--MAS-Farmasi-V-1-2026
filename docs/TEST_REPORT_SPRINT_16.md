# Test Report 0.23.0 — Go-Live Readiness & Acceptance Evidence

## Hasil final — 2026-08-11

- Full regression: **212 test lulus** pada Python 3.13.15 64-bit.
- Branch coverage: **87%**; baseline Sprint 15 dipertahankan.
- Alembic single head: `0019_go_live_acceptance`.
- Data lifecycle 0018→0019, backup, restore, rollback, dan re-upgrade: `PASS`.
- Binary smoke: `READY` pada schema 0019 dengan audit chain valid.
- Binary dan installer qualification: `QUALIFIED`.
- Manifest final: 247 artefak (246 file ONEDIR dan satu installer), seluruh
  checksum cocok dengan file aktual.
- Tiga warning deprecation adapter datetime SQLite tidak menggagalkan gate dan
  tidak berasal dari kegagalan fungsional Sprint 16.

## Artefak final

- Installer: `e-MSS-Farmasi-RS-Setup-0.23.0-x64.exe`
- Ukuran installer: 46.744.260 byte
- SHA-256 installer:
  `6C586568D17F94E651128A62AACCD869E8752619F9458E2E77FF7B6B4339AAA6`
- SHA-256 executable:
  `0B80F656DB642A7F22278F9AD64284CE409FA16A837726AEBB44CE06C2CC782D`
- Authenticode binary/installer: `NotSigned`.
- Qualification mencatat
  `AUTHENTICODE_POLICY=NOT_REQUIRED_BY_BUILD_POLICY`; checklist
  `TECH-SIGNING` tetap BLOCKED sampai signature atau waiver formal tersedia.

## Skenario baru

- release report bukan `QUALIFIED`, versi/schema salah, atau installer berubah
  ditolak sebelum sesi dibuat;
- role tanpa kewenangan tidak dapat membaca atau mengubah acceptance;
- PASS tanpa bukti checksum ditolak;
- attestation ditolak sampai seluruh item fungsi PASS;
- perubahan evidence mencabut hanya attestation pemilik fungsi tersebut;
- dua attestor dan pengambil keputusan GO wajib tiga pengguna independen;
- NO-GO dapat dicatat tanpa readiness palsu;
- session expiry dan ledger tamper menahan GO;
- keputusan final serta evidence dilindungi trigger UPDATE/DELETE;
- downgrade 0019→0018 mempertahankan data lama dan re-upgrade berhasil;
- Authenticode required menolak binary/installer `NotSigned`.

## Gate eksternal yang belum dijalankan

- clean-host INSTALL/UPGRADE/UNINSTALL pada image Windows yang disetujui;
- preservasi ProgramData memakai data staging representatif;
- UAT klinis, alert-fatigue review, SOP/pelatihan, dan incident drill;
- signature Authenticode atau waiver formal;
- attestation tiga-pihak dan keputusan GO/NO-GO aktual.

Karena gate eksternal tersebut belum mempunyai evidence PASS, aplikasi belum
boleh dinyatakan production-ready meskipun build lokal `QUALIFIED`.

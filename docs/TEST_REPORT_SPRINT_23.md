# Test Report Sprint 23 — Bundled DDI Master Seed

Tanggal verifikasi: 14 Agustus 2026  
Versi aplikasi: `0.30.0`  
Alembic head: `0026_bundled_ddi_master` (single head)

## Ringkasan hasil

- Full regression: **256 passed**, 3 warning, 0 failed, Python 3.13.15.
- Branch coverage keseluruhan: **88%** (minimum gate tetap 87%).
- Coverage `src/emss/services/bundled_ddi.py`: **81%**.
- Preflight: **QUALIFIED**.
- Data lifecycle upgrade/backup/restore/downgrade/re-upgrade: **PASS**.
- Frozen binary qualification: **QUALIFIED**.
- Installer qualification tanpa kewajiban signature: **QUALIFIED**.
- Negative gate `--require-signature`: **FAILED** dengan exit 1 untuk
  `NotSigned`, sesuai perilaku fail-safe.

Warning test hanya berasal dari deprecation adapter datetime SQLite pada
SQLAlchemy/Python 3.13 dan tidak mengubah hasil gate.

## Kontrak master DDI yang dibundel

- Bundle ID: `DDI-KHANZA-v1.0.0`.
- DDI pairs: **5.432**.
- Zat aktif: **159**.
- Status knowledge base: `DRAFT`.
- Semua rule tetap `DRAFT` dan `is_enabled=false`; tidak ada aktivasi klinis
  otomatis.
- Tidak ada akun pengguna atau identitas pasien dalam payload.
- Satu identitas validator sumber telah direduksi menjadi
  `MIGRATED_VALIDATION_REDACTED`.
- SHA-256 database sumber:
  `6B7953B8643F22D4534C8BDADA0DAB532AD0C2717E7D06036360DF7938DBE551`.
- SHA-256 payload gzip:
  `EF207BEDE48CC3A8D1972C28CE8B52A345602EC7DE11451B0C327947FB0926CD`.
- SHA-256 manifest:
  `2EDFE076F5E9A617F5CE3981DAFD8215307B115767C2462E58129647A32A9141`.
- SHA-256 semantik payload:
  `DBD4539134135CEAA2F872FAA7068B4445DD2EAE8414D479DB3F6C22A421D16E`.

Qualification memeriksa keberadaan payload dan manifest, checksum terikat,
jumlah record, canonical pair, status DRAFT, serta tidak adanya identitas
pasien. Log Inno Setup juga mengonfirmasi payload seed dan
`templates/ddi_import_template.xlsx` masuk ke installer.

## Regression perilaku instalasi/upgrade

- Instalasi kosong tanpa administrator menunda seed secara aman.
- Pembuatan administrator pertama melalui CLI atau dialog UI menerapkan seed
  satu kali dalam transaksi yang sama dan mencatat provenance/audit.
- Database yang sudah mempunyai knowledge base atau DDI rule tidak ditimpa.
- Pemanggilan ulang bersifat idempotent dan tidak menggandakan rule.
- Zat aktif dengan normalized name yang sama digunakan kembali tanpa mengubah
  master obat lokal.
- Payload hilang, berubah, melampaui batas, tidak kanonik, atau memiliki
  checksum salah ditolak fail-closed.
- Input rule dari aplikasi, unduh template, preview/import workbook atau CSV,
  commit draft, serta export master tetap tersedia.

## Data lifecycle

Drill dimulai dari fixture legacy `0020_limited_rollout` dan memverifikasi:

1. backup serta checksum;
2. upgrade ke `0026_bundled_ddi_master`;
3. restore backup dan forward migration;
4. downgrade kompatibel kembali ke `0020_limited_rollout`;
5. re-upgrade dan health check pada `0026_bundled_ddi_master`.

Seluruh tahap berstatus **PASS**. Downgrade hanya menghapus struktur provenance
Sprint 23; master klinis yang sudah diterapkan tetap dipreservasi.

## Artefak final

- Installer:
  `outputs/installer/e-MSS-Farmasi-RS-Setup-0.30.0-x64.exe`
- Ukuran: **47.124.126 byte**.
- SHA-256:
  `C8DD773EB639CBEAAF663211905E0D883A6A0FA9FDE60A3CA878D768105B6CA2`.
- Authenticode: **NotSigned**.

Laporan mesin:

- `outputs/qualification/preflight.json`
- `outputs/qualification/data-lifecycle-drill.json`
- `outputs/qualification/binary-qualification.json`
- `outputs/qualification/release-qualification.json`
- `outputs/qualification/release-qualification-signature-required.json`

## Keputusan dan blocker eksternal

Artefak lokal berstatus **QUALIFIED**, tetapi **bukan Production Ready**.
Blocker yang tidak boleh dipalsukan atau dipenuhi otomatis oleh aplikasi:

- Authenticode valid atau waiver formal yang masih berlaku;
- clean-host install/upgrade/uninstall evidence aktual di lingkungan rumah sakit;
- preservasi data dan rollback/restore evidence aktual pada host sasaran;
- UAT aktual dengan bukti dan penandatangan independen;
- change approval, deployment window, dan keputusan produksi rumah sakit.

Tidak ada deployment atau perubahan database produksi yang dilakukan selama
qualification ini.

# Sprint 23 — Bundled DDI Master Seed

## Tujuan

Rilis 0.30.0 membawa master DDI yang sebelumnya dimasukkan pengguna bersama
installer, tanpa menyalin akun, audit, resep, atau data operasional dari
database sumber. Jalur input manual dan workbook tetap dipertahankan.

## Dataset yang dibundel

- Bundle: `DDI-KHANZA-v1.0.0`.
- Zat aktif: 159.
- DDI pairs: 5.432, tanpa canonical pair duplikat.
- Checksum sumber knowledge base:
  `9f5283e7908fbfe679484344567b8b34e58b78ced80c8a3de9a38a805667420a`.
- Checksum bundle gzip:
  `ef207bede48cc3a8d1972c28ce8b52a345602ec7de11451b0c327947fb0926cd`.
- Checksum semantik payload:
  `dbd4539134135ceaa2f872faa7068b4445dd2eae8414d479db3f6c22a421d16e`.
- Tidak ada identitas pasien dan tidak ada akun pengguna dalam bundle.
- Identitas validator yang tersimpan pada satu rule sumber tidak disertakan;
  penanda `MIGRATED_VALIDATION_REDACTED` digunakan untuk menjaga privasi.

Database sumber mencatat knowledge base sebagai `DRAFT`, seluruh 5.432 rule
sebagai `DRAFT`, dan tidak ada rule aktif. Rilis tidak menaikkan status tersebut
secara otomatis. Klaim bahwa konten sumber telah divalidasi tidak menggantikan
review, approval, dan publication formal di rumah sakit tujuan.

## Perilaku instalasi dan upgrade

1. Migrasi membuat tabel provenance ledger immutable.
2. Bundle diverifikasi terhadap checksum yang diikat di source code.
3. Sebelum administrator pertama ada, seed berstatus `DEFERRED_NO_ADMIN`.
4. Perintah `create-admin` menerapkan seed dalam satu transaksi.
5. Jika knowledge base atau DDI rule sudah ada, seed berstatus
   `SKIPPED_EXISTING_MASTER`; tidak ada overwrite atau merge rule.
6. Zat aktif yang sudah ada dengan normalized name sama digunakan kembali,
   tanpa mengubah master/mapping obat yang sudah ada.
7. Keberhasilan dicatat pada audit dan ledger immutable dengan checksum serta
   jumlah record, tanpa menyimpan konten klinis penuh di audit.

Downgrade dari `0026_bundled_ddi_master` menghapus tabel provenance saja.
Knowledge base dan DDI pairs tetap dipertahankan. Re-upgrade membuat struktur
provenance kembali dan tetap tidak menggandakan master yang sudah ada.

## Metode input yang tetap tersedia

- Tambah/ubah rule dari **Knowledge Base & Master DDI** sesuai role.
- **Unduh Template DDI** dari tab **Import DDI**.
- Preview workbook/CSV tanpa mengubah master.
- Commit sebagai versi `DRAFT` dengan backup sebelum commit.
- Export master lengkap untuk audit/pemulihan konten.
- Review klinis, resolution HOLD, approval, dan publication melalui workflow
  yang sudah ada.

## Batas keselamatan

- Seed bukan production authorization dan tidak mengaktifkan alert otomatis.
- Upgrade tidak boleh mengganti master lokal rumah sakit.
- Bundle yang hilang, berubah, terlalu besar, tidak kanonik, atau checksum-nya
  tidak cocok ditolak fail-closed.
- Installer tetap harus melewati qualification dan negative signature gate.
- Status produksi tetap tergantung Authenticode/waiver, clean-host evidence,
  UAT aktual, dan persetujuan rumah sakit.

## Hasil verifikasi final

- Versi `0.30.0`; Alembic single head `0026_bundled_ddi_master`.
- 256 test lulus; branch coverage keseluruhan 88%.
- Data lifecycle/rollback/restore/re-upgrade `PASS`.
- Binary dan installer lokal `QUALIFIED`.
- Installer `e-MSS-Farmasi-RS-Setup-0.30.0-x64.exe` mempunyai SHA-256
  `C8DD773EB639CBEAAF663211905E0D883A6A0FA9FDE60A3CA878D768105B6CA2`.
- Authenticode `NotSigned`; negative signature gate `FAILED` sesuai fail-safe.

Rincian tersedia pada `docs/TEST_REPORT_SPRINT_23.md`.

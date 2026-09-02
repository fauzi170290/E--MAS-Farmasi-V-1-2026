# Test Report — Sprint 2

## Ringkasan

- Tanggal pengujian: 30 Juli 2026
- Platform: Windows 64-bit
- Runtime verifikasi sementara: Python 3.12.13
- PySide6/Qt: 6.11.1
- Pytest: 9.1.1
- Hasil: 46 lulus, 0 gagal
- Coverage core: 87%
- Target coverage: minimal 85%

## Cakupan test

- Migrasi database kosong dan upgrade Sprint 1 ke Sprint 2.
- Preservasi pengguna ketika migrasi dijalankan.
- Pembacaan XLSX/CSV dan penolakan formula.
- Pembatasan berkas XLSX serta perlindungan ZIP/XML.
- Validasi header, versi, duplikasi, status, jumlah komponen, dan urutan.
- Preview tanpa perubahan master.
- Commit transaksional dan pemblokiran batch invalid.
- Pencegahan commit ulang untuk checksum yang sama.
- Mapping tetap inactive dan `PENDING_REVIEW` setelah commit.
- Approval terpisah mengaktifkan mapping.
- Otorisasi role, audit impor, pencarian katalog, serta UI.

## Validasi data nyata

Workbook awal DDI-KHANZA v1.0.0 dibaca tanpa modifikasi:

- preview: 461 valid, 0 invalid;
- commit database uji: 221 obat, 240 mapping, 159 bahan aktif;
- approval database uji: 221 obat dan 240 komponen aktif.

Database uji tersebut bersifat sementara. Tidak ada approval otomatis pada
database aplikasi pengguna.

## Pemeriksaan tambahan

- `pip check`: tidak ada dependency rusak.
- `compileall`: source dan test dapat dikompilasi.
- Migrasi database pengguna pada 31 Juli 2026 berhasil dari `0001_sprint1`
  ke `0002_sprint2` dengan satu akun aktif tetap utuh.
- Health check database pengguna setelah migrasi: `READY`, schema
  `0002_sprint2`, foreign key aktif, WAL aktif, dan rantai audit valid.
- `PRAGMA integrity_check`: `ok`; `PRAGMA foreign_key_check`: tanpa temuan.
- Pemindaian pola credential/private key: tidak boleh menemukan credential
  nyata.

## Keterbatasan dan release gate

Python 3.13 64-bit belum tersedia pada environment Codex ini. Metadata proyek
mewajibkan Python 3.13, tetapi test Sprint 2 dijalankan memakai Python 3.12.13.
Pengujian ulang pada Python 3.13 wajib dilakukan sebelum build executable.

Belum diuji pada Sprint 2:

- koneksi baca database produksi Khanza;
- view integrasi;
- pasangan interaksi DDI dan rule engine;
- antrean resep dan alert klinis;
- installer Windows, restore operasional, silent pilot, dan UAT.

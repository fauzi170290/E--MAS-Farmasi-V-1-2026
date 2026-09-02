# Test Report — Sprint 1

## Ringkasan

- Tanggal pengujian: 30 Juli 2026
- Platform: Windows 64-bit
- Runtime verifikasi sementara: Python 3.12.13
- PySide6/Qt: 6.11.1
- Pytest: 9.1.1
- Hasil: 27 lulus, 0 gagal
- Coverage core: 92%
- Target coverage: minimal 85%

## Cakupan test

- Konfigurasi dan validasi path database.
- Migrasi SQLite dan seed sepuluh role.
- Foreign key, WAL, dan busy timeout.
- Password policy dan Argon2id.
- Pembuatan administrator pertama.
- Login berhasil, login gagal, dan penguncian akun.
- Audit login dan deteksi manipulasi audit.
- Health check.
- Redaksi password, token, dan connection string dari log.
- Login dialog dan health screen PySide6 secara headless.

## Pemeriksaan tambahan

- `pip check`: tidak ada dependency rusak.
- `compileall`: seluruh source dan test dapat dikompilasi.
- Pemindaian pola credential/private key: tidak menemukan pola credential
  nyata pada source.

## Keterbatasan

Python 3.13 64-bit belum tersedia pada environment Codex ini. Metadata proyek
telah membatasi target ke Python 3.13, tetapi test Sprint 1 dijalankan memakai
Python 3.12.13 yang tersedia. Pengujian ulang pada Python 3.13 wajib dilakukan
sebelum build executable dan tidak boleh dilewati sebagai release gate.

Belum diuji pada Sprint 1:

- Database produksi Khanza.
- View integrasi.
- Rule klinis dan workbook DDI.
- Installer Windows.
- Backup/restore.
- Silent pilot dan UAT.


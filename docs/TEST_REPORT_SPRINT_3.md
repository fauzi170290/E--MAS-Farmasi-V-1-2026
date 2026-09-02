# Test Report — Sprint 3

## Ringkasan

- Tanggal: 31 Juli 2026
- Platform: Windows 64-bit
- Runtime verifikasi sementara: Python 3.12.13
- PySide6/Qt: 6.11.1
- Pytest: 9.1.1
- Hasil: 65 lulus, 0 gagal
- Coverage core: 86%
- Target: minimal 85%

## Cakupan

- Migrasi schema sampai `0003_sprint3`.
- Canonical pair dan pencegahan pasangan identik/terbalik.
- Pemetaan severity ke INFO, REVIEW, HIGH_RISK, dan CRITICAL.
- Validasi status interaksi dan severity.
- Impor XLSX/CSV, formula rejection, staging, dan checksum.
- Referensi zat aktif, duplikasi, format tanggal, dan konsistensi sumber.
- Backup otomatis sebelum commit.
- Commit seluruh rule sebagai DRAFT dan inactive.
- Input/pembaruan DDI langsung.
- Duplikasi versi.
- Review, approval, publication, retirement, dan rollback.
- Penahanan workflow bila HOLD klinis belum selesai.
- Otorisasi role, audit, health check, dan UI read-only.

## Validasi workbook nyata

- Master obat: 461/461 baris valid.
- Master DDI: 5.410/5.410 baris valid.
- Canonical violation: 0.
- Duplicate pair: 0.
- Interaksi positif: 543.
- No-interaction terkonfirmasi: 2.505.
- Quick-closure: 1.141.
- NOT_ASSESSABLE: 975.
- EXCLUDED: 246.
- Clinical HOLD: 164.

## Database pengguna

- Backup pramigrasi tervalidasi.
- Schema: `0003_sprint3`.
- Health: `READY`.
- `PRAGMA integrity_check`: `ok`.
- `PRAGMA foreign_key_check`: tanpa temuan.
- Rantai audit: valid.
- Rule enabled: 0.

## Release gate

Runtime Codex yang tersedia masih Python 3.12.13. Pengujian ulang pada Python
3.13 64-bit wajib dilakukan sebelum executable/installer produksi.

Belum diuji pada Sprint 3:

- DDI engine terhadap resep;
- prescription hash dan revision detection;
- mock prescription;
- koneksi baca Khanza;
- system tray, antrean, dan alert.

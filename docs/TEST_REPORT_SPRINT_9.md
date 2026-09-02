# Laporan Verifikasi Sprint 9

Tanggal: 4 Agustus 2026

## Master DDI

- versi: `DDI-KHANZA-v1.0.0`;
- workflow: `DRAFT`;
- total rule: 5.432;
- tambahan impor: 22;
- pasangan duplikat dalam versi: 0;
- clinical review/HOLD belum selesai: 174;
- clinical review/HOLD selesai: 1;
- rule aktif: 0 (sesuai workflow DRAFT).

## Pengujian otomatis

- hasil: 144 lulus, 0 gagal;
- cakupan: service backup/restore, checksum rusak, idempotensi backup harian,
  restore drill, UI admin/non-admin, integrasi, DDI, keamanan, dan konfigurasi
  packaging;
- peringatan: dua deprecation warning adapter datetime sqlite3 dari Python 3.12,
  tidak menyebabkan kegagalan.

## Restore drill dari salinan database nyata

- database aktif hanya dibaca dan disalin; tidak diubah;
- rule sebelum restore: 5.432;
- rule setelah restore: 5.432;
- marker perubahan setelah backup berhasil hilang setelah restore;
- checksum backup: valid;
- rantai audit setelah restore: valid;
- safety backup `PRE_RESTORE`: berhasil dibuat.

## Export Excel master DDI

- rule workbook: 5.432;
- pasangan duplikat: 0;
- formula pada seluruh sheet: 0;
- sheet `DDI_IMPORT` berhasil dibaca dan divalidasi ulang;
- checksum SHA-256 final:
  `ee13e556a6ffff8fba6c96ba30177a5e5053db5d7eafe449b28f25a4a3153a6f`;
- export dicatat pada audit klinis tanpa memuat data pasien atau password.

## Release gate

Definisi ONEDIR dan installer sudah tersedia. Binary final belum dibangun pada
workstation Codex karena runtime yang tersedia adalah Python 3.12.13, sedangkan
release mensyaratkan Python 3.13 64-bit, dan Inno Setup/PyInstaller belum
terpasang. `scripts\build_release.bat` sengaja menolak runtime yang salah.

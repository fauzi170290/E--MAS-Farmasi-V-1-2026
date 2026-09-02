# Laporan Verifikasi Sprint 10

Tanggal: 5 Agustus 2026

## Ruang lingkup

- migrasi `0009_sprint10` dari schema Sprint 8;
- kampanye dan import hasil validasi klinis;
- kalkulasi match dari expected vs actual;
- checklist UAT klinis/teknis dan dual sign-off;
- evaluasi gate advisory pilot;
- silent mode tanpa notifikasi tray/popup;
- penyembunyian antrean/intervensi bagi pengguna farmasi rutin;
- template XLSX validasi klinis dan UAT;
- packaging template pada definisi PyInstaller.

## Hasil otomatis

- 148 test lulus, 0 gagal setelah penambahan ikon dan alert fullscreen;
- branch coverage keseluruhan 87% (ambang 85%);
- migrasi baru dan upgrade dari Sprint 1 terverifikasi;
- gate tetap tertutup tanpa kasus, tanpa UAT PASS, atau tanpa sign-off;
- gate terbuka hanya setelah CRITICAL/HIGH_RISK 100%, racikan dan revisi lulus,
  semua kasus cocok, seluruh UAT PASS, serta persetujuan apoteker dan IT;
- silent mode tidak memanggil `show_screening_alert`;
- ikon ICO memuat ukuran 16, 32, dan 256 piksel; popup fullscreen memakai
  top-most dan `ShowWithoutActivating` serta membuka antrean saat diklik;
- dua deprecation warning adapter datetime SQLite pada Python 3.12 tidak
  menyebabkan kegagalan.

## Verifikasi workbook

- `TEMPLATE_VALIDASI_KLINIS_EMSS_SPRINT10.xlsx`: empat sheet, area input 100
  kasus, data validation untuk severity/boolean, tidak mengandung formula;
- `TEMPLATE_UAT_EMSS_SPRINT10.xlsx`: empat sheet, 12 item default, sign-off dan
  codebook;
- setiap sheet dirender dan diperiksa; tidak ada header penting terpotong atau
  formula error;
- kedua workbook dapat dibaca ulang oleh pembaca XLSX aplikasi.

## Verifikasi visual UI

Menu **Validasi Klinis & UAT** dirender pada database uji terpisah. Banner gate,
tombol template/import/evaluasi, tabel kasus, tabel UAT, serta daftar blocker
terlihat dalam palet terang. Pemeriksaan offscreen tidak memuat font Segoe UI
host, tetapi layout, warna, ukuran kontrol, dan scroll area berhasil dirender.

## Batas release

Status tetap **Ready for Clinical Validation**. Pengujian dilakukan dengan
runtime workspace Python 3.12.13. Build final dan installer tetap wajib diuji
memakai Python 3.13 64-bit pada Windows bersih. Kasus validasi klinis nyata,
silent pilot, UAT rumah sakit, dan alert-fatigue review belum dapat digantikan
oleh test otomatis.

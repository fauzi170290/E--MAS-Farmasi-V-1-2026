# Laporan Verifikasi Sprint 11

Tanggal verifikasi: 5 Agustus 2026

## Ruang lingkup

- agregasi resep non-MOCK untuk periode pilot;
- CRITICAL, HIGH_RISK, beban alert per 100 resep;
- alert ditampilkan, acknowledgement rate, dan median waktu respons;
- CRITICAL yang belum diakui;
- penyelesaian intervensi dan acceptance rate;
- ekspor CSV agregat tanpa identitas pasien;
- audit ekspor dan validasi periode;
- regresi UI, integrasi Khanza read-only, DDI, backup, serta UAT.

## Hasil otomatis

- 150 test lulus;
- branch coverage 87% (batas minimum 85%);
- 2 peringatan deprecation adapter `datetime` SQLite/SQLAlchemy, tanpa kegagalan;
- pemeriksaan whitespace/diff tidak menemukan error.

## Kontrol keselamatan yang terbukti

- resep MOCK tidak masuk metrik pilot;
- CSV tidak memuat nomor resep, nomor RM, atau nama pasien;
- monitoring tidak mengubah environment;
- monitoring tidak membuka gate advisory;
- hanya role validasi/UAT yang dapat melihat atau mengekspor ringkasan;
- ekspor dicatat dalam audit dengan checksum SHA-256.

## Status release

Status tetap **Ready for Clinical Validation**. Aplikasi belum dinyatakan
Ready for Advisory Pilot atau Production Ready karena validasi klinis nyata,
silent pilot, UAT, dual sign-off, dan keputusan alert fatigue rumah sakit belum
selesai.

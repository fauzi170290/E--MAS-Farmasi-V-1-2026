# Phase 3.1 — Compatibility & Deployment Wizard UAT

## RALAN
- [ ] Login sebagai SUPER_ADMIN dan buka Persiapan & Pemeriksaan Instalasi.
- [ ] Pastikan profile RALAN, sumber Desktop/JAB, database lokal, dan KB DDI berstatus LULUS.
- [ ] Buka satu resep RALAN di Khanza lalu jalankan Uji Pembacaan Resep.
- [ ] Pastikan hasil akhir hanya SIAP DIGUNAKAN bila seluruh pemeriksaan kritis LULUS.
- [ ] Pastikan Mode Farmasi tidak memiliki akses commissioning.

## RANAP
- [ ] Ulangi pada instalasi RANAP terpisah; pastikan profile tetap RANAP setelah restart.

## Fail-safe
- [ ] Tutup Khanza: wizard harus menampilkan PERLU PERBAIKAN, tanpa stack trace atau data pasien.

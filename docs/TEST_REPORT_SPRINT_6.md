# Test Report — Sprint 6

## Otomatis

- Seluruh suite setelah penyempurnaan ikon/tray: **111 passed**.
- Cakupan: **86%**, melewati ambang wajib 85%.
- `compileall`: lulus.
- `git diff --check`: lulus.

## Kasus baru

- cursor waktu dengan tie-breaker nomor resep;
- normalisasi timestamp;
- exponential backoff berbatas;
- pipeline mock melewati stability check;
- kegagalan tanpa knowledge base menjadi `ERROR`, bukan `SAFE`;
- koneksi putus menjadi `DISCONNECTED` tanpa membuat antrean aman;
- panel Integrasi Khanza tersedia di UI.

## Database aktif

- Backup pra-migrasi: `pre-sprint6-20260803-095734-emss.db`.
- SHA-256 backup:
  `3116DEFCCCB31549930E5BD59E0D062ECB6F46B1A112E2FE1414E3674D33CCB6`.
- Schema aktif: `0006_sprint6`.
- Health: `READY`; foreign key aktif, WAL aktif, audit chain valid.
- Adapter pengembangan: `MOCK`, status awal `NOT_TESTED` sampai tombol polling
  dijalankan.

## Batas lingkungan

Runtime workspace menggunakan Python 3.12.13. Python 3.13 64-bit tetap menjadi
release gate sebelum build produksi. Arsip `D:\KhanzaHMSWindows.zip` tidak dapat
diakses pada sesi penutupan ini; pemetaan view aktual wajib diverifikasi IT pada
database uji rumah sakit sebelum adapter MySQL diaktifkan.

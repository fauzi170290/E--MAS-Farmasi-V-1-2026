# Test Report — Sprint 7

## Otomatis

- Seluruh suite setelah penyempurnaan dashboard/tema: **125 passed**.
- Coverage: **87%**, melewati ambang wajib 85%.
- `compileall`: lulus.
- Uji migrasi salinan database pengguna: lulus.

## Backup dan migrasi data pengguna

- Backup pra-migrasi: `pre-sprint7-20260804-120121-emss.db`.
- SHA-256:
  `9DC35224A27CEF196076EF47AD62D865F0C637FD9BC851D18C7D629703BDEFF2`.
- `PRAGMA integrity_check`: `ok`.
- Migrasi diuji pada salinan backup, bukan database aktif.
- Schema hasil: `0007_sprint7`.
- Rule DDI tetap: 5.410.
- HOLD selesai tetap: 1 dari 164.

## Kasus yang diverifikasi

- HIGH_RISK/CRITICAL menolak penyelesaian tanpa media/hasil komunikasi;
- terapi diteruskan menolak penyelesaian tanpa alasan klinis;
- intervensi selesai memperbarui status antrean;
- audit klinis tercatat dalam hash-chain;
- dashboard menghitung agregat risiko dan acceptance rate;
- laporan CSV tidak memuat identitas pasien;
- Mode Farmasi tidak dapat mencatat intervensi;
- menu ganti password admin tersedia;
- CRITICAL tidak dapat diselesaikan hanya dengan tombol review biasa.
- password enam karakter yang tidak umum diterima dan password umum ditolak;
- editor multi-baris serta menu memakai latar terang dan teks gelap;
- agregasi bulan, triwulan, tahun, seluruh data, dan tren 12 bulan;
- persentase CRITICAL, HIGH_RISK, tindak lanjut, acceptance, dan kelengkapan;
- dashboard ber-scroll dan tetap dapat digunakan pada jendela 1170 × 670 px.

## Release gate

Runtime workspace masih memakai Python 3.12 untuk pengembangan. Verifikasi
Python 3.13 64-bit, validasi klinis, silent pilot, UAT, backup/restore, dan
installer Windows bersih tetap wajib sebelum status produksi.

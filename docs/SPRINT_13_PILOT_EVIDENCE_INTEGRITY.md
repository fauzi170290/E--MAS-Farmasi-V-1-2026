# Pilot Evidence Export & Ledger Integrity Quarantine

Versi 0.20.0 menutup risiko bahwa ledger yang berubah di luar aplikasi masih
dapat dipakai untuk menjalankan Advisory Pilot. Verifikasi rantai dilakukan
setiap kali status Advisory dievaluasi, termasuk sebelum alert operasional.

## Respons fail-safe

Jika `previous_hash`, payload, metadata event, atau `entry_hash` tidak cocok:

1. safety control `GLOBAL` mengaktifkan karantina persisten;
2. aktivasi aktif dicabut dengan alasan `PILOT_LEDGER_INTEGRITY_FAILURE`;
3. closeout forensik dibuat tanpa menulis event ke rantai yang rusak;
4. audit utama mencatat head hash yang terdeteksi dan aktivasi terdampak;
5. alert ditahan dengan alasan `ADVISORY_LEDGER_QUARANTINED`;
6. permintaan aktivasi baru ditolak.

Karantina tetap aktif setelah restart. Emergency stop tetap independen dan
dapat aktif bersamaan.

## Pemulihan karantina

Hanya IT Admin atau Super Admin yang dapat membuka karantina. Tombol **Buka
Karantina Ledger** baru dapat digunakan setelah verifikasi rantai berhasil.
Referensi backup/insiden 10-300 karakter wajib diisi dan dicatat pada audit.

Prosedur minimum:

1. hentikan aplikasi pada seluruh workstation;
2. simpan salinan forensik database yang bermasalah;
3. verifikasi checksum dan integritas backup sebelum insiden;
4. restore memakai prosedur Backup & Restore;
5. jalankan pemeriksaan health dan buka subtab Ledger Sesi Pilot;
6. pastikan rantai dinyatakan valid;
7. buka karantina dengan referensi tiket insiden;
8. lakukan gate review dan aktivasi dua-person baru.

Jangan memperbaiki hash atau menghapus event secara manual pada database
produksi. Pembukaan karantina tidak mengaktifkan Advisory secara otomatis.

## Paket bukti sesi pilot

Tombol **Ekspor Paket Bukti** menghasilkan ZIP atomik berisi:

- `manifest.json`;
- `pilot_session_ledger.csv`;
- `pilot_shift_closeouts.csv`.

Manifest memuat format `EMSS_PILOT_EVIDENCE_V1`, versi aplikasi, schema
revision, waktu ekspor, jumlah event/closeout, head hash ledger, dan checksum
SHA-256 kedua CSV. Checksum ZIP final dicatat pada audit dan ditampilkan di UI.

Paket tidak memuat nama pasien, ID/RM pasien, nomor resep, unit pelayanan,
pesan alert, ataupun catatan klinis bebas. ID pengguna lokal dipertahankan
untuk akuntabilitas petugas.

## Migrasi dan rollback

Migrasi `0017_pilot_ledger_quarantine` hanya menambah kolom safety control dan
foreign key nullable. Default karantina untuk instalasi lama adalah nonaktif;
ledger dan closeout 0.19.0 tidak ditulis ulang.

Rollback ke `0016_shift_closeout_ledger` menghapus metadata karantina tanpa
menghapus ledger, closeout, aktivasi, pengguna, atau audit. Backup terverifikasi
tetap wajib sebelum rollback produksi.

## Checklist UAT

- Ekspor paket dan cocokkan checksum ZIP serta checksum CSV pada manifest.
- Pastikan pencarian nama pasien/RM/nomor resep pada arsip tidak menemukan data.
- Uji salinan database nonproduksi dengan perubahan payload ledger.
- Pastikan status berubah ke `LEDGER_QUARANTINED` dan alert tidak ditampilkan.
- Pastikan aktivasi baru serta pembukaan karantina ditolak selama rantai rusak.
- Restore data uji, verifikasi rantai, buka karantina, dan pastikan aktivasi baru
  masih wajib.

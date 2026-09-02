# Backup & Restore Sprint 9

## Tujuan dan batasan

Backup melindungi database lokal e-MSS. Fitur ini tidak menulis atau memulihkan
database SIMRS Khanza. Password integrasi tidak pernah masuk ke backup maupun
snapshot konfigurasi.

Lokasi default produksi:

- database aktif: `C:\ProgramData\eMSSFarmasi\Database\emss.db`;
- backup: `C:\ProgramData\eMSSFarmasi\Backups`;
- konfigurasi: `C:\ProgramData\eMSSFarmasi\config.toml`.

Setiap backup terdiri dari file `.db`, manifest `.manifest.json`, dan snapshot
`.config.json`. Manifest memuat SHA-256, ukuran, revisi schema, alasan, dan waktu.

## Operasi dari aplikasi

1. Login sebagai `SUPER_ADMIN` atau `IT_ADMIN`.
2. Buka **Backup & Restore**.
3. Klik **Buat Backup Sekarang** dan tunggu pesan “Backup selesai”.
4. Pilih hasil backup lalu klik **Verifikasi Terpilih**.
5. Pastikan muncul pesan bahwa checksum dan integritas sesuai.

Backup harian diperiksa saat jendela utama dibuka dan dibuat maksimal satu kali
per tanggal. Default retensi adalah 30 hari serta maksimal 30 backup. Nilai dapat
diubah lewat `backup_retention_days` dan `backup_retention_count`.

## Restore

1. Hentikan aktivitas input/import dan tunggu polling Khanza selesai.
2. Pilih backup yang waktu dan alasannya benar.
3. Klik **Verifikasi Terpilih**.
4. Klik **Restore Terpilih**, baca dampak, lalu konfirmasi.
5. Sistem membuat `PRE_RESTORE`, memverifikasi sumber, mengganti database,
   menjalankan migrasi yang diperlukan, dan memeriksa integritas.
6. Setelah pesan berhasil, aplikasi ditutup. Jalankan kembali e-MSS.
7. Periksa **Ringkasan**, **Integrasi Khanza**, dan jumlah master DDI.

Jika restore gagal, sistem berusaha mengembalikan safety backup dan menampilkan
pesan gagal. Jangan menghapus file apa pun; simpan log dan hubungi IT.

## CLI untuk IT

```powershell
e-MSS Farmasi RS.exe --config C:\ProgramData\eMSSFarmasi\config.toml backup
e-MSS Farmasi RS.exe --config C:\ProgramData\eMSSFarmasi\config.toml backup-list
e-MSS Farmasi RS.exe --config C:\ProgramData\eMSSFarmasi\config.toml backup-verify C:\path\backup.db
e-MSS Farmasi RS.exe --config C:\ProgramData\eMSSFarmasi\config.toml restore C:\path\backup.db --yes
```

Restore CLI tanpa `--yes` selalu dibatalkan.

## Latihan pemulihan berkala

Lakukan minimal setiap triwulan pada salinan/komputer uji:

1. verifikasi checksum;
2. restore ke lingkungan uji;
3. periksa `PRAGMA integrity_check` dan foreign key;
4. periksa revisi schema;
5. cocokkan jumlah master DDI dan mapping;
6. validasi rantai audit;
7. catat waktu pemulihan dan hasilnya.

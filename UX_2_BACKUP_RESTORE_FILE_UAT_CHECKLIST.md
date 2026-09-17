# UX-2 — Backup dan Restore File-Based: Checklist UAT

## PC sumber

1. Masuk menggunakan akun Admin atau Super Admin.
2. Buka **Pencadangan & Pemulihan**.
3. Pastikan penjelasan menyatakan backup hanya untuk database lokal E-MAS, bukan database Khanza.
4. Klik **Buat Backup** dan tunggu status berhasil.
5. Catat nama file, tanggal, ukuran, dan schema pada preview.
6. Klik **Buka Folder Backup**.
7. Salin satu set dengan nama dasar sama ke flashdisk atau folder jaringan:
   - `*.db`
   - `*.manifest.json`
   - `*.config.json`

## PC tujuan

1. Instal dan buka E-MAS, lalu masuk sebagai Admin atau Super Admin.
2. Salin tiga berkas backup tersebut ke folder lokal, flashdisk, atau folder jaringan yang dapat dibaca PC tujuan.
3. Buka **Pencadangan & Pemulihan** lalu klik **Pilih File Backup**.
4. Pilih berkas `*.db`; manifest dan snapshot konfigurasi harus berada di folder yang sama.
5. Pastikan preview menampilkan nama file, tanggal, ukuran, checksum, dan schema; tombol **Pulihkan Backup** baru aktif sesudah validasi berhasil.
6. Klik **Pulihkan Backup**, baca peringatan overwrite, lalu konfirmasi hanya bila data lokal PC tujuan memang boleh diganti.
7. Pastikan E-MAS memberi tahu safety backup dibuat dan meminta aplikasi dibuka kembali.
8. Buka ulang E-MAS dan verifikasi data lokal seperti pemetaan, Knowledge Base DDI, serta riwayat yang memang tersimpan pada backup sudah kembali.

## Penolakan aman

1. Coba pilih file `.db` tanpa manifest pasangannya atau file yang telah diubah; pastikan preview menolak file tersebut dan restore tetap tidak aktif.
2. Masuk sebagai user Farmasi biasa; pastikan membuat, memilih, dan memulihkan backup tidak tersedia.

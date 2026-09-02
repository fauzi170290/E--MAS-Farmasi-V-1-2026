# Ikon Windows dan Alert Fullscreen

## Ikon

Ikon e-MSS memakai bentuk kapsul/`e`, tanda medis, dan dua node sirkuit. Siluet
dibuat lebih tebal dan memenuhi bidang agar terbaca pada taskbar 16–32 piksel.
File `emss.ico` berisi ukuran 16, 20, 24, 32, 40, 48, 64, 96, 128, dan 256
pixel. Setelah perubahan aset, tutup seluruh proses e-MSS lalu jalankan kembali.
Binary installer harus dibangun ulang agar ikon baru tertanam pada EXE.

## Alert fullscreen

Alert yang memiliki `notify = true` tetap dikirim melalui notifikasi Windows dan
juga ditampilkan sebagai kartu e-MSS di kanan atas. Kartu memakai flag top-most
Windows dan `ShowWithoutActivating`, sehingga tidak mengambil fokus keyboard
dari aplikasi farmasi yang sedang digunakan.

- CRITICAL/ERROR: kartu merah, tampil 15 detik;
- persistent seperti HIGH_RISK, UNMAPPED, atau INCOMPLETE: kartu oranye, tampil
  15 detik;
- REVIEW/NOT_ASSESSED: kartu biru, tampil 8 detik;
- klik kartu atau balloon Windows: membuka tab **Antrean & Alert**;
- `silent_pilot`: kartu dan balloon tidak ditampilkan.

Kartu top-most menghindari ketergantungan pada Windows Focus Assist untuk alert
utama. Pengujian UAT tetap harus dilakukan pada aplikasi fullscreen yang benar-
benar dipakai rumah sakit. Aplikasi exclusive-fullscreen berbasis hardware dapat
memiliki aturan overlay sendiri; bila ditemukan, aplikasinya perlu memakai mode
borderless/windowed fullscreen atau kebijakan Windows yang sesuai.

## Uji pengguna

1. Tutup e-MSS dari menu system tray, lalu jalankan kembali.
2. Pastikan ikon taskbar dan tray tampil besar serta tajam.
3. Pada **Ringkasan**, klik **Uji Alert Fullscreen (muncul 3 detik)**.
4. Segera pindah ke browser atau Khanza dalam fullscreen.
5. Pastikan kartu merah berlabel UJI muncul di kanan atas tanpa memindahkan
   fokus. Uji ini tidak membuat resep maupun data pasien.
6. Klik kartu dan pastikan tab **Antrean & Alert** terbuka.
7. Ulangi dengan `run_silent_local.bat`; tombol uji tidak tersedia dan alert
   operasional tidak boleh muncul.

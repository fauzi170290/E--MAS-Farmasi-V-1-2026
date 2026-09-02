# Sprint 10 — Validasi Klinis, UAT, dan Silent Pilot

## Status release

Status aplikasi setelah Sprint 10 adalah **Ready for Clinical Validation**.
Status ini bukan Production Ready dan belum berarti layak menjalankan advisory
pilot. Menu gate hanya menilai bukti yang tersimpan; menu tersebut tidak pernah
mengubah environment, mempublikasikan knowledge base, atau menulis ke Khanza.
Kelulusan gate juga belum membuka alert sampai IT Admin/Super Admin melakukan
aktivasi Advisory Pilot secara eksplisit.

## Urutan pelaksanaan

1. Login memakai akun bernama, bukan Mode Farmasi.
2. Buka **Validasi Klinis & UAT**.
3. Unduh **Template Validasi Klinis** dan **Template UAT**.
4. Pada workbook validasi, salin contoh sintetis ke `VALIDATION_CASES`, lalu
   ganti kode obat dengan kode yang telah dipetakan di master RS. Jangan isi
   nama pasien, nomor RM, identitas dokter, atau kredensial.
5. Isi expected result sebagai apoteker sebelum menjalankan uji.
6. Jalankan kasus pada database lokal/test. Isi actual result, reviewer, dan
   review date berdasarkan hasil aplikasi, bukan berdasarkan harapan.
7. Import workbook hasil melalui **Import Hasil Validasi Klinis**. Aplikasi
   menghitung `match`; nilai match manual diabaikan.
8. Jalankan `scripts\run_silent_local.bat` untuk membuktikan resep tetap
   diproses tanpa tray/popup. Pengguna farmasi biasa tidak melihat antrean dan
   intervensi selama silent mode; reviewer berwenang tetap dapat membandingkan
   hasil.
9. Kerjakan checklist UAT satu per satu. Apoteker menguji item klinis; IT
   menguji integrasi read-only, polling/reconnect, silent mode, backup/restore,
   dan instalasi Windows bersih.
10. Setelah semua item miliknya PASS, apoteker dan IT memberi persetujuan
    masing-masing. Klik **Evaluasi Ulang Gate**.
11. Setelah gate lulus dan environment rumah sakit telah disiapkan sebagai
    `advisory_pilot`, IT Admin/Super Admin memilih durasi 4 jam–7 hari lalu
    menekan **Ajukan Aktivasi IT**.
12. Dalam 30 menit, Apoteker/KFT/Clinical Reviewer yang memakai akun berbeda
    menekan **Setujui Aktivasi Klinis**. Petugas tersebut menjadi pemilik shift.

## Gate menuju advisory pilot

Status **Siap Advisory Pilot** hanya muncul bila:

- semua kasus telah ditinjau dan cocok;
- sedikitnya satu kasus CRITICAL dan satu HIGH_RISK diuji, keduanya terdeteksi
  100%;
- tidak ada UNMAPPED yang berubah menjadi SAFE;
- tidak ada keluaran pasangan duplikat;
- uji racikan dan revisi lulus;
- semua checklist UAT PASS;
- UAT disetujui apoteker/validator klinis dan IT.

Jika status, hasil aktual, bukti, atau identitas penguji pada suatu item UAT
diubah setelah sign-off, aplikasi otomatis mencabut persetujuan pemilik item
tersebut. Item harus kembali PASS dan persetujuan terkait harus diberikan ulang;
persetujuan lama tidak dapat dipakai untuk membuka gate.

Gate juga memeriksa ulang metadata persetujuan setiap kali dievaluasi. Sign-off
tanpa identitas approver/waktu, atau yang waktunya lebih lama daripada bukti
pengujian terbaru, dianggap kedaluwarsa dan harus diberikan ulang.
Persetujuan juga terikat pada versi aplikasi. Setelah upgrade, sign-off versi
lama ditolak sampai Apoteker dan IT meninjau bukti lalu menyetujui ulang.
Kampanye validasi juga terikat pada versi aplikasi, screening engine, knowledge
base, dan fingerprint kebijakan keselamatan. Perubahan salah satunya mewajibkan
workbook hasil validasi diimpor ulang terhadap konfigurasi terbaru.
Sign-off Apoteker dan IT menunjuk kampanye yang terakhir diimpor. Jika workbook
baru diimpor, kedua persetujuan harus diberikan ulang untuk kampanye tersebut.
Aktivasi Advisory Pilot menunjuk versi aplikasi, kampanye, sesi UAT, dan waktu
kedua sign-off. Perubahan bukti akan mencabut aktivasi secara otomatis. Setelah
gate kembali lulus, IT Admin/Super Admin tetap harus melakukan aktivasi ulang;
otorisasi lama tidak hidup kembali dengan sendirinya.
Setiap aktivasi memiliki waktu kedaluwarsa. Setelah waktu tersebut, runtime
menahan alert dan IT Admin/Super Admin harus mengevaluasi kondisi lalu membuat
aktivasi baru. Perpanjangan diam-diam tidak diperbolehkan.

Tombol **EMERGENCY STOP** tersedia bagi reviewer klinis, Apoteker, KFT, IT
Admin, dan Super Admin dengan alasan wajib. Latch tersimpan di database dan
tetap aktif setelah restart. Hanya IT Admin/Super Admin yang dapat membukanya;
setelah dibuka, Advisory tetap nonaktif sampai aktivasi eksplisit dilakukan.

## Handover shift klinis

Petugas klinis pengganti login dengan akun sendiri lalu menekan **Ambil Alih
Shift Klinis**. Aktivasi lama tetap aktif selama permintaan menunggu agar tidak
ada celah operasional. IT Admin/Super Admin memeriksa identitas petugas dan gate,
lalu menekan **Sahkan Handover IT** dalam 30 menit. Transaksi tersebut mencabut
aktivasi lama dan membuat aktivasi baru secara atomik. Pemilik shift lama tidak
dapat mengajukan handover kepada dirinya sendiri.

Jika satu syarat gagal, status tetap **Ready for Clinical Validation** dan
daftar blocker ditampilkan. Perbaikan dilakukan pada data, mapping, aturan,
atau aplikasi sesuai akar masalah; gate tidak boleh dilewati secara manual.

## Silent mode

`environment = "silent_pilot"` membuat screening dan pencatatan tetap berjalan,
namun aplikasi tidak memanggil notifikasi tray/popup. Silent mode tetap
menggunakan adapter Khanza read-only. Mode ini bukan advisory: hasil tidak
dipakai untuk keputusan klinis pasien sampai validasi dan UAT disetujui.

## Batas keamanan

- Gunakan database clone/test selama validasi awal.
- Jangan memberikan Full Grant ke aplikasi; gunakan akun MySQL `SELECT` pada
  empat view integrasi.
- Jangan memasukkan data identitas pasien ke workbook validasi/UAT.
- Jangan mengubah `environment` menjadi `advisory_pilot` hanya karena aplikasi
  dapat dibuka. Status gate, persetujuan pemilik produk, apoteker, dan IT tetap
  wajib. Alert tetap terkunci sampai aktivasi eksplisit oleh IT Admin/Super
  Admin dicatat.

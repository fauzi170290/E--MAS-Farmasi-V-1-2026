# E-MAS 0.32.2 — pemeriksaan cepat untuk uji lokal

## Permintaan dan temuan

Pengguna meminta penghapusan tampilan status lengkap/tidak lengkap, mempertahankan
master/interaksi yang sudah ada dan dinyatakan telah divalidasi oleh pengguna,
serta mempercepat popup sesudah validasi Khanza. Obat/interaksi baru akan dimasukkan
melalui pembaruan master berikutnya.

Konfirmasi pemilik mengenai validasi basis dicatat pada 28 Agustus 2026. Paket
yang terpasang berisi 5.432 aturan DDI. Rilis ini tidak mengganti basis, tidak
mengarang identitas/tanda tangan reviewer, dan tidak mengubah metadata persetujuan
atau mempublikasikan versi secara otomatis. Penggunaan basis yang ada pada mode
uji tetap berjalan; koreksi/import pengguna tidak ditimpa saat upgrade.

Diagnosis read-only pada resep kontraindikasi terbaru menunjukkan:

- Diamati 28 Agustus pukul 15:40:19, selesai sekitar 15:40:29 (waktu lokal PC).
- Popup tercatat SHOWN sekitar 0,13 detik sesudah alert dibuat.
- Konfigurasi terpasang masih interval 10 detik; baca ulang untuk kestabilan
  menunggu putaran berikutnya walaupun syarat minimum stabil hanya dua detik.

## Perubahan

1. Pilihan installer **UJI LOKAL CEPAT: database tetap, pemeriksaan 1 detik** mengatur
   interval menjadi satu detik. Cadangan konfigurasi dibuat sebelum perubahan;
   lokasi database, kredensial, audio, histori dan master tetap dipertahankan.
2. Scheduler membangunkan worker pada batas waktu pembacaan stabil, tanpa menunggu
   satu periode penuh lagi. Waktu pemrosesan diperhitungkan dalam periode; satu
   worker saja, tanpa tumpang tindih. Pembacaan stabil minimum dua detik tetap ada.
3. Hasil setiap resep tetap dikirim dari worker saat selesai. Tidak menunggu seluruh
   batch. Polling kosong tidak menghilangkan pilihan resep yang sedang dibaca.
4. Kolom Kelengkapan dan ringkasan lengkap/tidak lengkap di antrean dihapus. Popup
   memakai "Ada catatan pemeriksaan" bila perlu. Rincian masalah sumber, obat belum
   terpetakan dan pasangan belum dinilai tetap terlihat. Penanda internal tetap
   disimpan; hasil tidak dinyatakan aman hanya karena kolom disembunyikan.

Persetujuan master interaksi berbeda dari kepastian bahwa daftar obat resep yang
terbaca mencakup semua perubahan setelah validasi. Karena kontrak item final belum
dibuktikan, catatan tersebut tetap disimpan. Rilis ini tidak mengubah view Khanza.

## Cara memasang

- Tutup E-MAS. Jalankan EXE installer 0.32.2; tidak perlu menjalankan PowerShell.
- Pilih **UJI LOKAL CEPAT: database tetap, pemeriksaan 1 detik** pada pilihan tugas.
  Ini khusus PC/seluruh database Khanza yang telah dikonfirmasi sebagai data uji.
- Setelah membuka aplikasi, halaman Koneksi Khanza harus menunjukkan interval
  penemuan resep **1 detik** dan jeda baca stabil **2 detik** (atau nilai stabil
  lebih besar jika sebelumnya sengaja diatur demikian).
- Jika opsi tersebut tidak dipilih, konfigurasi lama dipertahankan. Pada instalasi
  ini interval lamanya masih 10 detik; jangan menganggap otomatis menjadi 1 detik.
- Installer mempertahankan data ProgramData. Jangan menghapus folder data saat
  uninstall. Tidak perlu uninstall bila upgrade langsung berhasil.

## Batas dan pengujian

Sasaran untuk satu resep pada PC uji dengan sumber cepat dan popup tidak sedang
mengantri adalah beberapa detik. Ini polling cepat, bukan push sesaat setelah
commit. Durasi bisa bertambah bila database lambat, batch besar, resep berubah,
atau ada popup lain yang sedang tampil. Tidak menjanjikan nol detik atau SLA
pelayanan tanpa pengukuran lingkungan sebenarnya.

Uji otomatis memakai sumber sintetis, worker aktual, SQLite, dan popup Qt offscreen.
Itu mengukur alur aplikasi, bukan latensi commit server Khanza nyata atau suara
speaker. Angka uji dan kualifikasi binary/installer dicatat pada laporan keluaran
versi ini, setelah eksekusi selesai. Installer asli akan dipasang dan diuji pengguna.

Push membutuhkan perubahan pada alur validasi Khanza atau mekanisme peristiwa
server yang disetujui; belum dipasang trigger, service, maupun perubahan binlog.

Pemisahan wajib Rajal/Ranap dan suara konfirmasi tanpa popup tetap tercatat pada
`PERBAIKAN_AUDIO_PEMISAHAN_LAYANAN_20260828.md`, belum disertakan pada 0.32.2.

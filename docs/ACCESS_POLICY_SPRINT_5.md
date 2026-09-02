# Rancangan Akses Sprint 5 — Mode Farmasi dan Akses Admin

## Keputusan produk

Aplikasi akan mendukung dua lapis akses:

1. **Mode Farmasi** untuk pekerjaan operasional pada komputer farmasi yang
   telah dikendalikan IT.
2. **Akses berwenang** dengan username dan password untuk perubahan data,
   konfigurasi, serta keputusan administratif/knowledge base.

Mode Farmasi dirancang untuk mengurangi hambatan login tanpa membuka fungsi
perubahan master kepada pengguna anonim.

## Mode Farmasi

- Dapat diaktifkan secara eksplisit oleh IT; default tetap nonaktif.
- Hanya berlaku pada workstation yang telah didaftarkan.
- Dapat melihat panel, antrean, dan hasil skrining yang diperlukan.
- Tidak dapat mengimpor, mengubah, menyetujui, mempublikasikan, me-retire,
  atau melakukan rollback master DDI.
- Tidak dapat mengubah mapping obat, pengguna, konfigurasi, backup, atau
  kebijakan keamanan.
- Intervensi klinis tetap memerlukan identitas operator agar audit tidak
  menjadi anonim.

## Operasi yang wajib meminta autentikasi

- Input/import dan perubahan master obat atau master DDI.
- Review klinis, approval, publication, retirement, dan rollback knowledge base.
- Perubahan mapping dan aktivasi rule.
- Manajemen pengguna, role, konfigurasi, backup/restore, serta ekspor data.
- Perubahan kebijakan alert dan override.

Autentikasi berwenang menggunakan session timeout dan dapat meminta password
ulang sebelum operasi sensitif.

## Batas keamanan

Penghapusan password secara menyeluruh tidak digunakan karena aplikasi
menyimpan data pasien dan jejak intervensi. Mode Farmasi hanya boleh digunakan
bila kontrol Windows, penguncian layar, akses fisik, dan kebijakan workstation
diterapkan oleh IT.

Fondasi teknis telah diterapkan pada Sprint 5 bersama system tray, antrean,
alert, panel, dan single instance. Mode Farmasi tidak dapat mencatat review
klinis atas nama apoteker tertentu; identitas petugas dan intervensi dilanjutkan
pada Sprint 7.

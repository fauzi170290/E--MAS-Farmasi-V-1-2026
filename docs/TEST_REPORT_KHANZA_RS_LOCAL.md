# Laporan pengujian lokal integrasi Khanza RS

Tanggal: 3 Agustus 2026

## Ruang lingkup

- Dump database dan source Khanza diperiksa secara lokal/read-only.
- Tidak ada koneksi ke server asal.
- Tidak ada isi pasien atau kredensial yang disalin ke laporan.
- Pengujian aplikasi memakai data sintetis.

## Hasil

1. Sembilan tabel sumber yang dibutuhkan ditemukan pada dump:
   `resep_obat`, `resep_dokter`, `resep_dokter_racikan`,
   `resep_dokter_racikan_detail`, `databarang`, `reg_periksa`, `pasien`,
   `dokter`, dan `poliklinik`.
2. Alur source Khanza mengonfirmasi tabel `resep_dokter` dan keluarga tabel
   racikan sebagai sumber resep dokter; tabel pemberian obat bukan sumber awal
   yang dipakai view e-MSS.
3. Empat view MariaDB 10.4 telah dibuat sesuai kontrak adapter:
   header, item reguler, komponen racikan, dan master obat.
4. Template view lulus pemeriksaan statis: tepat empat view, alias kontrak
   lengkap, dan tidak memuat `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`,
   `TRUNCATE`, `GRANT`, atau `REVOKE`.
5. Adapter lulus pengujian kontrak dengan database sintetis: koneksi, cursor,
   header, obat reguler, racikan, revision hash, dan master aktif.
6. Seluruh suite aplikasi lulus: **115 passed**.

## Hasil eksekusi MariaDB lokal

- XAMPP MariaDB `10.4.32` berjalan di localhost.
- Dump berhasil diimpor ke database clone `sik_emss_uji_lokal`; terdapat 926
  tabel dasar.
- Data sumber agregat: 22.221 header resep, 110.000 baris obat reguler, 3.060
  header racikan, 8.686 komponen racikan, dan 2.845 master barang.
- View header menghasilkan 22.221 kunci resep unik dan nol `changed_at` kosong.
- View item menghasilkan 109.804 kunci reguler unik dan 8.686 kunci komponen
  racikan unik.
- Master view berisi 2.845 barang; 2.339 berstatus aktif.
- Akun `emss_readonly` berhasil membaca keempat view dan ditolak saat mencoba
  membaca tabel dasar.
- Adapter MySQL nyata lulus koneksi, dua halaman cursor, snapshot reguler dan
  racikan, revision hash, serta paginasi master obat.
- Uji end-to-end teknis terisolasi: 5 terdeteksi, 5 stabil, 5 diproses, 0 gagal.

NetBeans/Ant belum ditemukan. Source Khanza menargetkan Java 8, sedangkan Java
yang terdeteksi adalah Java 12 32-bit. NetBeans tidak diperlukan untuk uji
integrasi database e-MSS ini.

## Keputusan sementara

Kontrak, view, dan adapter sudah lulus uji database clone. Integrasi belum boleh
dipakai untuk keputusan klinis pasien sampai:

- Knowledge Base DDI yang masih `DRAFT` disetujui dan diaktifkan melalui alur
  klinis; uji real-mode membuktikan sistem menolak screening ketika belum aktif;
- pemindaian ulang resep aktif untuk menangkap revisi detail tanpa timestamp
  selesai diimplementasikan dan diuji;
- sampel resep rawat jalan, rawat inap, IGD, serta racikan diverifikasi oleh
  apoteker pada lingkungan uji.

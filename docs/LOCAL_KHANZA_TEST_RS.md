# Pengujian lokal Khanza RS

Dokumen ini berlaku untuk clone lokal dari dump `sik.sql`. Jangan arahkan langkah
ini ke server utama rumah sakit.

## Temuan struktur

- Header resep: `resep_obat`.
- Obat reguler: `resep_dokter`.
- Header dan komponen racikan: `resep_dokter_racikan` serta
  `resep_dokter_racikan_detail`.
- Master obat: `databarang`; nilai `status = '1'` diperlakukan aktif.
- Identitas pasien/unit/dokter: `reg_periksa`, `pasien`, `poliklinik`, dan
  `dokter`.

View yang sesuai berada di
`templates/khanza_integration_views_mariadb104.sql`. View tidak berisi DML dan
tidak mengubah stok, billing, resep, ataupun data pasien di Khanza.

## Urutan uji yang aman

1. Instal dan aktifkan MariaDB/MySQL lokal melalui XAMPP.
2. Buat database clone baru dengan nama yang jelas, misalnya
   `sik_emss_uji_lokal`.
3. Impor dump hanya ke database clone tersebut.
4. Dengan akun admin lokal, pilih database clone dan jalankan script empat view.
5. Uji jumlah dan tipe kolom view tanpa menyalin isi pasien ke laporan.
6. Buat akun `emss_readonly` hanya untuk host lokal dan beri `SELECT` pada empat
   view. Contoh grant tersedia terpisah dan masih berisi placeholder.
7. Atur e-MSS ke adapter `mysql`, database clone, serta akun read-only. Password
   hanya melalui environment `EMSS_KHANZA_PASSWORD`.
8. Jalankan `Periksa Poll Sekarang`; cocokkan hitungan agregat dan status tanpa
   menampilkan data identitas pasien pada tangkapan layar/laporan.

## Batasan klinis yang wajib ditangani

Skema yang diperiksa tidak mempunyai `updated_at` pada tabel detail resep dan
tidak ditemukan log revisi resep yang dapat dijadikan cursor monotonik.
`changed_at` pada view karena itu memakai waktu terakhir yang valid dari:

1. penyerahan obat;
2. pemrosesan farmasi; atau
3. pembuatan resep.

Konsekuensinya, perubahan detail setelah resep pertama kali terbaca tetapi
sebelum status berikutnya berubah tidak selalu menghasilkan timestamp baru.
Sebelum silent pilot, adapter harus memindai ulang resep berstatus
`DIRESEPKAN`/`DIPROSES_FARMASI` dan membandingkan hash isi. Sampai mekanisme
itu lulus uji, integrasi ini hanya layak untuk uji teknis lokal, belum untuk
keputusan klinis pasien.

Kolom `unit_depo` saat ini diisi dari poli/unit pelayanan karena header resep
Khanza yang diperiksa tidak menyimpan kode depo farmasi. Jika rumah sakit perlu
filter depo, IT harus menunjukkan sumber relasi depo yang sah pada kustomisasi
lokal.


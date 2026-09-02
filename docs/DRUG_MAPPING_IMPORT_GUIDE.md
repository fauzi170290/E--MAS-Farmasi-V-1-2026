# Panduan Import Master Obat dan Mapping

## Sebelum mulai

- Gunakan salinan workbook yang telah disetujui untuk review.
- Login sebagai `SUPER_ADMIN`, `KNOWLEDGE_ADMIN`, atau `CLINICAL_REVIEWER`.
- Jangan membuka atau menyimpan ulang workbook dengan perubahan yang belum
  divalidasi.
- Pastikan aplikasi hanya menggunakan database lokal e-MSS, bukan kredensial
  produksi Khanza.

## Import workbook lengkap

1. Jalankan aplikasi dan login.
2. Pilih tab **Import**.
3. Klik **Pilih Berkas** dan pilih workbook `.xlsx`.
4. Klik **Validasi & Preview**.
5. Untuk workbook awal, hasil yang diharapkan adalah 461 valid dan 0 invalid.
6. Tinjau tabel masalah. Jangan commit bila ada baris invalid.
7. Klik **Commit ke Master**.
8. Buka tab **Master Obat & Mapping**. Filter dan periksa obat yang
   `PENDING_REVIEW`.
9. Setelah review klinis, kembali ke tab **Import**, pilih batch yang benar,
   lalu klik **Setujui Batch**.

Approval mengaktifkan mapping komponen. Karena itu, approval hanya dilakukan
setelah nama obat, bahan aktif, jumlah komponen, dan urutannya dinilai benar.

## Format yang didukung

Workbook lengkap harus memiliki sheet:

- `DRUG_MASTER_KHANZA`
- `DRUG_COMPONENT_MAP`

Header berada pada baris 3 sesuai template awal. CSV juga didukung untuk impor
satu jenis tabel berdasarkan header-nya. Encoding CSV harus UTF-8.

## Bila validasi gagal

- Periksa nama sheet dan header persis seperti template.
- Periksa kode Khanza yang kosong atau duplikat.
- Pastikan `component_count` sama dengan jumlah baris komponen.
- Pastikan `component_order` dimulai dari 1 dan berurutan.
- Pastikan versi database konsisten.
- Hilangkan formula; isi impor harus berupa nilai tetap.
- Preview ulang setelah membuat berkas revisi.

Preview lama tetap menjadi jejak audit. Jangan mengedit database SQLite secara
manual.

## Pemulihan

Sebelum migrasi Sprint 2, database pengguna dicadangkan ke folder
`local-data/Backups`. Jika pemulihan diperlukan, tutup aplikasi dan minta tim
IT melakukan restore dari backup terverifikasi; jangan menimpa database aktif
saat aplikasi masih berjalan.

# Sprint 2 — Master Obat dan Mapping

## Tujuan

Menyediakan katalog obat lokal dan alur impor yang aman untuk menyiapkan
mapping kode barang Khanza ke bahan aktif standar. Sprint ini belum menjalankan
rule DDI dan belum membaca database Khanza.

## Komponen

- `ActiveIngredient`: bahan aktif standar yang unik.
- `DrugMaster`: obat berdasarkan kode barang Khanza.
- `DrugAlias`: nama alternatif obat untuk penelusuran dan review.
- `DrugComponentMapping`: urutan komponen bahan aktif setiap obat.
- `ImportBatch`: status, checksum, sumber, dan ringkasan setiap impor.
- `ImportStagingRow`: salinan data preview beserta hasil validasinya.
- `DrugMasterImporter`: preview, validasi, commit, dan approval.
- UI katalog dan impor berbasis role.

## Alur status

1. **Preview** membaca berkas dan menyimpan staging; master belum berubah.
2. **Commit** hanya tersedia bila seluruh baris valid. Data masuk sebagai
   `PENDING_REVIEW` dan mapping belum aktif.
3. **Approval** dilakukan terpisah oleh role yang berwenang. Setelah disetujui,
   obat dan komponen menjadi `APPROVED`, dan komponen mapping aktif.

Checksum berkas mencegah batch sumber yang sudah di-commit atau disetujui
di-commit ulang.

## Batas keselamatan

- Tidak ada koneksi atau penulisan ke database Khanza.
- Tidak ada keputusan klinis atau label `SAFE`.
- Formula dalam sel impor ditolak.
- Workbook asli dibaca saja dan tidak dimodifikasi.
- Berkas macro-enabled dan struktur ZIP/XML yang tidak aman ditolak.
- Persetujuan mapping wajib terpisah dari commit.

## Hasil validasi workbook awal

Workbook `MASTER_DDI_KHANZA_APLIKASI_v1.0.0_2026-07-24 (1).xlsx` berhasil
dipreview dengan:

- 461 baris data valid dan 0 invalid;
- 221 obat;
- 240 komponen mapping;
- 159 bahan aktif unik.

Hasil di atas berasal dari database uji sementara. Database aplikasi pengguna
tidak diisi atau menyetujui batch secara otomatis.

Database aplikasi pengguna telah dimigrasikan dari `0001_sprint1` ke
`0002_sprint2` pada 31 Juli 2026 setelah backup terverifikasi dibuat. Health
check pascamigrasi menghasilkan `READY`; akun pengguna yang ada tetap utuh dan
tabel master obat masih kosong sampai pengguna menjalankan alur impor.

## Acceptance criteria

- Migrasi dari Sprint 1 ke Sprint 2 mempertahankan pengguna yang ada.
- XLSX dan CSV dapat dipreview dengan nomor baris sumber yang akurat.
- Header, duplikasi, versi, jumlah komponen, urutan, dan konsistensi lintas-sheet
  divalidasi.
- Baris invalid memblokir commit.
- Commit bersifat transaksional dan diaudit.
- Mapping hasil commit tidak aktif sebelum approval.
- Hak akses import dan approval dibatasi.
- Katalog dapat dicari dan status mapping terlihat di UI.
- Seluruh test otomatis lulus dengan coverage core minimal 85%.

# Implementasi Batch 3–5 — E-MAS Farmasi

Tanggal: 31 Agustus 2026  
Baseline: 0.34.1

## Batch 3 — antrean

Batch 3 telah dilengkapi dengan filter rentang detected_at pada layanan antrean. Antrean operasional default menampilkan **Masuk E-MAS hari ini (UTC)**; menu Riwayat memilih **Semua data / Riwayat**. Data lama tetap tersimpan dan tidak diubah statusnya.

Label tersebut sengaja menyebut basis waktu masuk E-MAS. Kontrak tanggal pelayanan resep (service_date) dari P0 belum tersedia, sehingga sistem belum mengklaim bahwa filter ini adalah tanggal pelayanan rumah sakit.

## Batch 4 — dashboard

- Periode baru **Hari ini (masuk E-MAS)** menjadi default.
- Pemilih tanggal tersedia untuk melihat hari tertentu.
- Bulanan, Triwulanan, Tahunan dan Seluruh Data tetap tersedia.
- Service dashboard menerima periode DAY dengan batas hari dan pembanding hari sebelumnya.
- Kartu, unit dan ekspor menggunakan periode yang dipilih.
- Tooltip menjelaskan bahwa periode harian sementara berbasis waktu masuk E-MAS.

Perubahan ini tidak menghapus riwayat dan tidak mengubah definisi bahwa agregat berasal dari hasil tersimpan. Perubahan ke service_date harus dilakukan setelah sumber tanggal pelayanan terverifikasi.

## Batch 5 — master dan pair

- Tab **Obat & Kandungan** menjadi **Master Obat**.
- Tab **Data Interaksi Obat** menjadi **Pasangan Interaksi Obat**.
- Dialog pair menggunakan pemilih kandungan aktif dari master E-MAS, tetap dapat mengetik untuk pencarian/validasi.
- Tombol menjadi **Tambah Pasangan DDI** dan **Simpan Pair (Draft)**.
- Pesan dialog menjelaskan bahwa aktivasi langsung menunggu layanan berwenang Batch 6.
- Belum ada tombol aktivasi palsu, CRUD obat baru, atau bypass role. Penyimpanan pair masih mengikuti service lama yang memerlukan versi DRAFT dan role writer; implementasi Simpan & Aktifkan SUPER_ADMIN/KFT tetap Batch 6.

## Verifikasi

- Tes terarah UI, dashboard, knowledge base: **53 passed, 2 warnings**.
- Tes Batch 2 sebelumnya: **64 passed, 5 warnings**.
- python -m compileall -q src/emss: lulus.
- Tidak ada migration, perubahan database operasional, atau installer yang dibuat.


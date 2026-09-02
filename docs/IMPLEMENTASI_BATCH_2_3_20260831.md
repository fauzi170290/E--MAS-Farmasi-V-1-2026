# Implementasi Batch 2 dan 3 — E-MAS Farmasi

Tanggal: 31 Agustus 2026  
Baseline: 0.34.1

## Batch 2 — pilot UI modern

- Form Intervensi Apoteker memiliki container lokal `interventionFormPage` dengan latar terang dan teks label gelap agar terbaca pada stylesheet/palette berbeda.
- Antrean diberi styling pilot lokal dan tombol umum memakai radius ringan dengan aksen teal pada aksi utama.
- Tidak ada perubahan pada validasi, status klinis, penyimpanan intervensi, atau hak akses.

## Batch 3 — antrean harian (implementasi aman sementara)

- `ProcessingQueueService.list_items()` menerima batas `detected_after`/`detected_before` dengan interval akhir eksklusif.
- Antrean membuka filter `Masuk E-MAS hari ini (UTC)` secara default dan menyediakan `Semua data / Riwayat`.
- Menu Riwayat otomatis memilih seluruh data; menu antrean operasional kembali ke filter hari berjalan.
- Data lama tidak dihapus, tidak diubah menjadi REVIEWED, dan tetap dapat ditelusuri.
- Ringkasan membedakan total tersimpan dari jumlah yang sedang ditampilkan.

Batasan yang sengaja dipertahankan: filter ini berbasis `detected_at` (waktu masuk E-MAS), bukan tanggal pelayanan resep. Kontrak `service_date` dari P0 tetap menjadi pekerjaan berikutnya sebelum label klinis “resep pelayanan hari ini” digunakan.

## Verifikasi

- `python -m compileall -q src/emss`: lulus.
- Tes terarah UI dan screening/queue: **64 passed, 5 warnings**.
- Direktori sementara pytest memakai `.tmp-tests-b23` karena direktori temporary Windows global menolak akses.
- Tidak ada database operasional atau installer yang disentuh.

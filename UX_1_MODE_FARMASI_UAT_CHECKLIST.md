# UX-1 — Mode Farmasi dan Antrean Resep: Checklist UAT

## Persiapan

1. Jalankan E-MAS dan masuk ke **Mode Farmasi**.
2. Pastikan sedikitnya satu hasil resep tersedia pada **Antrean Resep**.

## Header dan status Khanza

1. Pastikan header menampilkan wordmark E-MAS, area pelayanan, dan status kecil di satu area ringkas.
2. Saat Khanza terhubung, pastikan pill hijau bertuliskan **Terhubung ke Khanza**.
3. Tutup Khanza dengan aman; pastikan pill kuning bertuliskan **Menunggu Khanza dibuka**.
4. Buka Khanza kembali; pastikan status berubah otomatis menjadi hijau tanpa restart E-MAS.
5. Jika integrasi benar-benar gagal, pastikan pill merah bertuliskan **Gangguan koneksi Khanza** dan gunakan halaman diagnostik untuk detail teknis.

## Antrean resep dan detail

1. Periksa bahwa area tabel antrean berada di atas dan rincian skrining berada di bawah.
2. Pilih satu resep. Pastikan pasangan obat, status, dan rekomendasi tampil di rincian bawah.
3. Tarik garis pemisah di antara antrean dan rincian untuk memberi ruang lebih besar kepada rincian; tutup dan buka E-MAS kembali, lalu pastikan ukuran pilihan tetap dipakai.
4. Pada layar 1024 × 720 atau lebih pendek, pastikan pencarian, filter, **Muat Ulang**, **Tandai Sudah Ditinjau**, **Coba Periksa Ulang**, dan **Catat Intervensi Apoteker** tetap dapat dijangkau.
5. Ubah filter dan pilih resep lain; pastikan rincian berpindah sesuai resep yang dipilih.

## Konsistensi

1. Buka Intervensi Apoteker, Riwayat Pemeriksaan, Riwayat Intervensi, Dashboard Kajian pDDI, dan halaman referensi.
2. Pastikan header ringkas tetap konsisten dan tabel menjadi area utama halaman.
3. Pastikan popup, audio, overlay, dan hasil skrining DDI tetap berfungsi seperti sebelum UX-1.

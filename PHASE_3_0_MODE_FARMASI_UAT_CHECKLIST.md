# Phase 3.0 — Mode Farmasi Clinical Safety Assistant: UAT

Gunakan data resep yang diizinkan. Jangan tulis identitas pasien pada catatan hasil UAT.

## Rawat Jalan

- [ ] Buka E-MAS pada instalasi yang telah dikunci sebagai Rawat Jalan.
- [ ] Pastikan judul utama berbunyi `E-MAS — Farmasi Rawat Jalan`.
- [ ] Buka **Antrean Resep** dan pastikan kolomnya **Waktu**, **No. Resep**, **Pasien**, **Hasil Pemeriksaan**, **Peringatan**, dan **Tinjauan**.
- [ ] Pastikan tidak ada kolom atau filter Asal Poli, Unit, Poli, maupun Depo.
- [ ] Pastikan resep yang belum ditinjau berada di bagian atas, lalu resep yang sudah ditandai ditinjau berada di bagian bawah.
- [ ] Pilih resep baru dan gunakan **Tandai Sudah Ditinjau**; pastikan resep berpindah ke bagian bawah setelah tinjauan tersimpan.
- [ ] Pastikan menu hanya menampilkan Antrean Resep, Riwayat Pemeriksaan, dan Status E-MAS.
- [ ] Periksa resep tanpa DDI: status menampilkan **Tidak ditemukan DDI**.
- [ ] Periksa resep dengan DDI: status menampilkan **Interaksi Obat**; popup, audio, dan overlay tetap benar.
- [ ] Periksa resep unmapped/incomplete: status menampilkan **Pemeriksaan belum lengkap** dan tidak pernah menyatakan aman.
- [ ] Lakukan navigasi cepat A → B → C; pastikan hasil tidak tertukar dan overlay tidak stale.

## Rawat Inap

- [ ] Jalankan pada instalasi RANAP terpisah yang telah di-commission sebagai Rawat Inap.
- [ ] Pastikan judul utama berbunyi `E-MAS — Farmasi Rawat Inap`.
- [ ] Pastikan struktur antrian sama ringkasnya dan hanya resep RANAP yang diproses.
- [ ] Uji satu resep DDI dasar; popup, audio, dan overlay tetap benar.

## Pemisahan akses

- [ ] Masuk Mode Farmasi: menu Master Obat, Mapping, Obat Belum Dipetakan, Knowledge Base, Import/Export, konfigurasi, dan diagnostik tidak terlihat.
- [ ] Masuk sebagai Super Admin: menu administratif tetap tersedia dan tindakan backend tetap mengikuti RBAC yang ada.

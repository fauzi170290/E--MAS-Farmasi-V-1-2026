# Phase 3.4A — Backup & Restore UAT

1. Login sebagai Admin/Super Admin dan buka **Pencadangan & Pemulihan**.
2. Buat backup; pastikan database, manifest checksum, dan snapshot konfigurasi nonsensitif terbentuk.
3. Periksa ringkasan schema/version backup dan validasi checksum.
4. Ubah data uji yang aman, lalu pilih backup dan lakukan restore dengan konfirmasi eksplisit.
5. Restart E-MAS; pastikan state kembali ke backup dan aplikasi dapat melakukan screening.
6. Login non-admin; pastikan tindakan backup/restore yang dilindungi ditolak.
7. Coba file backup tidak valid pada lingkungan uji; pastikan restore ditolak tanpa mengubah database aktif.

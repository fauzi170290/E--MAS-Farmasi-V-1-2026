# Phase 3.5 — Operational Health & Recovery: Checklist UAT

1. Login Admin/Super Admin, buka **Pengaturan → Status Operasional & Pemulihan**, lalu pilih **Periksa Ulang**.
2. Saat semua komponen tersedia, pastikan database, KB Published, commissioning, dan sumber resep menunjukkan status siap serta ringkasan tidak menunjukkan gangguan.
3. Tutup atau putuskan KhanzaBridge secara aman pada lingkungan uji. Pastikan Khanza/JAB dan Bridge menampilkan gangguan tanpa aplikasi crash.
4. Klik **Coba Pulihkan Bridge** sekali. Pastikan bridge kembali bila Khanza/JAB tersedia dan tidak ada bridge kedua.
5. Simulasikan gangguan tulis database sekunder pada lingkungan uji; pastikan status menampilkan gangguan dan screening valid tidak dinyatakan SAFE secara keliru.
6. Pastikan ketika KB Published tidak tersedia, status KB adalah gangguan dan DRAFT tidak ditampilkan sebagai pengganti produksi.
7. Uji audio atau overlay unavailable. Pastikan popup dan hasil DDI tetap tampil; overlay akan clear/hide dan audio hanya memberi peringatan.
8. Saat pemeriksaan health berlangsung, lakukan urutan resep A → B → C dan pastikan popup/audio tidak tertahan.
9. Login Apoteker biasa; pastikan recovery administratif tidak tersedia dan service menolak akses.
10. Buka Detail Teknis hanya bila diperlukan untuk petugas IT; jangan salin data pasien ke catatan gangguan.

# Phase 3.4B — Paket Update Knowledge Base DDI: Checklist UAT

1. Login dengan akun `SUPER_ADMIN` atau `KNOWLEDGE_ADMIN`.
2. Buka **Data referensi → Paket Update KB DDI**, pilih paket `.zip`, lalu pilih **Preview & Validasi**.
3. Pastikan KB aktif dan versi paket, jumlah baris, serta insert/update tampil; pastikan belum ada perubahan pada screening production.
4. Ubah satu byte salinan paket dan pastikan checksum ditolak.
5. Coba paket ZIP rusak dan pastikan ditolak dengan pesan jelas.
6. Coba paket dengan versi yang lebih lama dari KB aktif dan pastikan downgrade otomatis ditolak.
7. Pilih **Install sebagai Draft**, setujui konfirmasi, lalu pastikan backup `PRE_KB_UPDATE` muncul pada **Pencadangan & Pemulihan**.
8. Buka **Knowledge Base** dan pastikan versi hasil instalasi berstatus `DRAFT`; review/approval/publish tetap dilakukan di workflow yang sama.
9. Periksa sampel rule: source `MEDSCAPE` dan `DRUGS.COM` masih tampil sebagai source masing-masing.
10. Pastikan conflict/HOLD tetap harus diselesaikan sebelum publish dan tidak ada dua KB `PUBLISHED`.
11. Login sebagai `APOTEKER`; menu paket tidak tersedia dan akses service ditolak.
12. Saat validasi atau install paket sengaja gagal, lakukan screening resep uji: KB aktif lama, popup/audio, dan hasil screening tetap berjalan.

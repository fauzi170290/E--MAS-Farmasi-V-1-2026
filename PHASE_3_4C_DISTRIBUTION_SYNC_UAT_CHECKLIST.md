# Phase 3.4C — Distribusi dan Sinkronisasi Knowledge Base DDI: Checklist UAT

1. Pada PC RALAN, login `SUPER_ADMIN`/`KNOWLEDGE_ADMIN`, buka **Data referensi → Paket Update KB DDI**, pilih folder LAN/media bersama, lalu pilih **Tulis Status Lokal**.
2. Ulangi pada PC RANAP. Pastikan masing-masing laporan menampilkan nama workstation, profile, versi E-MAS, dan KB `Published` tanpa data pasien.
3. Siapkan paket KB v2, pilih paket pada PC Admin, lalu pilih **Preview & Validasi**. Pastikan KB target v2 terlihat dan belum ada KB yang diaktifkan.
4. Pilih **Muat Status Workstation** dari folder yang sama. PC dengan KB v1 harus berstatus **Perlu Update**.
5. Pada masing-masing PC, install paket dengan konfirmasi. Pastikan backup `PRE_KB_UPDATE` dibuat.
6. Selesaikan review, approval, dan publish v2 melalui tab **Knowledge Base** pada setiap PC. Instalasi paket hanya membuat `DRAFT`.
7. Tulis ulang status lokal dari kedua PC dan muat kembali di PC Admin. RALAN serta RANAP harus berstatus **Terbaru** untuk KB v2.
8. Salin lalu rusak satu paket ZIP atau laporan JSON. Pastikan sistem menolaknya/menandainya **Gagal Update** dan KB Published lama tetap dapat dipakai.
9. Login sebagai `APOTEKER`; menu paket dan pemuatan status tidak tersedia.
10. Saat paket atau laporan sengaja gagal, lakukan screening resep uji. Pastikan E-MAS tetap berjalan dan tidak ada perubahan pada popup, audio, atau hasil screening.

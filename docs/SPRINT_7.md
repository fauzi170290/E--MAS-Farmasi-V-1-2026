# Sprint 7 — Intervensi, Audit Klinis, Dashboard, dan Reporting

## Hasil

Sprint 7 menambahkan dokumentasi intervensi apoteker pada database lokal e-MSS.
Tidak ada query tulis ke SIMRS Khanza. Perubahan status intervensi hanya berlaku
di database SQLite e-MSS.

## Alur intervensi

1. Apoteker login menggunakan akun bernama.
2. Apoteker memilih resep di **Antrean & Alert**.
3. Tombol **Catat Intervensi Apoteker** membuka formulir klinis.
4. HIGH_RISK/CRITICAL wajib memuat keputusan, media komunikasi, hasil
   komunikasi, dan pihak yang dihubungi.
5. Keputusan meneruskan terapi wajib memuat alasan klinis.
6. Formulir dapat disimpan sebagai `OPEN` atau ditandai `COMPLETED`.
7. Antrean berubah menjadi `INTERVENTION_OPEN` atau
   `INTERVENTION_COMPLETED`.
8. Audit hash-chain mencatat penciptaan/pembaruan tanpa menyimpan password.

Mode Farmasi tanpa password tidak boleh mencatat intervensi atas nama petugas.
Role yang dapat mencatat adalah `APOTEKER`, `SUPER_ADMIN`, dan
`CLINICAL_REVIEWER`.

## Dashboard dan laporan

Dashboard menyajikan jumlah resep diskrining, CRITICAL, HIGH_RISK, intervensi
terbuka/selesai, acceptance rate, dan agregat per unit. Dashboard manajemen dan
CSV agregat tidak memuat nama pasien, nomor RM, atau identitas pasien lainnya.

Pengguna dapat memilih hasil bulanan, triwulanan, tahunan, atau seluruh data.
Dashboard menampilkan perbandingan volume terhadap periode sebelumnya,
persentase risiko tinggi/CRITICAL, cakupan tindak lanjut, kelengkapan skrining,
tren Januari–Desember, dan persentase per unit/depo. Istilah klinis disertai
penjelasan singkat agar dapat dipahami oleh pengguna manajemen non-apoteker.

Ekspor CSV tersedia bagi admin/manajemen berwenang dan dicatat sebagai
`AGGREGATE_REPORT_EXPORTED` pada audit trail.

## Password admin

Administrator membuka **Akun → Ganti Password Admin**. Dialog tetap meminta
password saat ini, password baru minimal 6 karakter, dan konfirmasi. Password
yang sangat umum tetap ditolak. Hash
Argon2id diperbarui; password tidak masuk log atau audit.

## Konsistensi tema Windows

Editor catatan/alasan, menu Akun, popup pilihan, tooltip, dan kontrol input
memakai warna terang eksplisit. Dengan demikian teks tetap terbaca meskipun
Windows menggunakan tema gelap.

## Schema

Revisi Alembic: `0007_sprint7`.

Tabel baru:

- `pharmacist_intervention`;
- `intervention_detail`.

## Batas sprint

Duplicate therapy, polifarmasi, high-alert, dan LASA merupakan Sprint 8.
Backup/restore lengkap, packaging, dan installer merupakan Sprint 9. Status
aplikasi tetap **Development**, belum untuk keputusan klinis produksi.

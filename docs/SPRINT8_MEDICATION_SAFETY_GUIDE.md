# Panduan Sprint 8 — Keselamatan Obat

Sprint 8 menambahkan duplicate therapy, polifarmasi, high-alert, dan LASA ke
mesin skrining yang sama dengan DDI. Seluruh konfigurasi disimpan di SQLite
lokal e-MSS. Tidak ada `INSERT`, `UPDATE`, atau `DELETE` ke database Khanza.

## Urutan konfigurasi yang disarankan

1. Login sebagai `SUPER_ADMIN`, `KNOWLEDGE_ADMIN`, `CLINICAL_REVIEWER`, atau
   `KFT`.
2. Buka tab **Keselamatan Obat**.
3. Periksa **Kebijakan Polifarmasi**. Default aplikasi adalah 5 zat aktif unik
   untuk polifarmasi dan 10 untuk hiperpolifarmasi. Ubah bila kebijakan rumah
   sakit berbeda, lalu klik **Simpan & Validasi Kebijakan**.
4. Isi **Kelas Terapi** hanya untuk zat aktif yang sudah ada pada master. Rute
   boleh dikosongkan agar profil berlaku untuk semua rute.
5. Isi **High-Alert** berdasarkan kode obat Khanza, kategori, cakupan unit,
   kebutuhan double-check, rekomendasi, dan sumber kebijakan. Gunakan `*` untuk
   semua unit.
6. Isi pasangan **LASA** menggunakan dua kode obat yang berbeda. Pilih salah
   satu kategori: Look-Alike, Sound-Alike, kemasan mirip, kekuatan mirip, nama
   generik mirip, atau nama merek mirip.
7. Uji dengan resep simulasi atau data lokal testing. Tinjau hasil pada
   **Antrean & Alert** dan agregatnya pada **Dashboard & Laporan**.

## Cara sistem memberi alert

- Zat aktif sama pada lebih dari satu item menghasilkan `DUPLICATE_THERAPY`
  dengan status `REVIEW`.
- Zat aktif berbeda tetapi kelas terapi sama juga menghasilkan review; pesan
  menyatakan kombinasi mungkin disengaja dan perlu penilaian klinis.
- 5–9 zat aktif unik menghasilkan `POLYPHARMACY / INFO`; 10 atau lebih
  menghasilkan `POLYPHARMACY / REVIEW` dengan ambang default.
- High-alert dan LASA hanya muncul bila entri master aktif serta cakupan unit
  cocok. Severity mengikuti konfigurasi yang disetujui.
- Risiko klinis dan kelengkapan asesmen tetap dua dimensi. Temuan keselamatan
  tidak mengubah pasangan DDI yang belum dinilai menjadi aman.

Setiap perubahan master tercatat dalam audit. Sidik konfigurasi ikut masuk ke
identitas skrining, sehingga resep yang sama akan memperoleh revisi baru bila
kebijakan keselamatan berubah.

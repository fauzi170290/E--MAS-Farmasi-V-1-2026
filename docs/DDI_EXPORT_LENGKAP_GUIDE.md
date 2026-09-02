# Export Master DDI Lengkap

## Membuat export

1. Login dengan role `SUPER_ADMIN`, `KNOWLEDGE_ADMIN`, `CLINICAL_REVIEWER`,
   `KFT`, atau `IT_ADMIN`.
2. Buka tab **Import DDI**.
3. Klik **Export Master DDI Lengkap**.
4. Pilih lokasi dan nama file `.xlsx`.
5. Tunggu pesan “Export lengkap selesai”.

Aplikasi juga membuat file `.sha256.txt` di folder yang sama. Simpan kedua file
bersama-sama dan batasi aksesnya sebagai dokumen internal rumah sakit.

## Isi workbook

- `RINGKASAN`: versi, workflow, jumlah rule, HOLD, kontrol kualitas, dan batasan;
- `DDI_IMPORT`: konten yang dapat dipilih kembali pada menu Import DDI;
- `DDI_EXPORT_LENGKAP`: seluruh field rule, sumber, workflow, validasi, dan ID;
- `MASTER_ZAT_AKTIF`: zat aktif yang dipakai versi tersebut;
- `MAPPING_OBAT_KHANZA`: referensi kode/nama obat Khanza dan komponennya;
- `CODEBOOK`: definisi kolom dan nilai yang diperbolehkan.

Workbook tidak memuat pasien, resep, nomor rekam medis, atau password.

## Pemulihan dari Excel

1. Buka tab **Import DDI** dan pilih workbook hasil export.
2. Klik **Validasi dan Preview**.
3. Pastikan seluruh baris valid dan tinjau apakah hasilnya insert/update/unchanged.
4. Klik **Simpan sebagai Draft** hanya setelah backup database dibuat.
5. Lakukan review klinis serta workflow knowledge base kembali.

Sheet `DDI_IMPORT` sengaja menetapkan status `DRAFT`. Excel tidak boleh dipakai
untuk melewati review klinis atau langsung mengaktifkan rule. Untuk kehilangan
database lokal secara keseluruhan, metode utama adalah menu **Backup & Restore**
karena backup SQLite juga mempertahankan audit, pengguna, workflow, dan status
intervensi.

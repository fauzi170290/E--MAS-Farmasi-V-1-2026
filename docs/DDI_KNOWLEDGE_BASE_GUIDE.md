# Panduan Master DDI dan Knowledge Base

## Kondisi awal

Versi `DDI-KHANZA-v1.0.0` telah dimuat sebagai `DRAFT`. Seluruh rule inactive.
Mapping obat juga masih menunggu review. Kondisi ini disengaja agar tidak ada
keputusan klinis yang aktif tanpa persetujuan.

## Review master obat lebih dahulu

1. Login sebagai pengguna berwenang.
2. Buka **Master Obat & Mapping**.
3. Periksa 221 obat dan 240 komponen.
4. Pada tab **Import**, pilih batch master obat yang berstatus `COMMITTED`.
5. Klik **Setujui Mapping Batch** hanya setelah review mapping selesai.

## Meninjau master DDI

1. Buka **Knowledge Base & Master DDI**.
2. Pilih `DDI-KHANZA-v1.0.0`.
3. Gunakan pencarian berdasarkan pasangan, efek klinis, atau sumber.
4. Pilih filter **HOLD belum selesai** agar rule lain tidak bercampur dalam
   antrean review.
5. Klik **HOLD Berikutnya**, lalu **Lihat Detail Klinis**. Telaah efek klinis,
   mekanisme, rekomendasi, monitoring, populasi berisiko, sumber, dan catatan.
6. Setelah yakin, klik **Selesaikan HOLD Terpilih**. Aplikasi menampilkan detail
   yang sama sekali lagi sebelum meminta catatan review klinis wajib.
7. Ulangi sampai indikator `HOLD selesai` mencapai seluruh HOLD dan
   `HOLD belum selesai` menjadi nol.
8. Untuk memperbarui isi rule, gunakan **Input DDI Baru** dan masukkan pasangan
   kanonik yang sama; service akan memperbarui rule draft, bukan membuat
   duplikat.
9. Tandai review klinis selesai hanya setelah efek, rekomendasi, monitoring,
   dan sumber diverifikasi.

## Workflow versi

1. `DRAFT`: dapat diimpor, ditambah, dan diperbarui.
2. `REVIEWED`: keputusan reviewer klinis; tidak dapat dicapai bila masih ada
   HOLD belum selesai.
3. `APPROVED`: persetujuan KFT/role berwenang.
4. `PUBLISHED`: versi berlaku. Hanya rule interaksi positif yang memenuhi
   syarat dapat aktif.
5. `RETIRED`: versi tidak lagi berlaku.

Rollback menuju versi APPROVED atau RETIRED membutuhkan alasan. Versi published
yang sedang berlaku otomatis di-retire.

## Mengimpor data tambahan

1. Buka tab **Import DDI**.
2. Klik **Unduh Template DDI**.
3. Isi sheet `DDI_IMPORT` mulai baris 4.
4. Jangan mengubah header, menggunakan formula, atau memasukkan macro.
5. Gunakan satu `knowledge_base_version` per file.
6. Semua baris harus berstatus `DRAFT`.
7. Klik **Validasi dan Preview**.
8. Perbaiki seluruh baris invalid.
9. Klik **Simpan sebagai Draft**. Sistem membuat backup database sebelum commit.

Template menerima XLSX; CSV UTF-8 dengan header yang sama juga didukung.

## Prinsip klinis

- `ASSESSED_NO_INTERACTION` tidak sama dengan pasangan yang belum dinilai.
- Quick-closure adalah jejak audit sumber, bukan jaminan aman.
- NOT_ASSESSABLE dan EXCLUDED dipertahankan sebagai status tersendiri.
- DDI engine Sprint 4 hanya memakai versi PUBLISHED pada mode normal.
- Simulator MOCK boleh memakai DRAFT pada development/test, tetapi hasilnya
  tidak boleh digunakan untuk keputusan klinis.
- Jangan mempublikasikan versi sebelum validasi klinis dan KFT selesai.

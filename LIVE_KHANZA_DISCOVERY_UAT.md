# UAT Live — Discovery Khanza 1.0.14

## Tujuan

Merekam gate identitas SIMRS Khanza yang benar-benar dipakai pada PC client. Diagnosis ini read-only dan tidak menampilkan judul jendela, data pasien, nomor rekam medis, nomor resep, atau isi command line.

## Persiapan

1. Tutup E-MAS.
2. Pastikan SIMRS Khanza sudah login dan jendela utamanya terlihat.
3. Pasang E-MAS Farmasi 1.0.14 sebagai upgrade. Data lokal E-MAS tetap dipertahankan.
4. Buka E-MAS lalu pilih **Koneksi Khanza**. Jalankan **Periksa Ulang** bila diperlukan.

## Bukti yang dicatat

Buka **Detail Teknis** pada Koneksi Khanza atau Status Operasional. Catat atau salin hanya baris berikut:

- Gate kandidat PID
- Jendela terlihat/JAB
- Command line
- Gate command line bila ada
- khanza.jar
- Root JAB/frame
- Menu bar/desktop pane
- Signature final
- Target Khanza ditemukan
- Bukti deteksi
- JAB attach
- Bridge
- Status identitas
- Status pembacaan resep

## Hasil yang diharapkan

| Skenario | Status yang benar |
|---|---|
| Khanza valid, form resep belum dibuka | KHANZA_CONNECTED dan PRESCRIPTION_VIEW_NOT_FOUND |
| Form resep valid terbuka | KHANZA_CONNECTED dan PRESCRIPTION_READY |
| Java/JAB ada tetapi identitas belum cukup | KHANZA_UNVERIFIED, dengan gate gagal terlihat |
| Tidak ada kandidat Java/JAB | KHANZA_NOT_FOUND |

Jika KHANZA_UNVERIFIED masih terjadi, kirim teks gate di atas. Jangan kirim screenshot yang menampilkan pasien atau resep.
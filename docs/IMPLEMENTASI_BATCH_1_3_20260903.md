# Implementasi Batch 1–3 — 3 September 2026

Baseline: rilis 1.0.3  
Kandidat source: 1.0.4  
Status installer: **DITAHAN — tidak dibangun**

## Batch 1 — koreksi kode SIMRS Master Obat

- Hanya akun bernama `SUPER_ADMIN` yang dapat mengubah kode SIMRS pada master
  yang sudah ada. Otorisasi diperiksa di UI dan service.
- KFT tetap dapat mengelola master/kandungan tetapi tidak dapat mengubah kode.
- Kode yang sama persis atau setara menurut identitas lima digit ditolak agar
  tidak membentuk master ganda. Perbedaan kandungan dilaporkan sebagai konflik.
- Koreksi kode saja mempertahankan baris pemetaan komponen dan tidak menulis
  ulang kode maupun hasil skrining historis.
- Audit menyimpan kode sebelum/sesudah dengan aksi
  `DRUG_SIMRS_CODE_CHANGED`.

Gerbang targeted: **22 tes lulus**.

## Batch 2 — pemisahan simulasi dari pelayanan

- Tombol **Simulasikan Risiko Kritis** dihapus dari panel bersama Antrian Resep
  dan Riwayat Pemeriksaan.
- Mesin/skenario dummy tetap tersedia di menu khusus **Simulasi Resep Dummy**
  pada environment pengembangan atau UAT.
- Mesin DDI, popup operasional, dan aturan audio tidak diubah.

Gerbang targeted: **4 tes lulus**.

## Batch 3 — Antrian Resep pada jendela tidak maksimal

- Filter berubah menjadi tata letak dua baris ketika area kerja menyempit.
- Lebar kolom tabel mengikuti viewport sehingga tidak memaksakan lebar lama
  760 piksel di luar area yang tersedia.
- Tindakan intervensi, tinjau, dan periksa ulang diletakkan sebelum rincian
  panjang serta membentuk dua baris pada tampilan sempit.
- Pengujian geometri dilakukan pada 1024×720, 1280×720, dan 1366×768; seluruh
  filter/tombol berada dalam viewport dan tabel utama tidak memiliki scroll
  horizontal.

Gerbang targeted kumulatif: **69 tes lulus, 1 peringatan dependency**.

## Batas perubahan

- Tidak ada migration/schema baru.
- Tidak ada penghapusan data historis.
- Tidak ada perubahan popup resep, aturan DDI, atau aturan audio.
- Full qualification dijalankan sekali setelah checkpoint ketiga batch final.
- Inno Setup/installer tidak dijalankan sampai ada instruksi setelah revisi
  berikutnya.

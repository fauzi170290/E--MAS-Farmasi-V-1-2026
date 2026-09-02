# Sprint 11 — Monitoring Pilot dan Bukti Alert Fatigue

## Tujuan

Menyediakan bukti agregat untuk menilai beban alert dan respons operasional
selama silent/advisory pilot. Sprint ini tidak mengaktifkan advisory mode dan
tidak menggantikan persetujuan apoteker, KFT, pemilik produk, atau IT.

## Input

- antrean resep riil/non-MOCK pada database lokal e-MSS;
- alert gabungan per resep beserta waktu tampil dan acknowledgement;
- intervensi apoteker serta hasil komunikasi yang terdokumentasi;
- periode pengamatan 7, 30, 90, atau 365 hari.

Tidak ada query tambahan dan tidak ada penulisan ke database Khanza.

## Output

- jumlah resep CRITICAL dan HIGH_RISK;
- alert per 100 resep;
- acknowledgement rate dan median waktu acknowledgement;
- CRITICAL yang belum diakui;
- penyelesaian intervensi dan acceptance rate;
- CSV agregat tanpa identitas pasien atau nomor resep.

## Asumsi dan keputusan

- Resep MOCK dikeluarkan agar indikator tidak tercampur data simulasi.
- Acceptance rate hanya memakai hasil `ACCEPTED_FULL`, `ACCEPTED_PARTIAL`, dan
  `NOT_ACCEPTED`. Outcome belum selesai atau dokter tidak dapat dihubungi tidak
  dipaksa menjadi penolakan.
- Aplikasi tidak menetapkan ambang alert fatigue secara otomatis. Ambang lokal
  harus disepakati apoteker/KFT setelah data pilot tersedia.
- Gate advisory tetap memakai hasil validasi klinis, checklist UAT, dan dua
  sign-off yang sudah diterapkan pada Sprint 10.

## Risiko

- Data sedikit dapat menghasilkan persentase yang menyesatkan.
- Alert yang tidak diakui belum tentu tidak dilihat; disiplin klik dan
  dokumentasi perlu diuji pada pilot.
- Acceptance rate bukan ukuran tunggal mutu klinis dan tidak boleh dipakai
  untuk menilai individu.

## Acceptance criteria

- hanya resep non-MOCK yang dihitung;
- tidak ada identitas pasien atau nomor resep pada ekspor;
- empat pilihan periode bekerja konsisten;
- CRITICAL belum diakui terlihat jelas;
- ekspor memiliki checksum pada audit;
- membuka/mengekspor monitoring tidak mengubah mode aplikasi;
- seluruh automated test lulus dengan branch coverage minimal 85%.

## Langkah pengguna

1. Jalankan e-MSS dalam silent pilot sesuai persetujuan IT.
2. Setelah data terkumpul, login memakai akun bernama.
3. Buka **Validasi Klinis & UAT → Monitoring Pilot**.
4. Pilih periode lalu klik **Muat Ulang Monitoring**.
5. Ekspor CSV agregat untuk rapat evaluasi apoteker/KFT/IT.
6. Catat keputusan ambang lokal alert fatigue di kebijakan rumah sakit.

## Informasi yang masih perlu dikonfirmasi

- target durasi silent pilot;
- jumlah minimum resep untuk evaluasi pertama;
- batas alert per 100 resep yang dapat diterima;
- target acknowledgement rate dan waktu respons;
- jadwal rapat evaluasi serta pihak penandatangan keputusan pilot.

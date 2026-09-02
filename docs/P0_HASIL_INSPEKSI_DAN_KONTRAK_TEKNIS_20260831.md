# P0 — hasil pemeriksaan baseline dan kontrak teknis E-MAS

Tanggal: 31 Agustus 2026  
Baseline diperiksa: sumber E-MAS Farmasi 0.34.1.  
Status: **SELESAI sebagai inspeksi dan keputusan desain.** Tidak ada kode aplikasi, database, schema, konfigurasi operasional, atau installer yang diubah.

Dokumen ini menjadi handoff wajib untuk Batch 1–9 dalam [rencana eksekusi terpadu](REKAP_BATCH_DAN_URUTAN_EKSEKUSI_EMAS_20260831.md).

## Kesimpulan yang dapat langsung dipakai

1. Antrean memang tidak memiliki filter tanggal. Resep lama tampil karena `ProcessingQueueService.list_items()` hanya memfilter scope, unit, status, dan pencarian; urutannya prioritas lalu `detected_at`. Status REVIEWED masih dapat tampil pada filter kosong.
2. Dashboard saat ini memakai periode Bulanan/Triwulanan/Tahunan/Seluruh Data dan UI memilih Tahunan sebagai default. Agregat memakai hasil antrean efektif, bukan baris yang terlihat di tabel antrean.
3. Tidak ada tanggal pelayanan/resep yang tersimpan dalam model E-MAS saat ini. `PrescriptionRevision.source_changed_at` berasal dari `changed_at` sumber Khanza; `ProcessingQueue.detected_at` berasal dari waktu E-MAS menangkap/mengantrikan hasil. Keduanya tidak boleh diberi label “tanggal resep” tanpa verifikasi.
4. Semua waktu aplikasi disimpan dalam UTC. Tampilan antrean mengubahnya ke timezone komputer lokal. Tidak ditemukan konfigurasi timezone RS yang eksplisit. Karena itu host workstation tidak boleh menjadi dasar otoritatif untuk batas hari operasional.
5. Mesin sekarang hanya membandingkan duplikasi kandungan terhadap riwayat 24 jam yang memenuhi kondisi tertentu. DDI lintas resep belum ada.
6. Aktivasi master/pair saat ini berbasis versi knowledge base: penulis adalah SUPER_ADMIN/KNOWLEDGE_ADMIN, KFT adalah approver; publikasi satu versi meretir versi PUBLISHED lain. Ini bertentangan dengan kebutuhan baru “Simpan & Aktifkan” per pair oleh SUPER_ADMIN/KFT, sehingga Batch 6 perlu perubahan layanan bersama yang eksplisit.
7. Dashboard saat ini menghitung pasangan interaksi unik dengan `pair_key` di seluruh periode. Metrik itu adalah jumlah jenis pasangan, bukan jumlah kejadian per resep; tidak cukup untuk laporan DDI lintas resep.

## Kontrak waktu dan tanggal

### T0 — penyimpanan waktu

- Semua timestamp internal disimpan dalam UTC, dengan offset timezone.
- Semua batas periode klinis dihitung pada service/backend menggunakan timezone RS eksplisit berbentuk IANA, lalu diterjemahkan ke interval UTC setengah-terbuka: `[00:00 hari, 00:00 hari berikutnya)`.
- Jangan menggunakan timezone komputer pengguna sebagai aturan bisnis. Ia hanya boleh dipakai sebagai pilihan tampilan bila diberi label.
- Nilai timezone RS belum ada pada sumber yang diperiksa. Penambahan konfigurasi global ini adalah perubahan sistem; rancang dan uji secara terpisah di Wave 3 bila diperlukan, jangan diselipkan pada patch UI.

### T1 — dua waktu yang berbeda

| Nama kontrak | Makna | Sumber saat ini | Boleh dipakai untuk |
|---|---|---|---|
| `service_date` | Tanggal pelayanan/resep yang terverifikasi | **Belum tersedia** | Antrean “Hari Ini” yang diminta pengguna dan dashboard resep pelayanan |
| `screened_at` | Waktu E-MAS menangkap/menyelesaikan skrining | `ProcessingQueue.detected_at`, `completed_at` | Aktivitas sistem, monitoring, troubleshooting |
| `source_changed_at` | Waktu perubahan rekaman sumber | `PrescriptionRevision.source_changed_at` dari `changed_at` | Jejak sumber dan kandidat sementara; bukan otomatis tanggal pelayanan |

Keputusan: istilah **“Hari Ini” untuk resep pelayanan tidak boleh diimplementasikan secara klinis** sebelum adapter sumber menyediakan tanggal pelayanan/resep yang maknanya disetujui dan E-MAS menyimpannya sebagai `service_date`. Jika diperlukan tampilan sementara, label harus jujur: **“Skrining masuk E-MAS hari ini”**. Tampilan sementara tersebut tidak memenuhi kebutuhan pengguna mengenai antrean resep pelayanan harian dan tidak boleh menggantikannya tanpa persetujuan.

### T2 — prerequisite data

Sebelum Batch 3/4 masuk patch query:

1. Pemilik integrasi Khanza memetakan kolom/view sumber untuk tanggal pelayanan/resep, timezone sumber, dan makna perubahan/revisi. Jangan menebak dari nomor resep atau `no_rawat`.
2. Tentukan apakah sumber tersedia pada header resep yang sudah dibaca; jika belum, perluas adapter.
3. Tambahkan penyimpanan `service_date` yang nullable beserta provenance/basis tanggal bila hasil inspeksi mengonfirmasi tidak ada kolom ekuivalen yang sudah tersimpan.
4. Susun migration dan indeks yang spesifik hanya setelah keputusan ini. Perubahan schema membutuhkan review/otorisasi implementasi tersendiri; P0 tidak menjalankannya.

## Kontrak identitas, revisi, dan scope

- Identitas pasien untuk korelasi adalah `Prescription.patient_id` dari `no_rm`, bukan nama pasien.
- Identitas resep memakai ID internal dan nomor resep sumber lengkap. Contoh suffix 001/002/003 tidak boleh menjadi logika urutan atau identitas.
- Revisi memakai `PrescriptionRevision.revision_number` yang unik per resep. Hasil skrining memiliki satu screening per revisi.
- `source_no_resep` saat ini unik secara global pada tabel Prescription. Validasi adapter perlu menegaskan bahwa ini aman lintas scope; jangan menggabungkan resep karena nama atau nomor parsial.
- RALAN/RANAP tetap dipertahankan sebagai scope penyajian dan notifikasi. Untuk Batch 7, keputusan eksplisit diperlukan apakah riwayat antar-care-setting menjadi kandidat klinis, serta provenance care setting mana yang disimpan untuk tiap pembanding. Jangan menyampaikan alert ke workstation yang salah.
- Resep batal/berhenti dan terapi yang statusnya tidak pasti belum memiliki kontrak khusus yang cukup pada hasil pemeriksaan ini. Batch 7 wajib membawa status dan alasan pengecualian/ketidakpastian; tidak boleh menganggapnya “aman”.

## Kontrak hasil efektif dan metrik

### E0 — hasil efektif

Definisi yang disetujui untuk implementasi:

- Untuk satu resep, pilih revisi efektif terbaru **sebelum** menerapkan filter periode.
- Filter dashboard resep pelayanan diterapkan menggunakan `service_date`, bukan `detected_at`.
- Pemeriksaan ulang esok hari tidak memindahkan resep pelayanan kemarin ke hari ini dan tidak menghapus riwayat kemarin.
- Hasil/revisi lama tetap immutable dan dapat ditelusuri; agregat tidak menjumlah setiap retry/revisi.

Implementasi sekarang melakukan ranking revisi lalu memfilter `detected_at`. Karena itu resep yang diperiksa ulang dapat bergeser periode. Batch 4 mengganti urutan tersebut setelah T2 terpenuhi.

### E1 — ukuran yang dipakai dashboard/ekspor

| Metrik | Definisi kontrak |
|---|---|
| Resep pelayanan | Jumlah resep efektif unik menurut `service_date` periode terpilih |
| Aktivitas skrining | Jumlah penyelesaian skrining menurut `screened_at`; selalu diberi label terpisah |
| Kasus DDI | Temuan interaksi unik untuk resep pemicu/revisi efektif pada periode |
| Jenis pasangan DDI | `pair_key` unik; indikator referensi, bukan jumlah kasus |
| Duplikasi terapi | Issue duplikasi; tetap kategori sendiri |
| Belum dinilai/pemetaan | Status kelengkapan yang berbeda dari tidak adanya interaksi |

Untuk temuan lintas resep, kunci kejadian yang direncanakan adalah:
`trigger_revision_id + counterpart_effective_revision_id + canonical_pair_key + finding_type`.

Dashboard mengatribusikan kejadian ke resep pemicu yang lebih baru. Jika detail kedua resep menampilkan kejadian yang sama, dashboard dan ekspor tetap menghitungnya sekali. Pasangan sama pada pasien atau episode lain tetap kejadian berbeda.

## Kontrak screening lintas resep

- DDI internal resep dipertahankan.
- Untuk pasien sama: resep 002 diperiksa terhadap 001; resep 003 diperiksa terhadap 001 dan 002, selain pemeriksaan internal serta duplikasi.
- Kandidat terapi historis tidak sama dengan terapi aktif yang pasti. Status penggunaan yang tidak lengkap harus tampil sebagai konteks potensial/perlu rekonsiliasi atau tidak dapat dinilai, sesuai bukti sumber.
- Tidak ada query Khanza tambahan pada presenter popup. Mesin screening yang menghitung konteks, lalu presenter hanya menyajikan hasil persistennya.
- Event terlambat, retry, restart, dan dua event berdekatan memakai kunci kejadian/pemeriksaan yang stabil. Tidak memindai seluruh riwayat setiap detik.
- Temuan/konteks baru membutuhkan tinjauan baru; status review lama tidak disalin otomatis dan tidak membuat intervensi fiktif.
- Pasangan tanpa rule/mapping tidak boleh ditampilkan sebagai SAFE.

## Kontrak master obat dan aktivasi pair

| Ketentuan | Keputusan P0 |
|---|---|
| Aktor | SUPER_ADMIN dan KFT saja untuk alur baru; APOTEKER/CLINICAL_REVIEWER tidak mendapat hak otomatis. Verifikasi wajib di service, bukan hanya menyembunyikan tombol. |
| Identitas obat baru | Tidak mengarang kode Khanza. Bila diperlukan entitas lokal, perlu skema identitas lokal yang jelas, asal data, dan pemisahan dari kode Khanza. |
| Pemetaan | Obat kombinasi menyimpan dan menampilkan kandungan yang benar-benar dipilih; tidak menyebarkan satu severity ke semua kombinasi. |
| Pair | A–B dan B–A adalah satu pair kanonis. Konflik membuka edit, tidak overwrite diam-diam. |
| Aktivasi | Satu transaksi: validasi → data/mapping → rule aktif → audit. UI menunjukkan Aktif hanya sesudah transaksi sukses dan engine dapat membacanya. |
| Dampak pair lain | Aktivasi A–B tidak mengaktifkan draft C–D, tidak mengubah hasil lama, dan tidak meretir aturan aktif yang tidak terkait. |
| Kegagalan | Tidak ada status aktif palsu atau data setengah tersimpan; konflik dua editor harus jelas. |

Kondisi teknologi saat ini menjelaskan mengapa Batch 6 berat: `save_manual_rule` hanya menerima versi DRAFT, membuat `activation_status=DRAFT` dan `is_enabled=False`; `publish_version` meretir versi PUBLISHED lain; screening mengharuskan rule `is_enabled`, `record_status=PUBLISHED`, serta `activation_status=ACTIVE`. Desain Batch 6 harus menyediakan pembacaan aturan aktif yang konsisten per skrining tanpa mempublikasikan seluruh draft atau menghilangkan rules lama.

Perubahan ini memenuhi high-effort gate untuk subarea shared knowledge/authorization/atomicity. Rekomendasi awal tetap Sol–Medium dengan review terarah; High hanya dipakai pada subarea tersebut bila rancangan/percobaan Medium menunjukkan kebutuhan nyata.

## Kepemilikan file dan urutan edit

| File/area | Batch | Aturan serial |
|---|---|---|
| `ui/intervention/panel.py`, stylesheet aplikasi | 1, 2, 8 | Kontras lokal dulu; jangan campur dengan validasi atau perubahan engine. |
| `services/queue.py`, `ui/queue/panel.py` | 3, 7, 8 | Filter tampilan selesai dulu; sumber konteks terapi tidak pernah berasal dari daftar tampak. |
| `services/dashboard.py`, `ui/dashboard/panel.py` | 4, 8 | Kontrak tanggal dan metrik dahulu; lintas resep kemudian. |
| `services/knowledge.py`, katalog/mapping, role/audit | 5, 6 | Form mengikuti layanan; tidak membuat bypass sementara. |
| `services/screening.py`, model hasil | 6, 7, 8 | Perubahan aturan/versi selesai sebelum konteks lintas resep. |
| `ui/application.py` | 2, 4, 5/6, 8 | Tema → refresh → menu/binding secara serial. |

## Bukti baseline yang diperiksa

- Versi proyek: 0.34.1.
- Laporan rilis terdahulu mencatat 380 tes lulus dan coverage cabang sekitar 88,01%. Itu baseline historis, bukan uji ulang atau bukti fitur baru.
- Tidak ada repositori Git pada folder sumber yang diperiksa. Gunakan manifest/hash dan snapshot sumber per checkpoint bila Git tetap tidak tersedia.
- Hash SHA-256 file shared pada saat P0:

| File | SHA-256 |
|---|---|
| `services/queue.py` | `FD2B78F0DB05F4672B1B78B6E4695B3D8AEBE5DA8F3D1276B33A47A29A2CDE64` |
| `services/dashboard.py` | `33A02C58EE297356812547A614C827A902AF2A1B80BE0DAE99A24F37AAE23F72` |
| `services/screening.py` | `9C7B555552C3E823E5CA34D90219590DC7AF66F1195588FD5527B820E297E501` |
| `services/knowledge.py` | `0E96EDB2B1600EC2A4F08A368A2EABBCDFC81EA15CDF8E45A251ADE38AAF1B32` |

## Status batch setelah P0

- Batch 1 dan 2 dapat dimulai tanpa dependency P0 yang belum selesai.
- Batch 3 dan 4 memiliki **gate T2** untuk klaim “resep pelayanan Hari Ini”. Perbaikan UI filter/riwayat dapat dirancang, tetapi tidak boleh memakai label klinis yang salah.
- Batch 5 dapat membuat form dan validasi lokal; data tulis/aktivasi penuh mengikuti Batch 6.
- Batch 6 dan 7 tetap berurutan. Batch 7 tidak dimulai sebelum kontrak aturan aktif Batch 6 lulus uji.
- Batch 8 menghitung ulang metrik dengan fixture yang mencakup internal DDI, DDI lintas resep, duplikasi, revisi, dan history.

Tidak ada tindakan yang perlu dilakukan pada database operasional untuk menyelesaikan P0.


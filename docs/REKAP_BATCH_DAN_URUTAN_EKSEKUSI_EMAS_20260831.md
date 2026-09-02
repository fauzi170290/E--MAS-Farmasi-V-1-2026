# Rekap batch dan urutan eksekusi E-MAS Farmasi

Tanggal: 31 Agustus 2026  
Baseline: 0.34.1  
Status: RENCANA TERPADU dengan pembaruan implementasi. Batch 6–7 selesai pada kode sumber; 411 tes regresi lulus, coverage gabungan 88,08%. Database operasional, schema, konfigurasi instalasi, dan installer tidak diubah oleh Batch 6–7. Rincian/batas hasil ada di IMPLEMENTASI_BATCH_6_7_20260831.md.

Dokumen ini menyatukan empat backlog terbaru. Penyederhanaan master/pair mengikuti revisi 2: SUPER_ADMIN dan KFT memakai **Simpan & Aktifkan**; rangkaian persetujuan/publikasi manual berulang bukan lagi alur rutin yang direncanakan. Tidak semua fitur di bawah sudah tersedia di versi 0.34.1.

## Rekomendasi utama

Mulai dengan pemeriksaan baseline dan kesepakatan teknis singkat (P0), kemudian **Batch 1: kontras form Intervensi Apoteker**. Selesaikan UI lokal, antrean harian, dan dashboard harian sebelum mengubah aktivasi master dan mesin DDI lintas resep.

Urutan kerja: **P0 → 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9**.

Ini satu rangkaian perubahan kumulatif pada proyek yang sama, dengan patch kecil dan titik pemulihan. Bukan sembilan aplikasi atau sembilan instalasi terpisah. Semua fitur digabung dan diuji sebelum membuat paket final. Tidak ada model atau urutan kerja yang menjamin nol crash; kelayakan rilis harus didukung bukti pengujian.

## Ringkasan model, effort, dan dependensi

| Batch | Wave / klasifikasi | Issues | Risk | Model | Effort | Alasan / dependency |
|---|---|---|---|---|---|---|
| P0 | Persiapan; MEDIUM | Baseline, batas tanggal, identitas, definisi metrik dan kontrak antarfitur | Sedang bila kontrak salah; inspeksi tanpa mutasi | GPT-5.6 Terra | Medium | Menyamakan asumsi sebelum UI, query dan engine dibangun. |
| 1 | Wave 1; LIGHT | Warna latar, label dan checkbox form Intervensi Apoteker | Rendah | GPT-5.6 Luna | Low | Cacat keterbacaan lokal; tidak mengubah validasi/keputusan klinis. |
| 2 | Wave 1; LIGHT | Pilot UI modern desktop, warna, spacing, kartu, ikon dan konsistensi visual | Rendah jika dibatasi lokal | GPT-5.6 Luna | Low | Memakai komponen yang ada; tidak mengganti framework atau mengubah handler. |
| 3 | Wave 2; MEDIUM | Antrean default Hari Ini, Riwayat, indikator tindak lanjut lama | Sedang | GPT-5.6 Terra | Medium | Filter dan state harus konsisten dengan tanggal, scope dan ringkasan. Setelah P0 dan pilot UI. |
| 4 | Wave 2; MEDIUM | Dashboard default harian, periode/ekspor konsisten, refresh dan status usang | Sedang | GPT-5.6 Terra | Medium | Memakai kontrak tanggal yang sama dengan Batch 3; agregasi tetap dari hasil tersimpan. |
| 5 | Wave 2; MEDIUM | Form Master Obat dan Pasangan Interaksi Obat, pencarian A/B, kandungan, severity, referensi, validasi | Sedang | GPT-5.6 Terra | Medium | Kerjakan bagian lokal yang independen. Penyimpanan/aktivasi baru menunggu layanan Batch 6. |
| 6 | Wave 3; HEAVY | Identitas obat baru, mapping, hak SUPER_ADMIN/KFT, Simpan & Aktifkan per entri, audit, versi dan konflik edit | Tinggi | GPT-5.6 Sol | Medium | Menyentuh layanan referensi bersama dan otorisasi; harus konsisten sampai engine. |
| 7 | Wave 3; HEAVY | Skrining DDI antar resep pasien yang sama, konteks terapi, revisi, event terlambat/bersamaan dan deduplikasi | Tinggi | GPT-5.6 Sol | Medium | Menggunakan aturan aktif dari Batch 6 dan riwayat yang tidak dibatasi filter tampilan harian. |
| 8 | Integrasi sesudah Wave 3; MEDIUM | Penyambungan form/hasil, state UI, pelaporan DDI lintas resep, konsistensi antrean–dashboard–ekspor | Sedang | GPT-5.6 Terra | Medium | Mengintegrasikan kontrak yang sudah diuji; masalah shared core dikembalikan ke Batch 6/7. |
| 9 | Kualifikasi rilis; MEDIUM | Regresi kumulatif, UAT terpadu, performa, frozen GUI, panduan dan installer | Sedang | GPT-5.6 Terra | Medium | Memverifikasi satu paket final. Temuan berat ditangani pada batch asal, bukan menaikkan seluruh pengujian menjadi High. |

Pemilihan keluarga model dan effort mengikuti karakter tugas: Luna untuk pekerjaan ringan, Terra untuk pekerjaan lokal/integrasi, Sol untuk reasoning sistem bersama. Medium menjadi titik awal yang seimbang; High digunakan jika bukti dan kebutuhan kualitas membenarkannya. [Panduan resmi model OpenAI](https://developers.openai.com/api/docs/guides/latest-model)

Rekomendasi ini tidak otomatis mengganti model sesi, memulai subagent, atau menjalankan implementasi.

## P0 — keputusan teknis sebelum patch

**Issues:** pastikan kode sumber dan hasil uji 0.34.1 yang dipakai, catat perubahan lokal lain, petakan pemilik file, dan tetapkan kontrak berikut.  
**Risk:** sedang untuk dampak keputusan; kegiatan ini hanya inspeksi/dokumentasi.  
**Model:** GPT-5.6 Terra. **Effort:** Medium.  
**Alasan:** mencegah setiap batch membuat definisi sendiri.

1. **Tanggal pelayanan:** periksa field tanggal resep sebenarnya dan zona waktu RS. Jangan menganggap waktu perubahan sumber atau waktu ditangkap E-MAS sebagai tanggal resep. Jangan menebak tanggal dari akhiran nomor resep. Tetapkan fallback berlabel bila sumber tidak memadai; jangan menjanjikan filter pelayanan akurat sebelum sumbernya terverifikasi.
2. **Identitas dan revisi:** gunakan identitas pasien stabil, ID resep lengkap, ID revisi dan waktu sumber yang maknanya diketahui. Nomor 001/002/003 hanya contoh tampilan; nama pasien dan suffix bukan kunci pencocokan.
3. **Metrik:** bedakan resep pelayanan hari terpilih, aktivitas skrining hari terpilih, jumlah resep dengan DDI, jumlah temuan, dan jumlah pasangan unik. Tetapkan hasil efektif serta cara mencegah retry/revisi dihitung berulang.
4. **Temuan lintas resep:** rancangan awal mengatribusikan temuan baru ke resep pemicu dengan referensi kedua resep. Temuan sama yang ditampilkan pada dua detail tidak otomatis dihitung dua kali. Kasus pasangan sama pada pasien lain tetap kasus terpisah. Finalisasi aturan event terlambat, revisi dan periode sebelum Batch 7–8.
5. **Konteks terapi:** definisikan kandidat riwayat, status batal/berhenti, jendela waktu/episode dan penanganan informasi penggunaan yang belum pasti. Jendela duplikasi lama tidak otomatis membuktikan seluruh obat masih digunakan. Filter Hari Ini adalah filter tampilan, bukan batas mesin DDI.
6. **Aktivasi:** definisikan identitas obat lokal jika belum punya kode Khanza, hak peran, status Aktif/Draft/Nonaktif, satu pembacaan aturan yang konsisten per skrining, audit, dan pelestarian hasil lama. Jangan membuat kode palsu yang seolah berasal dari Khanza.
7. **Batas scope:** tidak mengubah akses dashboard atau routing RALAN/RANAP tanpa kebutuhan khusus; tidak otomatis memberi semua peran apoteker hak pengelolaan master.

Jika inspeksi menunjukkan kebutuhan migration atau perubahan core tanggal, pisahkan sebagai pekerjaan Wave 3 dengan analisis risiko dan rancangan konkret. Tunda bagian Batch 3/4 yang bergantung padanya; jangan menyelipkan migration ke patch filter lokal. Persetujuan perubahan schema tidak dianggap sudah diberikan oleh permintaan rekap ini.

## Wave 1 — perubahan UI aman

### Batch 1 — perbaikan kontras intervensi

**Issues:** latar form gelap, label/checkbox sulit dibaca, konsistensi input dan fokus.  
**Risk:** rendah. **Model:** GPT-5.6 Luna. **Effort:** Low.  
**Alasan:** perubahan visual lokal dapat diperiksa tanpa mengubah data.

- Tetapkan latar/warna form secara lokal dengan kontras jelas; periksa pewarisan palette/stylesheet sebelum memilih perbaikannya.
- Warna risiko kritis/mayor tetap tegas. Jangan mengubah kewajiban isian, tombol simpan, atau pencatatan intervensi.
- Lulus jika terbaca pada Windows terang/gelap dan DPI 100/125/150%, termasuk label, placeholder, checkbox, fokus dan kondisi nonaktif.

### Batch 2 — pilot UI modern desktop

**Issues:** tampilan modern berdasarkan referensi, dimulai pada intervensi dan antrean.  
**Risk:** rendah selama visual lokal. **Model:** GPT-5.6 Luna. **Effort:** Low.  
**Alasan:** referensi mengarah ke soft UI bernuansa pastel dengan sedikit glassmorphism; cocok sebagai inspirasi warna/kartu, bukan menyalin kepadatan UI ponsel.

- Gunakan panel solid terang, teks gelap, aksen teal/biru, radius dan bayangan ringan. Hindari blur/transparansi di belakang nama obat, data pasien dan risiko.
- Pertahankan tabel desktop yang cukup padat, navigasi keyboard, keterbacaan 1280×1024, serta prioritas risiko.
- Tetapkan komponen/warna yang bisa dipakai ulang. Rollout visual dibagi per layar, bukan satu patch stylesheet global tanpa pemeriksaan.
- Bila ada perbaikan resize/state/handler, klasifikasikan MEDIUM dan kerjakan pada batch fungsional/integrasi yang terkait.
- Jangan menampilkan tombol Hari Ini atau Simpan & Aktifkan yang belum bekerja. Menu/form dengan dependency layanan langsung boleh diselesaikan bersama integrasi terkait, bukan dipaksakan ke Wave 1.

## Wave 2 — fungsi lokal

### Batch 3 — antrean harian dan riwayat

**Issues:** default Hari Ini, tanggal jelas, Riwayat/Tanggal tertentu/Seluruh Data, indikator pekerjaan lama belum ditinjau.  
**Risk:** sedang. **Model:** GPT-5.6 Terra. **Effort:** Medium.  
**Alasan:** menyentuh query, ringkasan, state filter, pemilihan resep dan pergantian hari.

- Resep lama keluar dari tampilan utama, tetap tersimpan beserta hasil dan auditnya.
- Hari berganti tidak membuat REVIEWED/intervensi/acknowledgement otomatis.
- Angka ringkasan memakai periode dan scope yang konsisten; pilihan tanggal manual tidak direset polling.
- Riwayat lama tetap dapat dibuka, termasuk indikator tindak lanjut yang belum selesai.
- Uji kemarin/hari ini, revisi/retry, layanan RALAN/RANAP, perubahan urutan baris, dan pergantian tengah malam.

### Batch 4 — Dashboard Kajian pDDI harian

**Issues:** default Hari Ini, periode lain tetap tersedia, refresh benar dan status pembaruan terlihat.  
**Risk:** sedang. **Model:** GPT-5.6 Terra. **Effort:** Medium.  
**Alasan:** antrean dan dashboard memakai sumber tampilan berbeda; memperbaiki filter antrean saja tidak mengubah agregasi dashboard.

- Diagnosis kode: antrean belum memfilter tanggal; dashboard default YEAR. Resep lama bukan semata karena belum diklik ditinjau.
- Kartu, severity, unit, pembanding dan ekspor mengikuti periode yang sama.
- Refresh saat hasil/revisi/intervensi relevan berubah, halaman dibuka kembali dan hari berganti. Gabungkan event berdekatan; jangan query agregasi penuh setiap polling satu detik.
- Jalur refresh sudah ada pada kode. Reproduksi keluhan sebelum menganggap seluruh mekanismenya rusak.
- Gagal refresh harus terlihat sebagai data usang/gagal, bukan angka nol palsu.
- Uji hitungan terhadap fixture hasil tersimpan dan ekspor. Simpan fixture ini untuk diuji ulang setelah DDI lintas resep ditambahkan.

### Batch 5 — form master dan pasangan yang sederhana

**Issues:** dua menu utama, tambah/edit obat, pencarian Obat A vs Obat B, kandungan, severity/status, sumber/referensi, validasi dan pesan kesalahan.  
**Risk:** sedang. **Model:** GPT-5.6 Terra. **Effort:** Medium.  
**Alasan:** pemilih, state dan validasi lokal dapat dipisahkan dari mekanisme aktivasi bersama.

- Menu: **Master Obat** dan **Pasangan Interaksi Obat**; pemetaan kandungan menjadi bagian form obat.
- Setelah obat dibuat, tindakan Tambahkan Pasangan DDI memilih obat tersebut sebagai A.
- A–B sama dengan B–A; pasangan yang ada diarahkan ke edit. Obat kombinasi harus memperlihatkan pasangan kandungan yang dinilai.
- Pisahkan status klinis/severity dari status pengelolaan Aktif/Draft/Nonaktif. Referensi wajib dapat ditelusuri.
- Gunakan layanan pencarian/validasi yang tersedia; jangan membuat backend sementara atau bypass peran agar form terlihat selesai.
- Penyimpanan obat baru, hak KFT dan Simpan & Aktifkan bergantung langsung pada Batch 6. Binding tersebut selesai bersama Batch 6/8 dan diuji sebagai satu alur sebelum dirilis.
- Alur lama yang masih bekerja tidak dihapus sebelum penggantinya lulus.

## Wave 3 — perubahan data dan sistem

### Batch 6 — aktivasi master/pair langsung dan berwenang

**Issues:** layanan tambah/edit/nonaktif obat dan mapping, izin SUPER_ADMIN/KFT, aktivasi per entri, audit, konsistensi versi/rules dan konflik edit.  
**Risk:** tinggi. **Model:** GPT-5.6 Sol. **Effort:** Medium sebagai awal.  
**Alasan:** perubahan melintasi knowledge, katalog/pemetaan, otorisasi dan pembacaan aturan oleh screening.

- **Simpan & Aktifkan** membuat entri benar-benar tersedia untuk pemeriksaan berikutnya, tanpa restart/publikasi manual seluruh versi.
- Transaksi penyimpanan, aktivasi dan audit harus konsisten; UI tidak mengumumkan Aktif sebelum backend berhasil.
- Mengaktifkan A–B tidak mengaktifkan draft C–D, tidak mempublikasikan semua draft lama, tidak menghilangkan aturan lama yang masih aktif.
- Akun bernama dan hak server/service wajib; Mode Farmasi anonim tidak menjadi penulis. Catat aktor sebenarnya, bukan persetujuan petugas lain yang dibuat otomatis.
- Hasil/audit lama tidak ditulis ulang diam-diam; nonaktif bukan hapus sejarah.
- Uji peran di service dan UI, validasi gagal, kegagalan transaksi, konflik dua editor, cache/versi, restart, serta penggunaan aturan baru oleh engine.
- Review terarah bagian otorisasi dan transaksi diperlukan. Naikkan hanya batch ini ke High jika hasil inspeksi/review menunjukkan kebutuhan reasoning, risiko atau ketidakpastian yang tidak tertangani dengan Medium.

### Batch 7 — DDI lintas resep

**Issues:** kandidat riwayat pasien, pemeriksaan lintas resep, provenance, revisi dan deduplikasi event.  
**Risk:** tinggi. **Model:** GPT-5.6 Sol. **Effort:** Medium sebagai awal.  
**Alasan:** mesin screening memakai konteks beberapa resep dan harus tetap konsisten saat ada perubahan/kejadian bersamaan.

- 09.00 resep 001: skrining internal.
- 09.45 resep 002: skrining internal + 002 terhadap 001, selain duplikasi.
- Resep 003 berikutnya: skrining internal + 003 terhadap 001 dan 002. Hasil 001–002 tetap dapat ditelusuri tanpa notifikasi identik berulang yang tidak perlu.
- Berlaku untuk pasien sama meski dokter/poli berbeda; jangan menyamakan pasien hanya dari nama.
- Riwayat adalah kandidat konteks. Informasi terapi lama yang belum pasti harus dijelaskan sebagai potensi/perlu rekonsiliasi, bukan diam-diam diabaikan.
- Simpan keterkaitan kedua resep, revisi, obat/kandungan, waktu, dokter/poli bila tersedia, severity dan kelengkapan penilaian.
- Bedakan DDI internal, DDI lintas resep, duplikasi dan masalah pemetaan. Pasangan tidak diketahui tidak menjadi SAFE.
- Temuan/konteks baru membutuhkan tinjauan baru; jangan membawa status ditinjau lama secara menyeluruh.
- Uji kejadian terlambat/bersamaan, urutan terbalik, revisi/batal, retry, restart, isolasi pasien/layanan, FINAL pada siklus pertama dan tidak membaca ulang semua resep tiap detik.
- Batch 6 dan 7 tidak dikerjakan bersamaan pada screening/aturan versi yang sama. Kenaikan High hanya untuk bagian core yang memenuhi gate setelah inspeksi, bukan UI lain.

## Integrasi dan kualifikasi

### Batch 8 — penyatuan seluruh fitur

**Issues:** binding final, rincian/popup, state/fokus/resize, angka dashboard dan ekspor setelah lintas resep.  
**Risk:** sedang. **Model:** GPT-5.6 Terra. **Effort:** Medium.  
**Alasan:** antarmuka dan metrik harus mencerminkan kontrak layanan yang sudah selesai.

- Form baru bekerja penuh sampai aktivasi dan skrining; menu lama yang tidak diperlukan disederhanakan setelah alur baru terbukti.
- Filter harian tidak menghilangkan sumber konteks lintas resep.
- Satu temuan yang tampil pada dua resep tidak menghasilkan hitungan ganda; jumlah resep dengan DDI dibedakan dari jumlah temuan.
- Semua daftar/ringkasan/ekspor memperlihatkan periode dan basis metrik secara konsisten.
- Pastikan gaya UI tetap mengikuti pilot, tanpa redesign global tambahan.
- Perubahan atomicity, schema, izin atau concurrency yang ditemukan di sini kembali ke Batch 6/7; jangan memasukkannya diam-diam sebagai perbaikan UI Medium.

### Batch 9 — regresi dan paket final

**Issues:** bukti uji kumulatif, skenario UAT, performa, GUI binary, dokumen dan installer.  
**Risk:** sedang. **Model:** GPT-5.6 Terra. **Effort:** Medium.  
**Alasan:** rilis harus berasal dari gabungan sumber yang sama dengan yang diuji.

- Jalankan uji terarah per batch, regresi kumulatif di akhir wave, dan seluruh suite pada sumber final. Tidak perlu membuat tes yang hanya meniru nilai warna/spacing.
- Ukur waktu pemrosesan/popup dan beban query dengan fixture yang sebanding. Jangan mengklaim hasil sintetis sebagai benchmark server operasional.
- Gunakan database uji terpisah dan data sintetis; jangan menjadikan pasien/DB operasional sebagai tempat eksperimen.
- Uji frozen Windows GUI dan installer, sumber daya audio, dua panduan PDF, kompatibilitas konfigurasi/jalur data, serta catat hash dan status tanda tangan paket.
- Tidak ada upgrade operasional otomatis. Bila perlu migration, siapkan rancangan, backup/restore terverifikasi dan persetujuan sesuai scope sebelum penerapan.
- Riwayat bukti 0.34.1: 380 tes lulus, coverage cabang sekitar 88,01%, schema 0028_pharmacy_scope, paket NotSigned. Itu baseline terdahulu, bukan bukti bahwa fitur baru sudah lulus.
- Jangan menyatakan suara sudah terdengar atau UAT klinis disetujui bila belum benar-benar diverifikasi pengguna/petugas terkait.

## File bersama: urutan agar patch tidak bertumpuk

| Area | Batch yang menyentuh | Aturan |
|---|---|---|
| ui/application.py | 2, 4, 5/6, 8 | Serial: theme → refresh → navigasi/binding; periksa diff dari checkpoint terakhir. |
| ui/intervention/panel.py | 1, 2, 8 | Kontras lokal dahulu; jangan mengubah validasi pada patch warna. |
| services/queue.py; ui/queue/panel.py | 2/3, 7/8 | Filter tampilan dipisahkan dari pengambilan konteks terapi; pilihan berdasarkan ID dipertahankan. |
| services/dashboard.py; ui/dashboard/panel.py | 4, 8 | Metrik harian ditetapkan dahulu, lalu perluasan kategori lintas resep diuji tanpa double count. |
| services/knowledge.py; services/catalog.py; layanan mapping | 5/6 | Form memakai kontrak layanan; otorisasi/aktivasi/history dituntaskan pada Batch 6. |
| services/screening.py dan model hasil | 6, 7, 8 sebagai consumer | Aturan aktif/versi selesai dahulu, baru konteks lintas resep; jangan dua patch core berjalan bersamaan. |

Satu batch memiliki daftar file, tujuan, hal yang tidak boleh berubah, tes, dan checkpoint sumber. Jika Git tersedia gunakan commit kecil; jika tidak, gunakan snapshot sumber dan manifest/hash. Jangan menimpa perubahan yang tidak terkait.

Saat berganti model, serahkan ringkasan kontrak, checkpoint terakhir, file yang berubah, hasil tes dan pekerjaan tersisa. Model berikutnya harus membaca diff terakhir; tidak memulai dari salinan sumber lama.

## Titik pemeriksaan kumulatif

1. **Setelah Batch 4:** kontras/pilot UI + antrean harian + dashboard harian. Validasi bahwa data kemarin tetap di Riwayat dan kajian historis. Jangan ikut merilis form baru yang belum berfungsi.
2. **Setelah Batch 6 dan binding terkait:** tambah obat → pasangan → Simpan & Aktifkan → aturan terbaca pada skrining berikutnya. Draft lain dan hak peran tetap aman.
3. **Setelah Batch 7–8:** tiga resep berurutan menghasilkan skrining internal dan lintas resep yang benar, tampilan/angka/ekspor sinkron.
4. **Batch 9:** satu paket final dari checkpoint gabungan yang lolos. Titik pemeriksaan bukan kewajiban membuat banyak installer atau banyak cabang aplikasi.

Batch berikutnya tidak boleh menumpuk di atas kegagalan yang memengaruhi dependensinya. Kegagalan dikembalikan ke batch asal, diperbaiki dan diuji ulang bersama area terdampak.

## Skenario UAT terpadu wajib

- Pasien sintetis yang sama: 001 pukul 09.00, 002 pukul 09.45, 003 kemudian, dokter/poli berbeda. Gunakan pasangan uji yang interaksinya hanya muncul antar resep agar tes tidak lulus semata karena DDI internal.
- Pasien berbeda bernama sama tidak digabung; revisi bukan resep baru; resep batal/terapi tidak pasti ditangani menurut kontrak, dengan asal data terlihat.
- Hanya SUPER_ADMIN/KFT yang diizinkan melakukan aktivasi baru. A–B aktif dan dipakai screening; C–D draft tetap draft. Kegagalan simpan tidak memberi status Aktif palsu.
- Kemarin → hari ini → tengah malam, refresh, restart, retry dan event terlambat: tidak kehilangan hasil, tidak memindahkan tanggal resep hanya karena pemeriksaan ulang, tidak membuat tinjauan/intervensi fiktif.
- Antrean Hari Ini bersih dari baris hari lama; indikator tindak lanjut lama tetap ada. Semua DDI lama dapat dikaji pada periode historis.
- Cocokkan rincian hasil, jumlah kasus/temuan dashboard, dan ekspor untuk periode yang sama; pisahkan kategori internal/lintas resep serta belum dinilai.
- Routing RALAN/RANAP, pemilihan baris, popup prioritas, autentikasi tindakan dan pembatasan UAT/diagnostik yang sudah diperbaiki di 0.34.1 tidak mengalami regresi.
- Tampilan 1280×1024, skala 100/125/150%, mode Windows terang/gelap, keyboard/fokus, teks panjang dan keadaan nonaktif tetap terbaca.

## High effort gate

Tidak ada rekomendasi High untuk seluruh pekerjaan. Batch 6/7 memiliki risiko yang dapat membenarkan High, tetapi mulai Medium dengan inspeksi dan pengujian terarah.

Naikkan hanya batch/submasalah terdampak apabila ada: akar masalah masih ambigu setelah inspeksi; risiko korupsi/kehilangan data; race condition; perubahan shared core/arsitektur; dependensi lintas modul yang tidak bisa dipisah; isu keamanan kritis; upaya Medium berulang gagal; blast radius/regresi besar; atau reasoning kompleks yang nyata. Catat bukti dan alasannya, bukan jumlah item.

## Sumber kebutuhan

- [UI modern dan kontras](BACKLOG_UI_MODERN_DAN_KONTRAS_20260831.md)
- [Antrean dan dashboard harian](BACKLOG_ANTREAN_DASHBOARD_HARIAN_20260831.md)
- [Master obat dan pasangan DDI — revisi 2](BACKLOG_MASTER_OBAT_PAIR_DDI_20260831.md)
- [DDI lintas resep](BACKLOG_DDI_LINTAS_RESEP_20260831.md)
- [Bukti rilis 0.34.1](C:/Users/ozie1/Documents/Codex/2026-08-31/files-pasted-by-the-user-lanjutkan/outputs/CATATAN_RILIS_DAN_UAT_0.34.1.md)
- [Hasil P0 — inspeksi dan kontrak teknis](P0_HASIL_INSPEKSI_DAN_KONTRAK_TEKNIS_20260831.md)

Catatan kebutuhan terdahulu tetap menjadi rincian pendukung. Rencana ini menyatukan prioritas dan dependensinya; tidak membatalkan persyaratan pelestarian data, audit, pembatasan akses, atau persetujuan perubahan schema.

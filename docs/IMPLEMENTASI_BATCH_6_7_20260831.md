# Implementasi Batch 6–7 — E-MAS Farmasi

Tanggal: 31 Agustus 2026. Baseline sumber: 0.34.1. Engine DDI: 2.1.0.
Status: implementasi selesai pada kode sumber; **411 tes lulus**, tanpa kegagalan/error/skip pada regresi akhir.
**Ini perubahan kode sumber, belum installer/rilis operasional baru.**

## Batas pekerjaan

Mengikuti rekap yang telah disetujui: Batch 6 dan Batch 7 termasuk Wave 3 / HEAVY, effort awal Medium. Batch 6 dikerjakan dan diuji dahulu, baru Batch 7. Banyaknya item tidak menaikkan seluruh batch UI menjadi High. Tidak menjalankan subagent dan tidak mengubah model sesi melalui rekomendasi ini.

Proyek: `C:\Users\ozie1\Documents\Codex\2026-08-28\files-pasted-by-the-user-prompt\work\emas-farmasi`.
Checkpoint sebelum perubahan berada di `work/before_batch_6_7` pada task ini. Manifest SHA-256 memuat daftar perubahan dan hash sebelum/sesudah.

Tidak mengubah database Khanza, database operasional E-MAS, konfigurasi instalasi, schema/model database, atau berkas migration. Database yang ditulis selama pengujian hanya database sintetis terpisah. Schema tetap `0028_pharmacy_scope`. Enam WAV dan dua PDF bawaan tetap identik dengan checkpoint. Nomor aplikasi/installer masih 0.34.1; jangan menganggap installer lama sudah berisi fitur ini.

## Batch 6 — alur yang sekarang tersedia

1. Masuk menggunakan akun bernama **SUPER_ADMIN** atau **KFT**.
2. Buka **Master Obat → Tambah Obat**. Isi nama, kandungan terverifikasi, dan sumber/referensi pemetaan. Untuk obat kombinasi, pisahkan kandungan dengan titik koma.
3. Kode Khanza hanya diisi jika memang diketahui. Bila kosong, sistem membuat identitas berawalan `LOCAL:`; bukan kode Khanza buatan.
4. Klik **Simpan & Aktifkan**. Pemetaan tersedia untuk skrining berikutnya. Setelah obat dibuat dari menu master, form pasangan terbuka dengan obat tersebut sebagai A.
5. Pada **Pasangan Interaksi Obat → Tambah Pasangan DDI**, cari obat A dan B dari master, pilih kandungan yang dinilai, status interaksi, severity, sumber, dan referensi.
6. Klik **Simpan & Aktifkan**. **Tidak ada tombol publikasi lain yang wajib diklik.** Edit/nonaktif tersedia pada pasangan yang dipilih.
7. Obat nonaktif tetap dapat ditemukan melalui pilihan **Termasuk nonaktif**. Buka Edit Obat dan Simpan & Aktifkan untuk mengaktifkannya kembali setelah meninjau pemetaan.
8. **Lihat Referensi** tersedia bagi pengguna yang hanya membaca. **Arsip versi / draft lama** mempertahankan akses alur lama sebagai pengelolaan lanjutan, bukan langkah rutin.

Pasangan kandungan A–B sama dengan B–A. Pembuatan duplikat ditolak dan diarahkan ke Edit Pasangan. Satu penilaian komponen obat kombinasi tidak otomatis menilai seluruh komponennya. Pemilihan yang pemetaannya belum disetujui diblokir; perubahan pemetaan saat dialog terbuka juga diperiksa lagi di service ketika menyimpan.

**Kontrol backend:** akun aktif dan peran diperiksa ulang di service; Mode Farmasi anonim ditolak bahkan bila diberi peran pengelola secara keliru. Hak APOTEKER, CLINICAL_REVIEWER, KNOWLEDGE_ADMIN, dan IT_ADMIN tidak diperluas menjadi hak aktivasi langsung.

Aktivasi referensi tidak mengubah atau melewati gate operasional/deployment yang sudah ada.

**Transaksi dan riwayat:** penyimpanan, aktivasi, versi, dan audit satu transaksi. Kegagalan audit menggagalkan perubahan. Token versi/pemetaan mencegah editor kedua menimpa perubahan pertama. Aktivasi satu pair membuat snapshot versi aktif baru secara internal: aturan lama disalin beserta statusnya, hanya pair terpilih yang diubah. Draft versi lain tidak ikut dipublikasikan. Hasil skrining dan aturan versi lama tetap tersimpan; tidak membuat persetujuan petugas lain atau intervensi fiktif.

Snapshot per perubahan ini menjaga konsistensi pembacaan tanpa migration, tetapi menambah ukuran database seiring banyaknya perubahan pair. Perencanaan penyimpanan/retensi untuk pemakaian jangka panjang perlu dipertimbangkan saat kualifikasi, bukan menghapus versi yang dirujuk hasil lama.

## Batch 7 — kontrak skrining lintas resep

- Resep 001 diperiksa internal. Resep 002 memeriksa internal + kandidat 001. Resep 003 memeriksa internal + kandidat 001 dan 002, termasuk ketika dokter/poli berbeda.
- Pencocokan memakai ID pasien stabil, sumber/adapter, nomor resep lengkap, dan revisi/event. Nama pasien atau akhiran nomor tidak menjadi kunci.
- Kandidat berasal dari snapshot yang **sudah tercatat di E-MAS**, pada layanan yang sama: **kunjungan yang sama ATAU selisih waktu perubahan sumber paling jauh 24 jam**. Selisih dua arah mengakomodasi resep yang terlambat masuk.
- Waktu perubahan sumber bukan tanggal pelayanan, durasi terapi, atau bukti obat masih diminum. Penggunaan aktual diberi status belum diketahui dan pesan **perlu rekonsiliasi**.
- RALAN/RANAP tidak dicampur dan routing instalasi tidak diubah. Resep dari adapter lain tidak dicampur; nomor identik dari sumber berbeda memiliki identitas penyimpanan terpisah.
- Batas pengambilan konteks 200 resep terdahulu. Jika terlampaui, hasil diberi peringatan belum lengkap; kandidat yang tidak terambil tidak dianggap aman.
- Sistem mengambil event terakhir tiap resep **sebelum** mengecek FINAL/validasi. Revisi/batal tidak membuat komposisi FINAL lama dipakai kembali.
- ID pasien kosong/tidak konsisten, asal layanan tidak diketahui, komposisi/pemetaan belum lengkap, dan pair yang belum dinilai tetap terlihat sebagai keterbatasan. Tidak ada konfirmasi aman berdasarkan ketiadaan temuan saja.
- Resep batal, termasuk yang itemnya sudah kosong, menghasilkan revisi baru yang menandai pembatalan/penarikan validasi. Tidak menghapus hasil lama atau memutar konfirmasi “skrining bersih”.

### Kepemilikan temuan, revisi, dan notifikasi

Satu kasus lintas resep dicatat pada resep yang **pertama kali diskrining lebih belakangan oleh E-MAS**. Urutan penerimaan ini stabil, berbeda dari urutan jam sumber: resep terlambat dapat menjadi pemicu walaupun jam resepnya lebih awal. Dengan demikian satu pasangan resep tidak dibuat dua kali sebagai A–B dan B–A. DDI internal dan DDI lintas resep pada kandungan yang sama tetap dua penilaian yang berbeda.

Setiap temuan lintas resep menyimpan kedua nomor resep, adapter, event/sequence/fingerprint/revisi sumber, revisi skrining bila sudah tersedia, waktu sumber, kunjungan, dokter, poli, kode/nama obat, kandungan, dan semua kemunculan obat yang mendasari pair. Data ini disimpan pada kolom JSON hasil yang sudah ada; tidak membutuhkan perubahan schema.

Revisi atau pembatalan sumber menjadwalkan resep pemilik temuan terkait sebagai `CONTEXT_PENDING` secara persisten. Worker memeriksa ulang snapshot lokal pada siklus berikutnya, tanpa membaca ulang seluruh resep ke Khanza. Status ini bertahan saat restart. Resep FINAL baru tetap diproses pada siklus pertama; resep selesai tidak dibaca ulang setiap detik.

Fingerprint konteks mencakup event yang dibatalkan/ditolak juga. Konteks yang kembali kosong tidak menghidupkan hasil “bersih” lama sebagai revisi terbaru. Perubahan identitas pasien juga tidak menggabungkan kedua pasien. Transaksi skrining diserialkan sebelum membaca konteks agar dua kedatangan bersamaan menghasilkan satu pemilik kasus, bukan dua hasil yang sama-sama melewatkan pasangan.

Hasil/konteks baru memperoleh revisi/tinjauan baru sesuai kebutuhannya. Tidak menyalin acknowledgement/intervensi lama sebagai persetujuan baru. Notifikasi lama yang masih menunggu ditahan ketika hasil baru tersedia; hasil dan tinjauan historis tetap tersimpan.

### Penghubung minimum ke UI dan dashboard

Rincian antrean membedakan **DDI lintas resep** dari DDI internal, menampilkan kedua resep/dokter/poli/waktu, dan pesan rekonsiliasi. Popup utama tetap mengikuti tingkat severity yang sudah ada.

Hitungan pasangan unik memakai pasangan kandungan, bukan ID penyimpanan kasus lintas resep. Jumlah temuan tetap dapat berbeda dari jumlah pasangan unik. Aturan nonaktif/tidak dapat dipakai tidak dihitung sebagai DDI positif hanya karena masih menyimpan severity lama. Integrasi penuh tampilan, periode, dan ekspor tetap merupakan Batch 8.

## Bukti pengujian

- Uji terarah mencakup hak service/UI; tambah obat → aktifkan pair → engine; referensi wajib; konflik dua editor; pembatalan transaksi; nonaktif/aktifkan ulang; draft lain dan riwayat tetap utuh.
- Mesin diuji dengan data sintetis: tiga resep/tiga dokter; temuan yang hanya ada antar-resep; internal + lintas pada kandungan sama; duplikasi; pair tidak diketahui; pemetaan hilang; isolasi pasien/sumber/layanan; jendela waktu; resep terlambat; retry; dua kedatangan bersamaan; restart; revisi/batal kosong; koreksi ID pasien; pemeriksaan ulang lokal.
- Regresi akhir: **411 lulus, 0 gagal, 0 error, 0 skip**, durasi 530,19 detik. Tujuh warning merupakan deprecation adaptor datetime SQLite/Python; bukan kegagalan tes. Bukti: `verifikasi-batch-6-7/pytest-final.xml` dan `pytest-final.log`.
- Coverage sesuai konfigurasi proyek (UI tidak termasuk): gabungan statement+cabang **88,08%**, melampaui batas 87%; statement 91,26%, cabang murni 75,26%. Bukti: `coverage-final.json` dan `coverage-final.txt`.
- Run awal seluruh suite: 406 lulus, 1 gagal karena fixture lama hanya mengharapkan pasangan internal dan tidak memuat snapshot sumber lengkap. Fixture diperbarui agar tetap memeriksa internal sekaligus cross-Rx. Run terarah setelah koreksi: 24 lulus. Log awal dipertahankan sebagai bukti proses, bukan bukti final.
- Uji form native Qt dengan data sintetis: alur simpan lulus pada skala 100%, 125%, dan 150%. Screenshot form dan detail lintas resep diperiksa. Ini bukan kualifikasi seluruh layar/DPI, persetujuan UAT klinis, atau verifikasi speaker.
- Pengukuran sintetis pada 5.001 aturan: aktivasi satu pair sekitar **0,253 detik**, skrining dua obat sekitar **0,061 detik**, dilakukan saat ada beban tes lain. Aturan aktif tetap 1; 5.000 draft tidak ikut diaktifkan. Ini bukan benchmark server/latensi operasional.
- Database benchmark: integrity check **ok**, pelanggaran foreign key **0**, rantai audit **valid**.
- Uji sintetis 200 resep riwayat menghasilkan seluruh 200 pair lintas resep dalam sekitar **0,379 detik**, tanpa mengambil data ke sumber. Saat kandidat melebihi batas 200, hasil menjadi INCOMPLETE dengan peringatan yang sesuai. Bukti: `synthetic-context-performance.json`. Angka ini juga bukan jaminan latensi operasional.
- Manifest: `verifikasi-batch-6-7/source-manifest.json`. Pengukuran: `synthetic-performance.json`.
- Diff terhadap checkpoint: `verifikasi-batch-6-7/BATCH_6_7_SOURCE.diff` (16 file sumber/tes berubah). Bukti berada dalam folder outputs task ini; salinan laporan di docs proyek bukan paket installer.

## Pekerjaan yang tetap pada Batch 8–9

1. Batch 8: sinkronisasi hasil efektif vs Riwayat di seluruh antrean/rincian, label konteks menunggu pemeriksaan ulang, pelaporan/ekspor lintas resep, serta state/fokus UI. Temuan UI lokal untuk dipisahkan sebagai LIGHT/Low: kontras baris antrean terpilih dan format waktu sumber yang lebih ringkas pada rincian.
2. Audit ulang bagian Batch 3–4 yang belum sepenuhnya tuntas: keseragaman definisi hari UTC vs tanggal pilihan lokal, pergantian tengah malam, ringkasan sesuai filter, indikator tindak lanjut lama, dan informasi refresh gagal/usang. Perubahan schema/tanggal pelayanan tetap memerlukan pembahasan terpisah bila dibutuhkan.
3. Batch 9: UAT terpadu oleh petugas, benchmark yang mewakili lingkungan RS, pengujian GUI frozen/installer/DPI lengkap, pembaruan dua PDF, versi dan paket final.
4. Verifikasi klinis terhadap sumber pair, keputusan rekonsiliasi, dan persetujuan penggunaan operasional adalah pekerjaan petugas berwenang. Tes sintetis bukan validasi terapi pasien Zainal atau pasien nyata lain.

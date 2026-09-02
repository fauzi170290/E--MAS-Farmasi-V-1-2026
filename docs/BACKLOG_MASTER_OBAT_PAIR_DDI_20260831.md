# Backlog E-MAS Farmasi — master obat dan pasangan DDI yang disederhanakan

Tanggal: 31 Agustus 2026.
Baseline: 0.34.1.
ID kebutuhan: MASTER-OBAT-DDI-001.
Revisi kebutuhan: 2 — penyederhanaan atas permintaan pengguna.
Status: Batch 6 diimplementasikan pada kode sumber; regresi akhir gabungan Batch 6–7 lulus 411 tes. Belum masuk installer/operasional. Lihat IMPLEMENTASI_BATCH_6_7_20260831.md.
Catatan ini mengganti rancangan sebelumnya yang mewajibkan Simpan Draft → penyelesaian HOLD → tinjauan → persetujuan KFT → publikasi versi untuk setiap penambahan. Aplikasi, database, schema dan installer 0.34.1 tidak diubah saat pencatatan.

## Keputusan alur baru

Pengguna adalah tenaga farmasi berpengalaman. Pengelolaan obat, pemetaan kandungan, dan pasangan DDI harus dapat diselesaikan melalui satu tindakan penyimpanan oleh akun bernama yang berwenang, tanpa persetujuan berulang di beberapa menu.

- **SUPER_ADMIN dan KFT** dapat menambah/mengubah obat, pemetaan, serta pasangan DDI dan mengaktifkannya langsung melalui **Simpan & Aktifkan**.
- Aksi tersebut sekaligus merupakan keputusan aktivasi oleh petugas yang masuk. Sistem mencatat akun, waktu, sumber/referensi, isi perubahan, dan hasil validasi secara otomatis.
- Tidak membuat rekaman fiktif seolah petugas lain melakukan review atau memberikan persetujuan terpisah.
- Hak aktivasi untuk peran APOTEKER/CLINICAL_REVIEWER tidak otomatis diperluas hanya karena uraian pengguna menyebut apoteker senior/klinisi. Daftar awal adalah SUPER_ADMIN dan KFT; penambahan peran lain harus ditetapkan secara eksplisit.
- Mode Farmasi tanpa identitas/kata sandi tidak boleh menjadi identitas penulis atau pengaktif master. Akses pengelolaan menggunakan akun bernama yang berwenang.
- **Simpan Draft** boleh tersedia sebagai pilihan sekunder jika petugas belum selesai. Draft bukan lagi langkah wajib.
- Tidak ada perubahan mode operasi aplikasi, gate deployment, atau persetujuan seluruh master lama secara otomatis. Penyederhanaan ini khusus pemetaan obat dan aktivasi entri DDI yang dipilih.

## Menu yang direncanakan

Di kelompok **Data referensi**, tampilkan dua menu utama berikut.

| Menu | Tindakan utama | Field penting |
|---|---|---|
| **Master Obat** | Tambah Obat, Edit Obat, Simpan & Aktifkan, Nonaktifkan | Nama, kode/identitas sumber, kandungan, asal pemetaan. |
| **Pasangan Interaksi Obat** | Tambah Pasangan, Edit Pasangan, Simpan & Aktifkan, Nonaktifkan | Obat A vs Obat B, kandungan yang dinilai, status interaksi, severity, sumber dan referensi. |

- Pemetaan kandungan menjadi bagian form Master Obat, bukan tahapan persetujuan terpisah.
- Setelah tambah obat berhasil, sediakan tindakan **Tambahkan Pasangan DDI** dengan obat baru otomatis terpilih sebagai Obat A.
- Obat B dipilih melalui pencarian master E-MAS. Dua obat yang sudah ada juga dapat dipasangkan.
- Status pengelolaan yang ditampilkan cukup **Aktif / Draft / Nonaktif**. Status klinis interaksi dan severity tetap field terpisah.
- Kolom ringkas menampilkan obat/pasangan, severity atau status klinis, status aktif, sumber, serta petugas/waktu perubahan. Rincian teknis dan histori tersedia bila dibutuhkan.
- Tidak mewajibkan pengguna mengklik Selesaikan HOLD, Setujui Tinjauan Klinis, Persetujuan KFT, Duplikasi Versi, atau Publikasikan sebagai bagian alur rutin baru.
- Bila versi internal tetap dibutuhkan untuk audit/hasil historis, pengelolaannya dilakukan sistem dan tidak menjadi pekerjaan administratif tambahan bagi pengguna.

## Perilaku Simpan & Aktifkan

1. Petugas berwenang mengisi form obat/pemetaan atau pasangan.
2. Sistem memvalidasi identitas, kandungan, status/severity, kelengkapan sumber, serta konflik data.
3. Penyimpanan, keputusan aktivasi, dan audit berhasil sebagai satu operasi konsisten.
4. UI baru menyatakan **Aktif** setelah backend mengonfirmasi entri dapat digunakan mesin skrining.
5. Entri aktif tersedia pada pemeriksaan berikutnya tanpa restart dan tanpa publikasi manual seluruh master. Hasil resep lama tidak ditulis ulang otomatis; pemeriksaan ulang tetap melalui alur yang tercatat.
6. Kegagalan validasi menunjukkan field yang perlu diperbaiki. Kegagalan transaksi tidak boleh meninggalkan data setengah tersimpan atau memberi pesan aktif palsu.

Aktivasi **per entri/pasangan** tidak boleh mengaktifkan semua rule DRAFT lama. Misalnya menambah A–B hanya mengubah A–B dan dependensi pemetaannya yang dipilih secara eksplisit; C–D yang masih draft tetap draft. Draft lain tidak menghalangi aktivasi pasangan valid. Jangan mengganti satu versi master dengan versi yang hanya berisi satu pasangan hingga rule lama hilang.

## Validasi otomatis yang tetap diperlukan

- Nama/kode/kandungan harus jelas; pencocokan berdasarkan identitas data, bukan teks tampilan saja. Tidak mengarang kandungan dari nama merek.
- Model sekarang mensyaratkan kode Khanza unik. Jika obat belum memiliki kode Khanza, tetapkan identitas lokal dengan asal data yang jelas; jangan membuat kode yang diklaim berasal dari Khanza. Tidak menulis ke database Khanza.
- A–B sama dengan B–A. Bila pasangan sudah ada, arahkan ke edit; jangan membuat duplikasi atau menimpa diam-diam.
- Obat kombinasi memperlihatkan pasangan kandungan yang akan dinilai. Satu severity/referensi tidak otomatis berlaku bagi semua kombinasi.
- Severity memakai Minor, Signifikan, Mayor, Kontraindikasi; NONE hanya untuk status yang sesuai. Status klinis seperti ASSESSED_NO_INTERACTION harus mempunyai dasar penilaian, bukan pengganti “belum diketahui”.
- Referensi DDI dapat berupa nama sumber dengan URL/DOI atau identitas publikasi yang dapat ditelusuri. Petugas menentukan isinya; sistem tidak mengarang atau mengklaim telah memverifikasi kebenaran klinis referensi secara otomatis.
- Referensi/asalan pemetaan kandungan tetap tercatat. Detail tambahan tidak perlu memaksa pengisian berulang bila sudah tersedia secara sah.
- Pasangan tanpa mapping yang memadai tidak ditampilkan siap skrining. Penyederhanaan menu tidak mengubah UNMAPPED/NOT_ASSESSED menjadi aman.
- Edit/nonaktifkan menyimpan jejak perubahan. Dua petugas yang mengedit data sama harus mendapat penanganan konflik yang jelas, bukan saling menimpa.
- Penonaktifan entri tidak menghapus hasil atau audit historis.

## Dasar teknis dari inspection

- src/emss/ui/knowledge/management.py sudah mempunyai form input DDI; gunakan kembali field yang relevan, ganti isian zat aktif bebas dengan pemilih master dan tampilan kandungan.
- src/emss/services/knowledge.py saat ini membatasi penyimpanan manual pada versi DRAFT dan publikasi pada satu versi master, dengan peran penulis berbeda dari KFT. Alur baru membutuhkan perubahan layanan, bukan sekadar penggantian tulisan tombol.
- src/emss/services/screening.py memilih versi master dan memeriksa beberapa atribut kelayakan rule. “Simpan & Aktifkan” harus dibuktikan membuat rule benar-benar terbaca, bukan hanya mengganti status di UI.
- Model sumber/referensi dan pemetaan sudah ada. Perluasan schema belum diputuskan. Bila perubahan schema diperlukan, buktikan kebutuhan dan minta persetujuan tersendiri.
- Pertahankan audit dan hasil historis yang sudah terikat versi. Pilihan mekanisme snapshot/versi internal baru ditentukan melalui inspection pada batch inti, bukan dipaksakan di tahap backlog.

## Batch A — Menu dan form ringkas

Issues: dua menu utama, pemetaan di dalam Master Obat, label/tombol Simpan & Aktifkan, ringkasan status, layout, penghilangan langkah administratif lama dari alur rutin.
Klasifikasi: LIGHT.
Wave: 1 — SAFE UI CHANGES.
Risk: rendah untuk perubahan visual saja.
Model: GPT-5.6 Luna.
Effort: Low.
Alasan: presentasi dan navigasi lokal tidak memerlukan reasoning sistem menyeluruh.
Dependency: kontrak tindakan ditetapkan; tombol tidak boleh mengklaim aktivasi berhasil sebelum layanan Batch C tersedia.
Verifikasi: form ringkas, field inti jelas, status klinis tidak tertukar dengan status aktif, tidak ada tombol mati tanpa penjelasan.
Rollback: patch UI terpisah dari hak akses dan penyimpanan.

## Batch B — Handler dan validasi form

Issues: pencarian obat, pengisian Obat A setelah tambah obat, CRUD lokal, validasi kode/kandungan/severity/referensi, deteksi duplikasi pasangan, state simpan/error, edit data dan pengikatan UI ke layanan.
Klasifikasi: MEDIUM.
Wave: 2 — LOCAL FUNCTIONAL FIXES.
Risk: sedang; salah ID atau pemetaan dapat mengubah arti input.
Model: GPT-5.6 Terra.
Effort: Medium.
Alasan: alur form, query lokal, dan UI–service; gunakan fondasi yang tersedia tanpa mencampurkan aturan aktivasi shared core.
Dependency: kontrak layanan Batch C; bagian independen bisa disiapkan lebih dahulu. Pengikatan operasional menunggu layanan siap.
Verifikasi: tambah obat → pilih pasangan → simpan; A–B/B–A; input kosong/tidak sesuai; kombinasi; edit/batal; transaksi gagal tidak memberi status aktif.
Rollback: handler dan CRUD terpisah; data pengguna tidak dihapus.

## Batch C — Aktivasi per pasangan dan kewenangan

Issues: SUPER_ADMIN/KFT dapat menyimpan sekaligus mengaktifkan; pemetaan aktif lewat satu tindakan; aktivasi satu pasangan tanpa menerbitkan seluruh draft; integrasi mesin skrining; audit keputusan langsung; preservasi versi historis; konflik dua editor dan konsistensi transaksi.
Klasifikasi: HEAVY.
Wave: 3 — DATA / SYSTEM CHANGES.
Risk: tinggi karena menyentuh otorisasi, master klinis bersama, dan kelayakan hasil skrining.
Model: GPT-5.6 Sol.
Effort: Medium sebagai awal.
Alasan: perubahan semantik publikasi versi menjadi aktivasi entri memerlukan reasoning sistem. UI dan handler tetap dapat dipisahkan.
Dependency: inspection layanan knowledge, mapping, screening, model hasil dan audit. Desain ditetapkan sebelum mengubah data/schema.
High effort gate: High hanya untuk bagian yang inspection-nya membuktikan race condition, ambiguity yang belum teratasi, risiko data loss/corruption, perubahan security-critical/shared core dengan kebutuhan reasoning tinggi, regression risk tinggi, atau beberapa percobaan Medium gagal. Jumlah menu/issue bukan alasan eskalasi.
Verifikasi: SUPER_ADMIN dan KFT berhasil; akun tidak berwenang/Mode Farmasi ditolak backend; satu aksi sah tercatat tanpa approval fiktif; A–B aktif dan terbaca screening berikutnya; draft C–D tetap tidak aktif; rule lama tidak hilang; hasil historis tidak berubah; konflik edit dan rollback; tidak mengubah mode pelayanan.
Rollback: rencana perubahan data dan pemulihan ditetapkan sebelum implementasi; tidak digabung dengan patch kosmetik.

## Hubungan dengan DDI lintas resep dan pelaksanaan

[Backlog DDI lintas resep](BACKLOG_DDI_LINTAS_RESEP_20260831.md) tetap terpisah. Master/pair aktif menyediakan sumber aturan; fitur lintas resep menentukan konteks pasien dan pasangan antar-resep. Penyederhanaan ini tidak otomatis menambahkan pemeriksaan lintas resep.

Urutan: UI independen → fungsi lokal → layanan/aktivasi sistem. Pengikatan yang mempunyai dependency langsung boleh menunggu Batch C; jangan membuat scaffolding tidak perlu atau mencampur semua wave dalam satu patch.

Perubahan ini tidak meminta sumber DDI baru, tidak mengaktifkan bundle DRAFT lama secara massal, tidak mematikan audit, dan tidak mengubah database Khanza. Versi target serta jadwal belum ditetapkan.

Rekomendasi model/effort adalah penilaian engineering per batch; bukan penggantian model otomatis. Acuan keluarga model: [OpenAI Model guidance](https://developers.openai.com/api/docs/guides/latest-model).

# Backlog E-MAS Farmasi — kontras dialog dan arah UI modern

Tanggal: 31 Agustus 2026.
Baseline rilis: 0.34.2. Perubahan sumber setelah rilis ini belum dibangun menjadi installer baru.
Status: KEBUTUHAN DICATAT; BELUM ADA PERUBAHAN UI modern/KODE/INSTALLER.
Sumber: dua gambar yang diberikan pengguna dalam percakapan; isi tulisan di gambar merupakan contoh tampilan, bukan instruksi untuk mengubah aturan aplikasi.

## 1. Perbaikan warna dialog Intervensi Apoteker

Permintaan pengguna: ubah warna tampilan yang ditunjukkan pada gambar pertama dan catat untuk perubahan selanjutnya.

Gejala terbukti secara visual:
- Area form/scroll berwarna hampir hitam, sedangkan label dan teks checkbox berwarna gelap.
- Label jenis intervensi, keputusan, komunikasi, dokter/pihak dihubungi, alasan, dan catatan sulit dibaca.
- Field input putih dan bagian luar dialog terang, sehingga tema terlihat tidak konsisten.
- Ini masalah keterbacaan, tidak hanya preferensi dekorasi.

Inspection terarah:
- src/emss/ui/intervention/panel.py membuat QWidget form_page di dalam QScrollArea; warna area form tidak ditetapkan secara lokal.
- src/emss/ui/application.py mempunyai aturan stylesheet bersama untuk teks dan beberapa container terang.
- Dugaan: pewarisan palette/background atau cakupan stylesheet pada isi scroll dapat membuat latar mengikuti tema gelap sementara teks mengikuti tema terang. Belum ada reproduksi runtime yang membuktikan penyebab tunggal.

Perubahan minimum yang direncanakan:
- Latar area form putih atau abu terang yang konsisten dengan dialog; teks label gelap dengan kontras jelas.
- Perbaiki label checkbox dan state fokus, hover, disabled, validasi/error tanpa mengubah kewenangan atau field wajib.
- Pertahankan peringatan klinis, arti status, isi form, handler penyimpanan, dan audit.
- Perbaikan lokal ini tidak menunggu penggantian tema seluruh aplikasi.
- Uji Windows tema terang/gelap serta scaling 100%/125%/150%, khususnya 1280 × 1024. Jangan menyatakan selesai hanya dari screenshot offscreen tanpa memeriksa palette yang memicu bug.

## 2. Identifikasi gaya referensi modern

Penilaian visual: gambar kedua paling dekat dengan **soft UI bernuansa glassmorphism ringan**: kartu putih/pastel, sudut membulat, bayangan lembut, gradasi mint/biru/lavender, dan kesan panel kaca. Ada nuansa neumorphism pada bayangan, tetapi tidak tepat menyebutnya neumorphism murni.

Ini nama pendekatan visual, bukan bukti framework tertentu. Dari gambar tidak dapat dipastikan apakah dibuat dengan Flutter, React, Qt, Figma, atau alat lain.

Referensi tersebut merupakan konsep aplikasi kesehatan mobile. Untuk E-MAS, ambil warna, kerapian, hirarki dan bentuk komponennya; tidak menyalin susunan tiga layar ponsel atau kartu besar ke seluruh tabel desktop.

Acuan: [NN/g — Glassmorphism](https://www.nngroup.com/articles/glassmorphism/) menjelaskan translucency/kesan kaca dan perlunya menjaga keterbacaan. Klasifikasi spesifik gambar ini adalah interpretasi visual, bukan identifikasi dari pembuatnya.

## 3. Arah desain yang disarankan untuk E-MAS

Pendapat desain: cocok untuk dimodernisasi secara bertahap menjadi aplikasi farmasi desktop yang terang dan mudah dibaca, dengan efek kaca hanya sebagai aksen.

- Background netral sangat terang, panel kerja putih solid, teks gelap, aksen teal/biru.
- Kandidat palet awal, belum keputusan final: background #F4F8FB; panel #FFFFFF; teks utama #172B4D; teks sekunder #475569; aksen utama #0F766E.
- Sudut membulat moderat, border tipis, bayangan halus pada panel utama; hindari efek berlebihan pada tiap sel tabel.
- Sidebar desktop tetap menyediakan navigasi cepat. Antrean resep dan tabel pasangan tetap padat namun terbaca; kartu dipakai untuk ringkasan dan pengelompokan form.
- Input, tombol, label wajib, fokus keyboard dan pesan error harus jelas. Label tidak digantikan placeholder.
- Merah tegas tetap untuk risiko kritis/kontraindikasi/mayor, dengan label teks/ikon. Warna hijau tinjauan tidak mengubah arti risiko atau menjamin terapi aman.
- Tidak memakai transparansi/blur di belakang data obat, dosis, identitas pasien, tabel DDI, dan peringatan klinis.
- Tidak menyalin teks kecil/kontras pucat pada referensi. Ukuran font, ruang kerja dan scaling ditentukan dari layar kerja E-MAS.
- Blur/gradasi dekoratif bersifat opsional. Hindari blur bergerak/animasi terus-menerus; ukur pengaruh tema terhadap startup, scroll, refresh antrean dan popup.
- Gunakan komponen/Qt yang ada selama memadai. Tampilan modern tidak otomatis memerlukan pindah ke web, mengganti framework, atau menambah dependensi.
- Pedoman awal kontras teks normal 4.5:1 dan teks besar 3:1, mengacu [W3C WCAG 2.2 Contrast Minimum](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html). Ini target desain yang harus diuji, bukan klaim aplikasi sudah memenuhi seluruh WCAG.

Tahap pertama desain: contoh tampilan dialog intervensi dan satu halaman Antrean Resep dengan data sintetis. Nilai keterbacaan dan kecepatan kerja sebelum menerapkan gaya ke layar lain. Pencatatan arah visual ini bukan izin rewrite menyeluruh atau perubahan business logic.

## Batch A — Warna dan kontras dialog intervensi

Issues: latar form hitam, label/checkbox tidak terbaca, ketidakkonsistenan warna input dan container.
Klasifikasi: LIGHT.
Wave: 1 — SAFE UI CHANGES.
Risk: rendah untuk patch visual lokal; masalah keterbacaannya perlu diprioritaskan.
Model: GPT-5.6 Luna.
Effort: Low.
Alasan: targeted palette/stylesheet di dialog, tanpa perubahan data atau logika klinis.
Dependency: reproduksi tema/scaling yang bermasalah. Jika penyebab ternyata global, pisahkan bagian global dari patch lokal.
Verifikasi: semua label dan state terbaca; field wajib, checkbox dan simpan tetap berperilaku sama.
Rollback: patch lokal terpisah; tidak mengubah global configuration.

## Batch B — Rancangan visual modern

Issues: palet, tipografi, bentuk panel/tombol, spacing, hierarki, contoh Antrean Resep dan dialog intervensi berdasarkan referensi pengguna.
Klasifikasi: LIGHT untuk rancangan dan perubahan visual lokal.
Wave: 1 — SAFE UI CHANGES, dipisahkan dari perbaikan bug Batch A.
Risk: rendah; memakai data sintetis dan tidak menyentuh layanan.
Model: GPT-5.6 Luna.
Effort: Low.
Alasan: pekerjaan desain/presentasi; banyak elemen visual tidak membuat kebutuhan reasoning otomatis HEAVY.
Dependency: gaya desktop, warna risiko dan ukuran layar dipertahankan; contoh terbaca sebelum diperluas.
Verifikasi: desktop bukan salinan layout mobile, tabel tetap efisien, kontras/label jelas.
Rollback: perubahan visual per halaman, bukan satu patch seluruh aplikasi.

## Batch C — Konsistensi tema, resize dan penerapan bertahap

Issues: penerapan komponen terpilih ke halaman/dialog lain, interaksi stylesheet bersama dan palette Windows, resize/scaling, state fokus/seleksi/disabled, pemeliharaan posisi pilihan saat refresh.
Klasifikasi: MEDIUM bila memerlukan handler/layout/state atau koordinasi beberapa komponen. Perubahan kosmetik murni tetap LIGHT.
Wave: 2 — LOCAL FUNCTIONAL FIXES hanya untuk penyesuaian perilaku layout/state; styling murni tetap Wave 1.
Risk: sedang karena stylesheet bersama dapat memengaruhi form atau dialog lain.
Model: GPT-5.6 Terra.
Effort: Medium.
Alasan: konsistensi lintas komponen membutuhkan pengujian terarah, tetapi tidak memerlukan perubahan mesin DDI/database.
Dependency: pola Batch B terpilih. Pecah per halaman/komponen; jangan menaikkan model karena jumlah layar.
Verifikasi: tema terang/gelap, skala layar, antrean, dialog master/pair, popup, keyboard, font, posisi pilihan dan respons UI.
Rollback: per komponen/layar, tanpa migrasi data.

Tidak ada Batch HEAVY/High yang otomatis diperlukan untuk permintaan visual ini. Bila ditemukan kebutuhan mengganti shared core, global configuration atau arsitektur tema, catat terpisah sebagai Wave 3; jangan memperluas scope atau effort tanpa bukti. Kebijakan aktivasi master dan DDI lintas resep tetap berada dalam backlog masing-masing.

## 4. Tambahan setelah build terakhir: alert klinis terpadu dan modernisasi UI

### Aturan alert satu resep

Jika satu resep mempunyai potensi duplikasi obat sekaligus DDI berstatus MAYOR atau CONTRAINDICATED, sistem menampilkan satu popup klinis terpadu. Risiko tertinggi menentukan urutan, judul, warna, suara, dan tindakan awal:

1. CONTRAINDICATED; popup merah dan tindakan tinjau/penundaan sesuai kebijakan layanan.
2. MAYOR; popup oranye-merah dan wajib ditinjau.
3. Duplikasi obat; hanya sebagai temuan tambahan dalam popup risiko yang lebih tinggi dan pada rincian resep.
4. Popup duplikasi berdiri sendiri hanya bila tidak terdapat CONTRAINDICATED atau MAYOR.

Tidak boleh ada cascade popup untuk satu resep yang membuat duplikasi muncul lebih dahulu. Semua pasangan DDI dan isu duplikasi tetap disimpan pada kajian/audit. Hasil belum dipetakan atau belum tervalidasi tidak ditampilkan sebagai kondisi aman.

### Arah visual yang dipilih untuk prototipe

Gunakan **modern clinical soft-glass**: glassmorphism ringan pada area dekoratif dan kartu ringkasan, dengan kedalaman lembut yang terinspirasi neumorphism. Jangan menerapkan liquid glass penuh atau neumorphism murni pada data pasien, tabel, input obat, dan popup risiko karena dapat mengurangi kontras serta kecepatan kerja.

- Tipografi UI desktop: Segoe UI Variable bila tersedia di Windows; fallback Segoe UI, Arial, sans-serif. Judul 20–24 px, isi 13–14 px, tabel minimum 12 px.
- Latar netral terang, kartu putih hampir solid, border transparan tipis, radius 10–14 px, dan bayangan halus satu arah.
- Aksen teal/biru hanya untuk navigasi, aksi, dan status nonkritis. Merah/oranye tetap khusus risiko klinis.
- Tidak ada blur/transparansi di atas identitas pasien, dosis, hasil DDI, form keputusan, atau teks penting.
- Semua tampilan harus tetap terbaca pada 1280x1024 dan skala Windows 100/125/150 persen, termasuk fokus keyboard, disabled, hover, seleksi, tabel panjang, dan dialog.

### Batch D — prioritas alert klinis terpadu

Issues: urutan popup/audio untuk resep yang memiliki duplikasi serta DDI mayor/kontraindikasi; isi popup ringkas yang tetap memperlihatkan semua temuan.
Klasifikasi: MEDIUM. Wave: 2 — LOCAL FUNCTIONAL FIXES.
Risk: sedang; menyentuh keputusan notifikasi dan tampilan, tetapi tidak mengubah basis data maupun aturan klinis.
Model: GPT-5.6 Terra. Effort: Medium.
Alasan: perlu menyatukan hasil skrining, validasi, audio, popup, dan audit dalam satu jalur serta menguji skenario kombinasi.
Verifikasi: satu resep kombinasi menampilkan kontraindikasi atau mayor lebih dahulu; tidak ada audio/popup duplikasi ganda; seluruh temuan tetap tersedia di detail dan audit.
Status: SELESAI DI SOURCE setelah rilis 0.34.2; 22 tes terarah lulus. Belum dibuat installer baru.

### Batch E — prototipe visual modern terukur

Issues: design tokens, font, kartu, tombol, input, panel Antrean Resep, dan dialog Intervensi; diterapkan bertahap tanpa mengubah business logic.
Klasifikasi: LIGHT untuk token dan dua layar prototipe; MEDIUM hanya bila stylesheet bersama menyebabkan dampak lintas layar.
Wave: 1 — SAFE UI CHANGES terlebih dahulu, lalu Wave 2 secara terpisah bila diperlukan.
Risk: rendah sampai sedang, dengan rollback per layar.
Model: GPT-5.6 Luna untuk prototipe LIGHT; GPT-5.6 Terra untuk penyesuaian MEDIUM. Effort: Low lalu Medium sesuai hasil inspeksi.
Alasan: presisi dicapai melalui sistem komponen dan pengujian visual terarah, bukan melalui redesign sekaligus.
Verifikasi: pembandingan screenshot sebelum/sesudah untuk dua layar, uji fungsi yang telah ada, kontras, resize, dan mode Windows terang/gelap.
Status: E1 dan E2 SELESAI DI SOURCE setelah rilis 0.34.2. Design tokens desktop, tipografi Segoe UI Variable dengan fallback, kartu, kontrol, tabel, tab, checkbox, scrollbar, dan status bar telah dimodernisasi tanpa mengubah logika klinis. 69 tes UI/unit lulus. Belum dibuat installer baru.

## Dokumen terkait

- [Master obat dan aktivasi pasangan yang disederhanakan](BACKLOG_MASTER_OBAT_PAIR_DDI_20260831.md).
- [DDI lintas resep pasien yang sama](BACKLOG_DDI_LINTAS_RESEP_20260831.md).

Rekomendasi model/effort adalah penilaian per batch menggunakan keluarga model yang sudah dibahas; bukan penggantian model otomatis. Belum ada mockup baru, perubahan aplikasi atau build installer pada pencatatan ini.

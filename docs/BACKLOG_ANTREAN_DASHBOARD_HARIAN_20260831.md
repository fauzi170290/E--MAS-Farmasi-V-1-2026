# Backlog E-MAS Farmasi — antrean dan Dashboard Kajian pDDI harian

Tanggal: 31 Agustus 2026.
Baseline: 0.34.1.
ID: ANTREAN-DASHBOARD-HARIAN-001.
Status: DIAGNOSIS KODE DAN KEBUTUHAN DICATAT; BELUM DIIMPLEMENTASIKAN.
Pencatatan tidak menghapus resep, pasangan DDI, audit, hasil skrining, intervensi, atau mengubah installer.

## Kebutuhan pengguna

Antrean pelayanan hari ini tidak dipenuhi resep kemarin/lusa yang sudah dibaca E-MAS. Seluruh DDI tetap tersimpan dan dapat dikaji dalam Dashboard Kajian pDDI. Dashboard default menunjukkan hari ini dan mengikuti pembaruan hasil, bukan menampilkan angka tahunan/seluruh histori seolah angka harian.

“Selesai dibaca/disaring E-MAS” berbeda dari “sudah ditinjau petugas”. Pergantian hari atau menyembunyikan baris lama tidak boleh membuat tinjauan/intervensi fiktif.

## Diagnosis terarah

| Issue | Temuan kode 0.34.1 | Confidence / batas |
|---|---|---|
| Resep lama masih tampil | services/queue.py, list_items memfilter layanan/status/pencarian tetapi tidak tanggal; default semua status. Urutan prioritas dapat menempatkan resep lama berisiko tinggi di atas resep baru. | Tinggi untuk penyebab perilaku default; belum mencocokkan setiap baris pada instalasi pengguna. |
| Apakah karena belum ditinjau? | Tombol tinjauan mengubah status, bukan tanggal atau menghapus baris. Resep REVIEWED juga dapat tampil pada filter semua status. | Tinggi. Bukan semata belum mengklik tombol tinjauan. |
| Angka dashboard terlihat total | ui/dashboard/panel.py default YEAR; pilihan MONTH/QUARTER/YEAR/ALL, belum ada DAY/TODAY. Service juga belum mendukung periode harian. | Tinggi. Default berupa agregat tahun terpilih, bukan angka hari ini. |
| Apakah dashboard menghitung baris yang terlihat? | services/dashboard.py menghitung hasil efektif dari data tersimpan dan pasangan ScreeningPair; tidak mengambil daftar baris UI antrean. | Tinggi. Mengubah tampilan antrean saja tidak memperbaiki periode dashboard. Menghapus queue di DB justru dapat mengganggu agregasi yang bergantung padanya. |
| Dashboard tidak update | application.py telah menghubungkan hasil skrining baru dan queue_changed ke refresh dashboard untuk akun berwenang. | Jalur refresh ada. Kegagalan aktual belum terbukti; perlu reproduksi periode, event, sumber pembaruan, pergantian hari dan error query. |

Area terkait: services/queue.py; ui/queue/panel.py; services/dashboard.py; ui/dashboard/panel.py; penghubung event pada ui/application.py.

## Antrean pelayanan harian

- Saat membuka Antrean Resep, default **Hari Ini**, dengan tanggal yang terlihat jelas.
- Tabel dan angka ringkasan antrean harus memakai periode, scope layanan, dan filter yang konsisten. Label menjelaskan bila suatu angka merupakan total hari terpilih sebelum filter status.
- Resep dari hari sebelumnya yang sudah diproses keluar dari tampilan utama Hari Ini, bukan dihapus dari database.
- Riwayat Pemeriksaan menyediakan tanggal/periode dan Seluruh Data untuk menemukan resep serta semua hasil lama.
- Sediakan indikator/link ringkas **Belum ditinjau dari hari sebelumnya: N** atau **Tindak lanjut sebelumnya** yang membuka riwayat terfilter. Baris lama tidak memenuhi tabel hari ini, tetapi pekerjaan klinis yang belum selesai tetap dapat diketahui.
- Jangan otomatis menandai REVIEWED, membuat intervensi, atau mengakui/mematikan alert tertunda ketika hari berganti. Perubahan aturan pengiriman alert lama merupakan scope terpisah.
- Memilih tanggal lama untuk penelusuran tidak boleh tiba-tiba kembali ke hari ini saat polling. Sebaliknya, mode Hari Ini mengikuti pergantian tanggal secara otomatis.
- Tetap pertahankan pilihan ID resep ketika refresh dan pembatasan RALAN/RANAP.

## Dashboard Kajian pDDI harian

- Tambahkan pilihan **Hari Ini** sebagai default, serta **Tanggal tertentu**. Bulanan, Triwulanan, Tahunan, dan Seluruh Data tetap tersedia untuk kajian historis.
- Kartu ringkasan, distribusi severity, tabel unit, angka pembanding dan ekspor mengikuti periode yang dipilih. Indikator utama tidak mencampur angka harian dengan total tahunan.
- Grafik tahunan tetap dapat diakses pada periode/halaman yang sesuai; jangan memberi kesan grafik tahunan merupakan data hari ini.
- Tampilkan tanggal/periode aktif dan waktu pembaruan terakhir.
- Pembaruan otomatis dipicu hasil skrining baru/revisi serta perubahan relevan. Periksa juga ketika halaman dibuka kembali, sesudah perubahan intervensi, dan saat tanggal berganti.
- Gabungkan event berdekatan dan batasi refresh agregat; jangan menjalankan query penuh dashboard pada setiap polling satu detik atau pada jalur penyajian popup.
- Tombol Muat Ulang tetap tersedia. Jika refresh gagal, tampilkan status gagal/usang; jangan mengubah angka menjadi nol yang tampak sebagai hasil sah.
- Resep belum ditinjau tetap dihitung jika hasil skrining memenuhi definisi metrik. Mengklik “Tandai Sudah Ditinjau” tidak menghapus DDI dari kajian.
- Hasil pemetaan/pasangan belum dinilai tetap dibedakan dari tidak ditemukan interaksi.
- Hak akses dashboard saat ini tidak diubah oleh kebutuhan harian ini.

## Tanggal, histori, dan definisi metrik

1. Hari operasional memakai zona waktu instalasi/RS yang terverifikasi, dengan interval [00.00 hari terpilih, 00.00 hari berikutnya). Jangan memakai batas hari UTC secara langsung jika berbeda dari hari pelayanan.
2. Utamakan tanggal pelayanan/resep dari sumber yang maknanya terverifikasi agar resep kemarin yang baru terbaca atau diperiksa ulang hari ini tidak tampak sebagai resep baru hari ini.
3. Sumber yang belum tersedia/ambigu tidak boleh ditebak dari akhiran nomor resep. Tentukan fallback dan tampilkan basis tanggalnya; jangan diam-diam menyamakan tanggal resep, tanggal perubahan sumber, dan waktu ditangkap E-MAS.
4. Kode saat ini menggunakan ProcessingQueue.detected_at yang berasal dari captured_at. source_changed_at adalah waktu perubahan, tidak otomatis tanggal asli resep. Kontrak ini harus diperiksa sebelum patch filter harian.
5. “Resep hari ini” dan “aktivitas skrining yang dilakukan hari ini” adalah dua metrik berbeda. Default yang diminta adalah resep pelayanan hari ini; jika aktivitas skrining ditampilkan, beri label terpisah.
6. Pertahankan definisi hasil efektif terbaru per resep untuk mencegah double count retry/revisi. Telaah ranking revisi terhadap batas periode: pemeriksaan ulang hari berikutnya tidak boleh memindahkan resep ke hari lain atau membuat histori kemarin hilang hanya akibat filter.
7. Seluruh hasil/revisi dan pasangan tetap tersimpan. Kajian agregat hasil efektif tidak berarti menjumlah semua versi lama; rincian historis tetap dapat ditelusuri.
8. Catatan aktivitas intervensi mempunyai waktu sendiri. Angka aktivitas harian dan rasio tindak lanjut kelompok resep harus memiliki dasar waktu/denominator yang jelas.
9. Filter hari ini hanya memengaruhi tampilan/kajian, bukan menghapus konteks internal 24 jam untuk duplikasi atau membatasi kebutuhan DDI lintas resep yang telah dicatat.
10. Tidak ada penghapusan ProcessingQueue atau histori, reset database, migration, atau perubahan Khanza yang otomatis diizinkan oleh pencatatan ini.

## Batch A — Filter dan label periode

Issues: pilihan Hari Ini/tanggal, label tanggal, waktu pembaruan, akses Riwayat dan indikator tindak lanjut lama.
Klasifikasi: LIGHT.
Wave: 1 — SAFE UI CHANGES.
Risk: rendah untuk tampilan saja.
Model: GPT-5.6 Luna.
Effort: Low.
Alasan: kontrol dan label lokal; tidak mengubah data atau definisi hitungan.
Dependency: kontrak tanggal dari Batch B/C. Jangan memberi label Hari Ini jika query masih tahunan.
Verifikasi: periode jelas, label angka tidak menyesatkan, ruang tabel tetap cukup.

## Batch B — Filter antrean dan riwayat

Issues: predicate tanggal/layanan/status, ringkasan antrean, pencarian riwayat, indikator hasil lama belum ditinjau, pergantian hari dan preservasi pilihan baris.
Klasifikasi: MEDIUM.
Wave: 2 — LOCAL FUNCTIONAL FIXES.
Risk: sedang; salah batas hari dapat menyembunyikan resep yang seharusnya terlihat.
Model: GPT-5.6 Terra.
Effort: Medium.
Alasan: query lokal dan state UI–service; dapat dipisahkan dari mesin klinis.
Dependency: identifikasi tanggal sumber dan fallback tanpa menulis ulang histori.
Verifikasi: kemarin/hari ini/lusa, 23.59/00.00 zona lokal, resep sudah/belum ditinjau, keterlambatan pembacaan, retry, riwayat ditemukan, RALAN/RANAP, jumlah record tetap.
Rollback: filter saja; tidak memerlukan pemulihan data yang dihapus karena tidak ada penghapusan.

## Batch C — Agregat harian dan refresh dashboard

Issues: periode harian, dasar tanggal yang benar, revisi efektif tanpa double count, angka/kategori/ekspor konsisten, event refresh, pergantian hari, error/stale state, pengukuran query dan latensi.
Klasifikasi: MEDIUM untuk query laporan, period bounds dan handler lokal.
Wave: 2 — LOCAL FUNCTIONAL FIXES; patch terpisah dari antrean.
Risk: sedang; dapat menghasilkan angka kajian salah bila periode/denominator/revisi tercampur.
Model: GPT-5.6 Terra.
Effort: Medium.
Alasan: mengadaptasi agregasi yang sudah ada, bukan menulis ulang mesin DDI.
Dependency: definisi tanggal/hasil efektif disepakati dari bukti sumber. Penghitungan dashboard tidak bergantung pada baris UI antrean yang sedang terlihat.
Verifikasi: default Hari Ini; hasil baru tampil; hasil lama tetap pada histori/periode terkait; jumlah severity cocok; retry/revisi tidak ganda; tinjauan tidak menghilangkan DDI; angka nol yang sah; ekspor; tengah malam; beban refresh.
Rollback: query/handler/periode dipisah, tanpa menghapus histori atau mengubah hak akses.

Tidak ada kebutuhan HEAVY/High yang sudah terbukti untuk filter tanggal ini. Bila pemeriksaan menemukan kebutuhan migration, perubahan timestamp historis, shared core atau konsistensi lintas proses yang tidak dapat ditangani lokal, buat batch Wave 3 tersendiri dengan model kuat/Effort Medium dahulu dan High hanya dengan alasan gate yang nyata.

## Backlog terkait

- [DDI lintas resep](BACKLOG_DDI_LINTAS_RESEP_20260831.md).
- [Master obat dan aktivasi pasangan](BACKLOG_MASTER_OBAT_PAIR_DDI_20260831.md).
- [UI modern dan kontras](BACKLOG_UI_MODERN_DAN_KONTRAS_20260831.md).

Angka tes 0.34.1 bukan bukti perubahan harian ini berhasil. Setelah implementasi, jalankan tes terarah dan pengukuran baru; jangan membangun klaim dari diagnosis atau backlog saja.


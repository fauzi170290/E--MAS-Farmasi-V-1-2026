# Prompt task baru — upgrade e-MSS pascauji Khanza

Lanjutkan pengembangan e-MSS Farmasi berdasarkan temuan uji lokal 27 Agustus 2026 dan catatan proyek. Tugas ini mengizinkan implementasi perbaikan teknis e-MSS, bukan sekadar mengulang diagnosis atau mencatat backlog. Kerjakan secara otonom sampai implementasi, pengujian teknis, dokumentasi, dan installer untuk UAT lokal selesai; berhenti meminta keputusan hanya jika membutuhkan kewenangan baru, pilihan arsitektur material, atau persetujuan klinis yang tidak tersedia. Jangan menyatakan UAT rumah sakit atau kesiapan produksi telah lulus tanpa bukti aktual.

Rekomendasi pengaturan task: GPT-5.6 Sol, reasoning High. Pengaturan model dilakukan di aplikasi, bukan berubah otomatis karena teks prompt. Jangan membuat task tambahan, subagent, atau automation tanpa permintaan saya. Beri update singkat berkala. Hitung pesan pengguna dalam task baru ini dan beri tahu sekali ketika jumlahnya melebihi 10; jangan menganggap jumlah pesan sebagai ukuran pasti token atau biaya.

## 1. Lokasi dan dokumen wajib

Source aktif yang harus diaudit dan dipreservasi:
`C:\Users\ozie1\Documents\Codex\2026-08-13\lanjutkan-pengembangan-e-mss-farmasi-dari\work\emss-farmasi`

Root Git yang terdeteksi saat handoff:
`C:\Users\ozie1\Documents\Codex\2026-08-13\lanjutkan-pengembangan-e-mss-farmasi-dari`

Jangan kembali ke salinan Juli 2026 atau menimpa perubahan lokal. Periksa AGENTS.md, status Git, source, dependency, migrasi, dan laporan aktual terlebih dahulu. Jika bekerja dalam worktree baru, pastikan seluruh source, perubahan belum commit, backlog, serta audio dari lokasi di atas ikut tersedia sebelum implementasi; jangan kehilangan hasil pekerjaan hanya karena memulai dari default branch.

Baca lengkap:
- `docs/BACKLOG_KHANZA_REALTIME_AUDIO_20260827.md` — sumber kebutuhan terperinci, termasuk revisi keputusan popup tanpa interaksi dan audio pilihan pengguna.
- `docs/TEST_REPORT_SPRINT_23.md` dan `docs/SPRINT_23_BUNDLED_DDI_MASTER.md`.
- `docs/TEST_REPORT_KHANZA_RS_LOCAL.md`, `docs/LOCAL_KHANZA_TEST_RS.md`, dan kontrak view yang relevan. Laporan Agustus awal memakai clone berbeda; jangan menganggapnya kondisi runtime terbaru.
- Laporan terbaru di `outputs/qualification/`.

Python wajib:
`C:\Users\ozie1\Documents\Codex\.venv-emss313\Scripts\python.exe`

Arahkan TEMP/TMP pengujian ke folder writable di bawah `C:\Users\ozie1\Documents\Codex`. Minta izin filesystem secara spesifik bila diperlukan. Jangan mem-bypass sandbox. Pada task sebelumnya, pemberian izin ke ProgramData/XAMPP sempat merusak helper eksekusi; jika terjadi, laporkan dan gunakan lingkungan uji terisolasi yang diizinkan, bukan mengulang permintaan izin luas atau menghentikan semua pekerjaan teknis.

## 2. Baseline yang harus diverifikasi ulang

Source dan laporan Sprint 23 menyebut:
- Versi `0.30.0`.
- Alembic single head `0026_bundled_ddi_master`.
- 256 test passed; branch coverage keseluruhan tampil 88%, minimum historis 87%.
- Data lifecycle upgrade/backup/restore/downgrade/re-upgrade PASS.
- Binary dan installer lokal QUALIFIED; installer NotSigned.
- Negative gate `--require-signature` FAILED sesuai fail-safe.
- Installer `outputs/installer/e-MSS-Farmasi-RS-Setup-0.30.0-x64.exe`, SHA-256 `C8DD773EB639CBEAAF663211905E0D883A6A0FA9FDE60A3CA878D768105B6CA2` menurut laporan. Hash ulang, jangan menganggap laporan sebagai verifikasi baru.

Jangan mengarang nomor sprint/head. Tentukan versi dan migrasi berikutnya setelah audit. Coverage harus tidak turun dari baseline aktual yang dapat direproduksi; target minimal tampil 88%, dan jangan pernah melemahkan gate 87% yang sudah ada. Jangan menghapus test, mengecualikan kode sulit dari coverage, atau memalsukan hasil.

## 3. Kondisi runtime dan temuan uji

Aplikasi terpasang:
`C:\Program Files\eMSS Farmasi RS\e-MSS Farmasi RS.exe`
Config:
`C:\ProgramData\eMSSFarmasi\config.toml`
SQLite:
`C:\ProgramData\eMSSFarmasi\Database\emss.db`

Khanza lokal: MariaDB 10.4.32 dari XAMPP, host `127.0.0.1`, port `3306`, database `sik`. Source Khanza tersedia di `D:\PROJECT KHANZA\SIMRS-Khanza`, juga ada varian custom Salim. Cocokkan varian aplikasi yang benar sebelum menyimpulkan kontrak.

Akun aplikasi `emss_readonly` hanya SELECT pada empat view `vw_emss_prescription_header`, `vw_emss_prescription_item`, `vw_emss_compound_item`, `vw_emss_drug_master`. Password berasal dari environment `EMSS_KHANZA_PASSWORD`; nilai Machine Windows sebelumnya berbeda dari environment proses lama. Password Machine berhasil diuji. Jangan mencetak, menyimpan di source/laporan, atau mengubah password. Tangani startup/diagnostik kredensial secara aman; jangan mengubah sumber kredensial secara diam-diam.

XAMPP pernah rusak dan telah diinstal ulang; dump `D:\PROJECT KHANZA\sik\sik.sql` berhasil diimpor ke `sik`, 926 tabel. Jangan mengimpor ulang dump, menimpa database, atau memulihkan folder fisik yang rusak. Data historis dapat berisi identitas pasien nyata meski lingkungan lokal disebut uji; jangan kirim ke internet, log publik, screenshot, atau fixture repo. Gunakan kasus sintetis untuk pengujian yang dibagikan.

Hasil terakhir terverifikasi (periksa ulang, bukan asumsi keadaan sekarang):
- Koneksi CONNECTED, tetapi poll PARTIAL: 100 terdeteksi, 87 stabil, 0 diproses, 13 belum lengkap, 87 gagal dengan ScreeningUnavailableError.
- Cursor masih 27 Januari 2023; lebih dari 22 ribu resep historis mendahului resep baru.
- Master obat lokal 0, mapping 0; satu KB DRAFT, 5.432 pairs bawaan belum siap dipakai klinis. Kehadiran pair tidak sama dengan rule aktif atau interaksi yang harus di-alert.
- `khanza_polling_enabled=false`; interval 10 detik; page size 100; jeda stabilitas per resep 2 detik; popup baru diteruskan setelah seluruh batch selesai.
- Tiga resep uji yang dibuat pengguna: `202608270001`, `202608270002`, `202608270003`; semua sudah terlihat di view sebagai DIPROSES_FARMASI tetapi belum masuk antrean/skrining e-MSS. Masing-masing memiliki 4 item biasa; 5 item biasa; serta 2 item biasa + 4 komponen racikan. Jangan menyalin nama/identitas pasien ke laporan.

Pemetaan validasi yang telah dicek pada database dan source lokal:
- Peresepan: `resep_obat.tgl_peresepan` + `jam_peresepan`.
- Validasi/pemrosesan farmasi: `resep_obat.tgl_perawatan` + `jam`.
- Penyerahan: `tgl_penyerahan` + `jam_penyerahan`.
- `resep_obat.status` adalah ralan/ranap, BUKAN penanda validasi.
- View saat ini memetakan validasi menjadi DIPROSES_FARMASI dan mengubah changed_at. Jangan menganggap timestamp ini bukti persetujuan klinis atau seluruh item final sudah stabil.
- View item membaca resep_dokter dan resep_dokter_racikan_detail. Telusuri apakah perubahan obat saat validasi tersimpan di sumber lain; skrining harus mencakup komposisi final yang benar, bukan hanya resep awal.

## 4. Hasil yang harus dibangun

### Pembacaan otomatis dan keandalan

Setelah konfigurasi integrasi dan izin mode sah, pengguna cukup membuka e-MSS lalu bekerja di Khanza. Resep baru, validasi, dan revisi harus terbaca serta masuk daftar otomatis, tanpa klik Poll, Mulai Polling Otomatis, Muat Ulang, atau membuka tab Integrasi. Tetap bekerja ketika diminimalkan ke tray. Jelaskan perilaku jika aplikasi ditutup penuh; jangan memasang Windows service/autorun diam-diam.

Kebutuhan pengguna disebut "tanpa polling". Audit kemampuan event/push/CDC versus polling internal. Jangan menyebut polling sebagai push atau mengklaim realtime seketika. Sampaikan desain dan batas latensi. Jika kebutuhan literal tanpa polling memerlukan perubahan Khanza, trigger, binlog, hak akses baru, atau service server, minta persetujuan sebelum menerapkannya. Solusi tanpa klik pengguna dapat diprototipekan dan diuji di lingkungan terisolasi; jika tetap memakai polling internal, jelaskan tradeoff dan minta konfirmasi sebelum menjadikannya keputusan final terhadap persyaratan literal tersebut.

Pisahkan pemrosesan resep terkini dari replay historis dengan checkpoint/antrean yang teraudit. Jangan reset cursor, menghapus histori, melewatkan resep gagal, atau mengambil satu resep lewat SQL lalu mengaku seluruh alur otomatis sudah diperbaiki. Sediakan retry terarah yang sah agar tiga kasus uji dapat diperiksa tanpa menghabiskan seluruh backlog.

Tangani item parsial, transaksi belum lengkap, revisi dalam detik sama, perubahan item tanpa timestamp, timestamp dimundurkan, pembatalan validasi, restart, reconnect, dan race condition. Cegah kehilangan revisi dan alert duplikat. Jangan melemahkan pemeriksaan kestabilan hanya demi kecepatan. Audit bahwa deduplikasi tidak menghilangkan kewajiban pemberitahuan pada peristiwa validasi.

Tampilkan perbedaan koneksi, kesiapan KB/mapping, pemantauan aktif, backlog, progres resep, kegagalan, dan waktu hasil terakhir. Jangan menyembunyikan penyebab di balik PARTIAL/CONNECTED. Pesan kesalahan harus membantu pengguna awam tanpa membocorkan password atau identitas pasien.

### Kesiapan skrining

Perbaiki alur impor/sinkronisasi master obat dan mapping zat aktif agar dapat diselesaikan pengguna. Pertahankan pairs valid yang pernah diberikan, input manual, template, preview/import, review, dan publikasi. Jangan mempublikasikan KB atau mengaktifkan ribuan rule otomatis; jangan menyamar sebagai reviewer/KFT atau memalsukan identitas persetujuan. Approval klinis aktual tetap milik pihak berwenang.

Gunakan fixture sintetis dan basis pengetahuan uji terisolasi untuk membuktikan implementasi jika persetujuan klinis belum tersedia. Tandai bukti teknis versus UAT aktual dengan jelas. Jangan memaksa mock_mode, mengubah environment operasional, atau bypass gate untuk membuat resep pasien tampak lulus.

### Popup dan audio

Popup harus diterbitkan per resep setelah hasilnya tersedia, bukan menunggu batch. Untuk hasil major dan kontraindikasi, gunakan suara pilihan pengguna sesuai kategori rule yang benar; jangan menyamakan semua CRITICAL dengan kontraindikasi tanpa memeriksa klasifikasinya. Jangan meniadakan penanganan minor/moderate atau peringatan keselamatan lain.

Setelah validasi, hasil lengkap tanpa interaksi tetap WAJIB menampilkan popup dan suara. Teks: "Skrining selesai — tidak ditemukan interaksi pada basis DDI aktif". Ini bukan jaminan aman klinis. Jangan mengeluarkan konfirmasi ini saat ada mapping/item/pair belum dapat dinilai, KB belum siap, warning keselamatan lain, kegagalan koneksi/skrining, atau sekadar karena daftar alert kosong.

File pilihan pengguna sudah disalin dan hash dicatat di backlog, relatif terhadap source:
- `docs/audio-intake/screening-clear.wav` — Mixkit software interface start 2574, 2,347 detik, untuk hasil lengkap tanpa interaksi.
- `docs/audio-intake/major.wav` — Mixkit sci-fi error alert 898, 1,661 detik.
- `docs/audio-intake/contraindicated.wav` — Mixkit slot machine win alert 1931, 3,564 detik.

Semua PCM WAV stereo 44.100 Hz 16-bit. Jangan mengganti pilihan atau mengonversi tanpa alasan. Verifikasi lisensi/provenance sebelum bundling installer. Suara kontraindikasi perlu uji persepsi pengguna agar tidak dianggap bunyi sukses; jangan mengaku sudah mendengarkan jika hanya membaca metadata.

Implementasikan prioritas, antrean popup/audio, deduplikasi, pengaturan volume dan pemilihan/test suara, serta fallback visual jika file/perangkat audio gagal. Pertahankan mode silent pilot, otorisasi, dan fail-closed controls. Tombol demo suara/popup tidak boleh membuat hasil skrining klinis palsu.

## 5. Verifikasi dan deliverable

Mulai dengan audit dan baseline test aktual, kemudian implementasi bertahap. Migrasi baru bila diperlukan wajib single head dan backward-compatible. Jangan reset perubahan yang sudah ada atau mengubah ledger lama.

Uji otomatis dan skenario pengguna di lingkungan lokal terisolasi harus mencakup:
- Resep baru dan validasi terdeteksi tanpa klik e-MSS; hasil masuk daftar otomatis saat jendela normal dan di tray.
- Major, kontraindikasi, hasil lengkap tanpa interaksi, hasil belum dapat dinilai, racikan, substitusi/perubahan item final, dan rule tidak aktif.
- Backlog historis besar, reconnect, restart, retry, duplikasi, revisi tanpa timestamp, dan beberapa popup bersamaan.
- KB/mapping tidak siap, koneksi putus, audio hilang/rusak, serta tidak adanya konfirmasi aman palsu.
- Ukur latensi dari commit/terlihatnya resep atau validasi sampai skrining dan popup: laporkan p95/maksimum, volume/beban, dan target yang dipakai. Jangan mengarang angka atau mengeklaim hard realtime.

Jalankan seluruh regression test dan branch coverage. Jalankan upgrade/downgrade/re-upgrade, backup/restore/data lifecycle, binary qualification, installer qualification, serta negative signature gate. Preserve data/ledger dan konfigurasi pengguna. Installer tetap harus memuat pairs/template serta audio yang lisensinya memenuhi syarat. Jangan menginstal ke Program Files atau mengubah runtime pengguna/produksi otomatis; siapkan installer UAT dan minta izin saat deployment diperlukan.

Laporkan:
1. Temuan audit, perubahan, versi, dan Alembic head.
2. Jumlah test, persentase branch coverage, rollback/data lifecycle, binary/installer qualification, dan negative signature gate.
3. Lokasi installer serta SHA-256 aktual.
4. Bukti teknis end-to-end dan batas yang belum teruji; screenshot/JPEG UI dengan data sintetis.
5. Tutorial singkat pengguna: buka e-MSS, buat/validasi resep di Khanza uji, lihat hasil/popup/audio tanpa klik e-MSS.
6. Status tiap kebutuhan backlog, pekerjaan yang masih terbuka, serta blocker eksternal.

Tidak ada akses tulis klinis Khanza, perubahan produksi, global sql_mode, restore dump, penambahan hak admin, pemalsuan approval, atau bypass signature yang diizinkan oleh prompt ini. Jika view baru diperlukan, siapkan skrip untuk clone uji dan tinjau hak aksesnya; perubahan database yang sedang digunakan memerlukan konfirmasi target/backup/izin terlebih dahulu.

Integrasi read-only hanya membaca setelah commit. Jangan mengklaim dapat menahan cetak/validasi Khanza sebelum hasil keluar. Interlock tersebut adalah perubahan terpisah yang memerlukan kewenangan tambahan.

Signature/waiver, clean-host evidence rumah sakit, approval independen, deployment window, dan UAT aktual belum otomatis terpenuhi. Selesaikan seluruh pekerjaan teknis yang aman; jangan menutup task dengan klaim Production Ready.

# Catatan kebutuhan: pembacaan resep baru dan audio alert

> Pembaruan 28 Agustus 2026: permintaan suara hasil lengkap tanpa popup klinis dan
> pemisahan WAJIB instalasi Rajal/Ranap dicatat di
> [Perbaikan audio dan pemisahan layanan](PERBAIKAN_AUDIO_PEMISAHAN_LAYANAN_20260828.md).
> Dokumen tersebut memuat pembeda sumber yang telah ditelusuri, kriteria penerimaan,
> dan batas bukti; fitur barunya belum diimplementasikan.

Tanggal: 27 Agustus 2026.
Status: DICATAT / BELUM DIIMPLEMENTASIKAN.
Urutan yang diminta pengguna: lanjutkan perubahan ini setelah uji coba integrasi saat ini berhasil. Pencatatan ini bukan persetujuan produksi atau bukti UAT lulus.

## Harapan pengguna

Ketika resep tersimpan di database Khanza, e-MSS segera membaca resep, melakukan skrining, dan menampilkan popup pemberitahuan pada komputer yang menjalankan e-MSS. Pengguna mengharapkan pemrosesan tepat waktu, tanpa menunggu satu batch resep selesai.

Tambahkan pilihan file MP3 untuk interaksi major, kontraindikasi, dan nada konfirmasi hasil tanpa interaksi. Fitur audio masih berupa kebutuhan pengembangan, bukan kemampuan yang sudah tersedia.

## Kondisi uji terakhir yang terverifikasi

- Koneksi MYSQL: CONNECTED.
- Poll terakhir: PARTIAL; 100 terdeteksi, 87 stabil, 0 diproses, 13 belum lengkap, 87 gagal.
- Kesalahan antrean untuk 87 resep: ScreeningUnavailableError.
- Basis pengetahuan lokal masih satu versi DRAFT; belum ada versi PUBLISHED.
- Master obat lokal dan mapping komponen masih kosong saat pemeriksaan terakhir.
- Cursor pada tangkapan layar masih Januari 2023: resep baru tidak dijamin masuk batch berikutnya.
- Pengaturan yang diperiksa: polling 10 detik, maksimal 100 resep per batch, jeda stabilitas 2 detik per pemeriksaan ulang. Popup hasil saat ini diteruskan setelah batch selesai.

CONNECTED hanya membuktikan koneksi. Tidak muncul alert bukan bukti resep aman atau skrining berhasil. Kondisi ini belum lulus uji end-to-end.

## Kebutuhan pengembangan setelah uji

1. Pisahkan penanganan histori dari resep baru dengan alur eksplisit dan teraudit. Jangan menghapus histori, mereset cursor, atau melewati resep gagal secara diam-diam.
2. Kirim hasil dan popup per resep setelah skrining berhasil, bukan menunggu batch selesai; antarmuka tetap responsif.
3. Tetap verifikasi resep lengkap/stabil, tangani pembaruan resep, reconnect, retry kegagalan, dan deduplikasi alert. Jangan menjadikan resep parsial atau kegagalan sebagai SAFE.
4. Tentukan dan uji sasaran latensi dari resep lengkap yang sudah commit/terlihat di view sampai popup. Harapan adalah hitungan detik; angka SLA belum ditetapkan atau dibuktikan. Catat p95, maksimum, backlog, dan beban uji sebelum menyatakan realtime.
5. MP3 terpisah untuk major dan kontraindikasi berdasarkan klasifikasi rule terverifikasi, dengan prioritas, antrean suara, deduplikasi, volume, dan tombol tes. Kegagalan audio tidak boleh menghilangkan popup visual.
6. Nada hasil tanpa interaksi bersifat opsional. Label: "Skrining selesai — tidak ditemukan interaksi dalam basis data yang digunakan", bukan jaminan aman. Jangan putar nada ini saat koneksi/skrining gagal, data atau mapping tidak lengkap, maupun basis pengetahuan belum memenuhi syarat.
7. Hormati mode silent pilot, izin alert, dan kontrol keselamatan yang ada. Uji popup dan audio melalui jalur uji yang sah, bukan melewati approval operasional.
8. Pertahankan akses Khanza read-only, kompatibilitas data/ledger, serta seluruh quality gate proyek.

## Prasyarat dan bukti uji

- Gunakan Khanza lokal khusus pengujian dan pasien dummy; pastikan bukan database pelayanan sebelum memasukkan resep uji.
- Selesaikan master/mapping obat serta review, approval, dan publikasi basis pengetahuan melalui alur aplikasi yang berlaku. Jangan memalsukan approval klinis.
- Verifikasi terpisah: resep terlihat di view, diambil adapter, skrining berhasil, hasil sesuai rule, popup sesuai mode, dan audio sesuai kategori.
- Uji juga resep tidak lengkap, obat belum terpetakan, koneksi putus, revisi resep, duplikasi, antrean historis besar, MP3 hilang/rusak, serta beberapa alert bersamaan.
- Jangan menyertakan identitas pasien atau password dalam bukti yang dibagikan.

## Tambahan: pemicu validasi apoteker Khanza

Permintaan pengguna: setelah validasi apoteker pada Khanza tersimpan, e-MSS harus memeriksa resep tersebut dan menampilkan alert/popup apabila ditemukan interaksi yang memenuhi kriteria alert. Ini melengkapi pemicu resep baru, bukan menggantikannya. Implementasi diminta untuk tahap perbaikan berikutnya, bersama kebutuhan latensi dan MP3 di atas.

### Temuan langsung pada database uji, 27 Agustus 2026

Pemeriksaan dilakukan read-only atas satu resep uji yang ditunjuk pengguna. Nama pasien dan nomor resep tidak disalin ke catatan proyek.

| Peristiwa | Kolom pada `sik.resep_obat` | Nilai teramati |
| --- | --- | --- |
| Peresepan | `tgl_peresepan` + `jam_peresepan` | 2026-08-27 13:12:26 |
| Validasi/pemrosesan farmasi | `tgl_perawatan` + `jam` | 2026-08-27 13:14:14 |
| Penyerahan | `tgl_penyerahan` + `jam_penyerahan` | 0000-00-00 + 00:00:00; belum tercatat |
| Jenis pelayanan, bukan status validasi | `status` | ralan; skema enum ralan/ranap |

View aktif `vw_emss_prescription_header` mengembalikan `status_resep=DIPROSES_FARMASI` dan `changed_at=2026-08-27 13:14:14`. Pada pemeriksaan sebelum validasi, view mengembalikan `DIRESEPKAN` dan waktu peresepan 13:12:26. Artinya perubahan validasi sudah terlihat pada lapisan view; bukan bukti skrining/popup e-MSS sudah berhasil.

Source lokal Khanza mendukung pemetaan tersebut:

- `D:/PROJECT KHANZA/SIMRS-Khanza/src/inventory/DlgDaftarPermintaanResep.java`: tabel berlabel Tgl.Validasi/Jam Validasi mengambil `tgl_perawatan`/`jam` (label sekitar baris 65, pemetaan sekitar 2903).
- `D:/PROJECT KHANZA/SIMRS-Khanza/src/inventory/DlgCariObat.java`: penyimpanan memperbarui `resep_obat.tgl_perawatan` dan `jam` untuk nomor resep terkait (sekitar baris 1579).
- `templates/khanza_integration_views_mariadb104.sql`: menerjemahkan tanggal validasi menjadi `DIPROSES_FARMASI`; waktu penyerahan mendapat prioritas jika terisi.

Pemetaan ini berlaku untuk paket/database lokal yang diperiksa, bukan jaminan semua varian Khanza. Timestamp tersebut tidak dengan sendirinya membuktikan persetujuan klinis independen, kelengkapan telaah, atau identitas penandatangan.

### Persyaratan implementasi dan penerimaan

1. Kenali resep baru, transisi validasi, revisi setelah validasi, dan pembatalan validasi sebagai peristiwa yang berbeda. Simpan status sumber dan hasil skrining e-MSS terpisah; validasi Khanza tidak otomatis berarti SAFE di e-MSS.
2. Jadwalkan skrining per resep segera setelah transaksi tersimpan dan data lengkap/stabil. Hindari penundaan oleh backlog historis tanpa membuang histori atau menggeser cursor diam-diam.
3. Verifikasi sumber item yang benar setelah apoteker mengubah obat/jumlah/racikan. View saat ini membaca `resep_dokter` dan `resep_dokter_racikan_detail`; belum dibuktikan bahwa semua perubahan pada obat tervalidasi selalu tercermin di kedua sumber itu. Telusuri hubungan data hasil validasi sebelum menyatakan resep akhir tercakup.
4. Jangan mengandalkan `changed_at` tunggal sebagai bukti seluruh perubahan: uji tanggal yang dimundurkan, peristiwa dalam detik yang sama, penyerahan yang menutupi waktu validasi, dan perubahan item tanpa perubahan timestamp. Desain deteksi tidak boleh kehilangan revisi.
5. Jika hasil skrining menemukan interaksi yang memenuhi aturan alert, tampilkan popup per resep dan suara sesuai kategori ketika mode operasional mengizinkan. Gunakan deduplikasi berdasarkan resep/revisi/peristiwa agar polling ulang tidak mengulang alert tanpa alasan, tetapi risiko yang masih ada saat validasi tetap ditangani secara eksplisit.
6. Kegagalan skrining, basis pengetahuan belum siap, atau mapping tidak lengkap harus tampil sebagai kegagalan/belum dapat dinilai; jangan memberi nada konfirmasi tanpa interaksi. Tetap hormati silent pilot, otorisasi, dan kontrol keselamatan.
7. Ukur latensi dari validasi yang sudah commit/terlihat oleh integrasi sampai hasil dan popup. Sasaran numerik harus disepakati dan diverifikasi, bukan mengklaim seketika dari polling saja.
8. Buktikan end-to-end memakai resep dummy: sebelum validasi, sesudah validasi, setelah perubahan item, setelah reconnect, dan polling ulang. Verifikasi popup tidak tertimpa alert lain dan tidak hilang ketika batch masih berjalan.

Batas arsitektur: integrasi e-MSS read-only dapat membaca perubahan sesudah commit, tetapi tidak dapat menjamin pemeriksaan selesai sebelum tombol Validasi/Cetak Khanza dijalankan, atau memblokir pencetakan/penyerahan. Bila dibutuhkan interlock sebelum validasi/cetak, itu memerlukan integrasi tambahan pada alur Khanza, izin terpisah, serta pengujian; belum termasuk perubahan yang diimplementasikan.

## Tambahan: otomatis tanpa tindakan pengguna dan rencana uji berikutnya

Permintaan eksplisit pengguna: resep baru wajib otomatis masuk dan terbaca tanpa polling atau muat ulang; validasi Khanza harus diikuti skrining dan alert bila ada interaksi pada pair yang memenuhi kriteria.

### Kriteria pengalaman pengguna

- Setelah konfigurasi integrasi dan izin operasional sah, membuka e-MSS cukup untuk mengaktifkan pemantauan. Tidak perlu klik Poll, Mulai Polling Otomatis, Muat Ulang, atau membuka tab Integrasi terlebih dahulu.
- Resep baru, perubahan resep, dan validasi memperbarui daftar/status secara otomatis. Pemantauan tetap berjalan ketika jendela diminimalkan ke tray; keluar penuh dari aplikasi harus dinyatakan menghentikan pemantauan kecuali kelak ada service terpisah yang disetujui.
- Tampilkan status pemantauan aktif/berhenti, koneksi, keterlambatan/backlog, progres per resep, dan alasan skrining tidak tersedia secara jelas. CONNECTED saja tidak cukup sebagai indikator kesiapan.
- Jangan mengklaim arsitektur tanpa polling sudah tersedia. Adapter saat ini memakai polling berkala. Usulan notifikasi berbasis peristiwa/push atau change-data-capture perlu penilaian terpisah atas dukungan Khanza, izin server, keamanan, dan pemulihan. Tidak ada izin otomatis memasang trigger, mengubah binlog, atau memodifikasi server produksi. Minimum pengalaman yang harus dicapai: tidak ada polling/refresh manual oleh pengguna; mekanisme teknis akhir harus dijelaskan dan dikonfirmasi bila tetap memakai polling internal.

### Audit pengguna terbatas, bukan UAT GUI lulus

Pemeriksaan ulang 27 Agustus 2026 dilakukan melalui source/config dan pembacaan database lokal. Tidak dilakukan klik validasi, pencetakan, popup klinis, atau input resep baru oleh agen.

- `khanza_polling_enabled=false` pada config terpasang: pemantauan belum otomatis dimulai pada startup. Mengubah flag saja tidak menyelesaikan backlog atau kegagalan skrining.
- Resep uji yang ditunjuk pengguna masih belum tercatat pada antrean lokal e-MSS.
- Hasil poll terakhir tetap PARTIAL: 100 terdeteksi, 0 diproses, 87 gagal.
- Master obat 0, mapping 0, basis pengetahuan 1 versi DRAFT.
- Source UI memperbarui hasil popup setelah batch; belum memenuhi kebutuhan pemberitahuan per resep tepat waktu.

### Urutan uji yang disepakati untuk dilaksanakan berikutnya

| Tahap | Tindakan pada lingkungan uji | Bukti lulus yang harus diperoleh |
| --- | --- | --- |
| 1. Persiapan aman | Backup lokal, pastikan target Khanza uji, pilih kasus dummy dan hasil yang diharapkan | Target/config diketahui, backup tersedia, tidak ada perubahan pelayanan nyata |
| 2. Kesiapan DDI | Impor master obat; cocokkan kode ke zat aktif; reviewer berwenang memeriksa pair, status aktif, dan publikasi melalui alur aplikasi | Semua item kasus uji terpetakan dan rule/version memenuhi syarat; approval nyata, bukan dibuat otomatis |
| 3. Uji satu resep terarah | Skrining resep dummy yang sudah ada lewat jalur resmi yang tersedia; bila pengambilan per nomor belum tersedia, implementasikan jalur uji teraudit atau gunakan lingkungan uji terisolasi, bukan reset cursor produksi | Resep yang benar beserta item final berhasil diskrining, hasil sesuai kasus, tanpa kehilangan histori |
| 4. Perbaikan pembacaan dan notifikasi | Implementasikan kebutuhan startup otomatis, jalur resep terkini, retry revisi, pembaruan UI, dan popup per resep pada source lalu uji regresi | Seluruh test/quality gate tetap lulus; tidak ada bypass keselamatan |
| 5. UAT tanpa klik e-MSS | Buka e-MSS, lalu buat dan validasi resep dummy hanya di Khanza; ulang saat e-MSS di tray | Resep masuk sendiri, hasil dan popup sesuai kasus muncul tanpa Poll/Refresh, latensi terukur |
| 6. Uji negatif dan ketahanan | Item belum lengkap, mapping hilang, rule nonaktif, koneksi putus/pulih, restart, perubahan setelah validasi, duplikasi, banyak resep | Tidak ada konfirmasi aman palsu, resep/revisi tidak hilang, alert tidak membanjiri atau tertimpa |
| 7. MP3 dan penerimaan | Tambahkan/tes suara per kategori; ulang uji end-to-end dan installer | Audio/popup sesuai prioritas, visual tetap ada saat audio gagal, bukti penerimaan disimpan |

Kasus minimal: satu pair interaksi aktif, satu kasus kontraindikasi terverifikasi bila tersedia, satu kasus lengkap tanpa interaksi terdeteksi, serta satu kasus belum dapat dinilai. Gunakan data uji dan hasil yang ditetapkan reviewer; jangan memilih obat klinis atau mengaktifkan pair semata-mata agar demo berbunyi. Uji popup demonstrasi hanya membuktikan tampilan, bukan keberhasilan deteksi DDI.

Uji otomatis end-to-end saat ini TERBLOKIR oleh kesiapan mapping/rule dan kekurangan alur ingestion/notifikasi. Temuan ini menjadi dasar perbaikan teknis sebelum mengulang UAT; tidak perlu menunggu pengujian yang mustahil lulus pada kondisi sekarang. Pencatatan ini bukan perintah untuk langsung mengimplementasikan atau mengubah database.

## Audio pilihan pengguna dan popup tanpa interaksi

Tanggal intake: 27 Agustus 2026. Pengguna telah menyerahkan tiga file WAV dan menetapkan pemetaannya. Salinan byte-identik disimpan di `docs/audio-intake/`; file asli di Downloads tidak diubah. Ini bahan pengembangan, belum dipasang ke aplikasi/installer.

| Kategori | File asli pilihan pengguna | Salinan proyek | Durasi |
| --- | --- | --- | --- |
| Skrining selesai tanpa interaksi terdeteksi | mixkit-software-interface-start-2574 (clear skrining aman).wav | screening-clear.wav | 2,347 detik |
| Interaksi major | mixkit-sci-fi-error-alert-898 (mayor).wav | major.wav | 1,661 detik |
| Kontraindikasi | mixkit-slot-machine-win-alert-1931 (kontraindikasi).wav | contraindicated.wav | 3,564 detik |

Ketiganya terbaca sebagai PCM WAV stereo, 44.100 Hz, 16-bit. Pemeriksaan intake hanya meliputi metadata, pembacaan header WAV, dan hash salinan; bukan uji dengar manusia, kelayakan alarm klinis, atau keberhasilan playback di installer. Tidak perlu mengonversi ke MP3 hanya karena permintaan awal menyebut MP3.

SHA-256:

- screening-clear.wav: `7323C6CED9605A9B8A406CD088550D06D1A39DC8D37C9ABFE52B536482468AD5`
- major.wav: `5BFC539686EEA7CF48B9A8DFACFE143FE040B9DE5B10B211EC24EA9A98CE5754`
- contraindicated.wav: `FFED841350B0B4673CE02AB841636460156DB415AC1DE9E890562407D19B0B8F`

Keputusan pengguna terbaru menggantikan sifat opsional nada konfirmasi pada rancangan awal: setelah validasi resep dan skrining berhasil, hasil lengkap tanpa interaksi tetap harus menghasilkan popup serta suara konfirmasi. Teks yang disarankan: "Skrining selesai — tidak ditemukan interaksi pada basis DDI aktif". Hindari klaim jaminan aman secara klinis.

Syarat keselamatan dan penerimaan tambahan:

1. Popup/nada konfirmasi hanya boleh mengikuti hasil lengkap yang memenuhi kebijakan skrining, semua item/komponen dikenali, dan basis DDI memenuhi syarat. Tidak boleh berasal dari daftar alert kosong, status CONNECTED, validasi Khanza saja, atau exception yang ditelan.
2. Jangan menampilkan konfirmasi aman saat ada interaksi tingkat lain, peringatan keselamatan lain, data/pemetaan parsial, pasangan belum dapat dinilai, skrining gagal, atau basis pengetahuan belum tersedia. Pesan gagal/belum dapat dinilai harus berbeda.
3. Prioritaskan kontraindikasi di atas major dan konfirmasi tanpa interaksi ketika beberapa hasil muncul bersamaan. Popup harus mempertahankan hasil per resep; audio tidak bertumpuk. Deduplikasi tetap harus membedakan peristiwa validasi baru dari pembacaan ulang yang sama.
4. Pertahankan semua mode/otorisasi alert. Persyaratan ini tidak mengizinkan bypass silent pilot atau gate operasional; uji popup memakai lingkungan dan jalur uji yang sah.
5. Pilihan kontraindikasi bernama "slot-machine-win-alert" dari sumber. Pertahankan pemetaan pilihan pengguna, tetapi uji persepsi bersama pengguna/apoteker agar bunyi tidak disalahartikan sebagai konfirmasi sukses; belum dinilai melalui pendengaran.
6. Asal Mixkit berdasarkan nama file dan konteks penyerahan pengguna. Tautan aset serta ketentuan lisensi yang berlaku harus dicatat/verifikasi sebelum bundling/distribusi; pemeriksaan hash bukan bukti izin distribusi.
7. Uji playback WAV pada binary terpasang, volume/mute perangkat, file hilang/rusak, beberapa resep bersamaan, serta popup visual tetap tersedia ketika suara gagal. Fitur pengaturan dan tombol tes diperlukan tanpa menciptakan hasil klinis palsu.

Catatan ini tidak mengubah konfigurasi, database, status approval, source aplikasi, atau installer.

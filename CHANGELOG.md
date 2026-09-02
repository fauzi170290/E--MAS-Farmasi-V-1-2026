# Changelog

## 1.0.1 - 2026-09-02

- Menambahkan keputusan KFT bernama dan audit berantai untuk aktivasi cohort 175 pair DDI berstatus HOLD.
- Menambahkan validasi checksum cohort, severity, dan bukti sumber sebelum aktivasi; tujuh pair tanpa referensi tetap ditandai dalam audit keputusan.
- Menambahkan tombol operasional aktivasi HOLD pada Master Pasangan DDI setelah katalog H3 dipublikasikan.
- Menyertakan fallback audio H5-A pada paket rilis agar alert tetap memakai audio bawaan ketika berkas audio kustom tidak tersedia.

## 1.0.0 - 2026-09-01

- Menyelesaikan fondasi KFA, pemulihan dan aktivasi terverifikasi pasangan DDI bawaan, serta pemeriksaan pasangan aktif pada resep Khanza secara read-only.
- Memisahkan antrean operasional hari ini dari riwayat, memprioritaskan perubahan resep baru, dan menjaga polling satu detik dengan pemeriksaan kesehatan ringan pada siklus normal.
- Menambahkan ikon SVG klinis yang dibundel, bermakna, dan konsisten untuk navigasi serta tombol; hover/pointer/elevasi 180 ms diterapkan tanpa mengubah struktur, ukuran, jarak, warna utama, atau fungsi layar.
- Memperbarui panduan instalasi dan penggunaan untuk installer v1.0.0; panduan tidak lagi menyebut UJI LOKAL CEPAT.
- Installer tetap menjaga data serta konfigurasi `ProgramData`, mempertahankan koneksi Khanza read-only, dan membundel aset ikon, audio, seed, serta kedua panduan.

## 0.34.6 - 2026-09-01

- Menambahkan tindakan ringkas **Validasi KFT & Aktifkan yang Memenuhi Syarat** untuk akun bernama Super Admin/KFT.
- Mengaktifkan tepat 379 pair positif dengan referensi dan evidence setelah validasi bernama; 175 HOLD dan 11 DRAFT tetap nonaktif.
- Menyetujui 414 pemetaan obat Khanza/444 relasi kandungan yang identik dengan bundle; pemetaan yang hilang atau berubah diblokir secara individual.
- Mencatat validator, waktu, alasan, checksum bundle, jumlah aktif, dan jumlah diblokir pada audit atomik.
- Memastikan katalog PUBLISHED tetap lolos verifikasi ledger H1 dan pair aktif digunakan mesin skrining melalui kode obat Khanza.
- Menambahkan frozen-binary gate H3 serta tata cara operasional terpisah; kedua panduan PDF tidak diperbarui.

## 0.34.5 - 2026-09-01

- Menambahkan fondasi identitas KFA untuk zat aktif dan produk obat tanpa koneksi API SATUSEHAT serta tanpa mengubah keputusan klinis.
- Memulihkan visibilitas katalog bawaan berisi 5.432 pasangan DDI dan mempertahankan hasil review KFT maupun master lokal sebagai data terpisah.
- Menambahkan gate binary untuk instalasi/upgrade: bundle klinis harus ikut terkemas, ledger lama harus pulih, serta koreksi obat, review klinis, master lokal, konfigurasi, dan preferensi audio harus tetap utuh.
- Installer tetap mempertahankan database dan konfigurasi di `ProgramData`; katalog serta pemetaan bawaan tetap DRAFT/nonaktif sampai kebijakan aktivasi Batch H3.
- Tidak memperbarui dua panduan PDF; schema terbaru `0029_kfa_identity`.

## Unreleased — Batch H0 Fondasi KFA

- Menambahkan identitas BZA KFA `91xxxxxx` pada master zat aktif serta identitas produk KFA `92/93/94xxxxxx` pada master obat.
- Mempertahankan kode obat SIMRS lokal dan menambahkan `source_system`, sehingga pemetaan Khanza maupun SIMRS lain dapat menunjuk identitas KFA yang sama.
- Memungkinkan mesin skrining menemukan master melalui kode produk KFA tanpa koneksi API SATUSEHAT; konflik pemetaan kandungan untuk satu kode KFA gagal secara aman.
- Menambahkan migration `0029_kfa_identity`, validasi format KFA, audit metadata, pencarian/tampilan KFA pada Master Obat, dan kontrak seed yang siap menerima kode BZA KFA.
- Tidak mengaktifkan pasangan DDI, tidak mengubah severity/referensi klinis, dan tidak menyimpan kredensial SATUSEHAT.

## Unreleased — Batch H1 Pemulihan pasangan bawaan

- Memastikan katalog bawaan berisi tepat 5.432 pasangan unik dan 159 zat aktif, dengan profil severity/status yang dikunci pada manifest.
- Menampilkan seluruh pasangan bawaan pada menu Pasangan Interaksi Obat walaupun master masih DRAFT, sehingga data tidak lagi tampak hilang.
- Memulihkan ledger bundle lama yang hilang setelah migration/downgrade apabila identitas 5.432 pasangan tetap lengkap.
- Memasang bundle DRAFT berdampingan dengan master lokal yang sudah ada tanpa menimpa versi, aturan, severity, referensi, atau hasil review pengguna.
- Menolak katalog yang kehilangan pasangan, mempunyai pasangan asing, atau mengubah relasi bahan aktif; perubahan review KFT yang sah tetap dipertahankan.
- Tidak mengaktifkan aturan untuk skrining; aktivasi dan label verifikasi KFT tetap menjadi Batch H3.

## 0.34.4 - 2026-09-01

- Memprioritaskan resep baru/revisi dalam rentang realtime dan menurunkan backlog sinkronisasi awal ke lane sejarah agar ribuan resep lama tidak mendahului resep hari ini.
- Menormalkan prioritas salah dari versi 0.34.3 tanpa menghapus inbox, histori resep, hasil skrining, atau audit yang sudah tersimpan.
- Membaca kredensial Khanza tingkat Machine secara langsung pada Windows tanpa menyalin password ke konfigurasi atau environment proses, sehingga shortcut Desktop tidak memakai nilai proses lama.
- Menetapkan polling installer dan konfigurasi contoh menjadi 1 detik; stabilisasi, deduplikasi, transaksi read-only Khanza, serta kontrol publikasi DDI tetap berlaku.
- Tidak memperbarui panduan PDF; schema tetap `0028_pharmacy_scope`.

## 0.34.3 - 2026-08-31

- Memperbaiki kontras lokal dialog Intervensi Apoteker tanpa mengubah validasi, penyimpanan, audit, atau keputusan klinis.
- Menyatukan alert resep: kontraindikasi atau mayor menjadi popup/audio utama, sementara duplikasi obat tampil sebagai temuan tambahan tanpa cascade popup.
- Memodernisasi komponen desktop secara bertahap dengan tipografi Windows, panel terang, kontrol, tabel, tab, checkbox, dan scrollbar yang lebih konsisten.
- Menghapus mode **UJI LOKAL CEPAT** dari installer, CLI, adapter, polling, dan UI. Konfigurasi lama dinonaktifkan dengan aman saat dibaca; data internal dan konfigurasi tidak dihapus atau dialihkan ke Khanza produksi.
- Tidak memperbarui panduan PDF; schema tetap `0028_pharmacy_scope`.

## 0.34.2 - 2026-08-31

- Menambahkan alur ringkas master obat dan pasangan DDI bagi SUPER_ADMIN/KFT dengan aktivasi terikat snapshot/audit internal.
- Menambahkan pemeriksaan pasangan DDI lintas resep pasien yang sama dengan provenance lokal, evaluasi ulang aman saat konteks berubah, dan tanpa query longitudinal tambahan ke Khanza.
- Memisahkan hasil efektif hari ini dari riwayat revisi pada antrean, memperjelas status evaluasi ulang konteks, dan menyamakan ringkasan antrean dengan filter aktif.
- Menjelaskan basis metrik dashboard/ekspor, termasuk temuan lintas resep yang dimiliki satu resep pemicu agar tidak dihitung ganda.
- Memperbarui dua panduan PDF untuk alur aktivasi, DDI lintas resep, antrean efektif/riwayat, dan dashboard; schema tetap `0028_pharmacy_scope`.

## 0.34.1 - 2026-08-31

- Memperbaiki pemilihan baris antrean agar tindakan tetap terkait ID hasil yang dipilih, termasuk saat urutan antrean berubah; pilihan kosong menonaktifkan tindakan.
- Mode Farmasi dapat mencatat tinjauan dan meminta pemeriksaan ulang terarah dengan verifikasi akun petugas per tindakan, tanpa membuka akses admin/UAT atau membuat intervensi klinis.
- Tinjauan berlaku sampai revisi yang dipilih pada layanan yang sama; revisi baru tetap perlu ditinjau. Penanda tinjauan hijau tidak menghapus warna merah risiko tinggi.
- Menampilkan nomor asli Khanza dari metadata sumber, termasuk histori dengan prefiks internal lama; sumber simulasi tetap diberi identitas uji. Tidak mengubah histori atau skema.
- Menyederhanakan Status Sistem & Diagnostik untuk Mode Farmasi; detail teknis hanya untuk Admin/IT dan UAT tetap ditolak melalui UI maupun layanan.
- Memperbarui popup duplikasi, menampilkan semua pasangan dengan kategori spesifik, dan memisahkan Kendala Pemetaan Obat. Kontraindikasi/mayor tetap didahulukan dari duplikasi.
- Menambahkan koreksi terarah kode Khanza 000004629 (WARFARIN 1 MG) ke warfarin sebagai PENDING_REVIEW; tidak mengarang persetujuan klinis atau aturan DDI yang belum tersedia.
- Mempertahankan pemrosesan FINAL pada siklus pertama, isolasi RALAN/RANAP, enam WAV dan dua PDF panduan yang diperbarui. DDI lintas resep belum ditambahkan.

## 0.34.0 - 2026-08-29

- Memproses snapshot resep berstatus FINAL pada siklus pemantauan pertama dan mengeluarkan resep selesai dari antrean baca per detik.
- Menambahkan popup serta audio orisinal untuk interaksi SIGNIFICANT dan potensi duplikasi kandungan antarresep final pasien yang sama dalam 24 jam.
- Menetapkan volume audio awal 75 persen, minimum aplikasi 1 persen, dan membundel enam audio yang tetap dapat diganti pengguna.
- Menyatukan Antrean Resep dan Perlu Perhatian, menghapus kolom Mode, serta menandai seluruh hasil resep terpilih saat ditinjau petugas berwenang.
- Mengubah laporan menjadi Dashboard Kajian Potensi Interaksi Obat (pDDI), menghitung hasil efektif terbaru, menampilkan seluruh spektrum DDI, dan membatasinya untuk SUPER_ADMIN.
- Menambahkan dua PDF bantuan lengkap untuk instalasi awal dan penggunaan ke aplikasi serta installer.

## 0.33.0 - 2026-08-29

- Meminta pilihan Farmasi Rawat Jalan atau Rawat Inap saat pertama kali masuk Mode Farmasi tanpa kata sandi, lalu menyimpannya sebagai pengaturan instalasi yang tidak dapat diubah dari mode tersebut.
- Memfilter pembacaan view Khanza, antrean, rincian, ringkasan, dan pengiriman alert berdasarkan `asal_layanan` agar resep RALAN dan RANAP tidak silang workstation.
- Memproses status validasi Khanza pada pembacaan ulang cepat tanpa menunggu interval stabilisasi resep yang masih draf.
- Membundel empat nada WAV orisinal lokal untuk kontraindikasi, interaksi mayor, obat high-alert, dan konfirmasi pemeriksaan lengkap tanpa interaksi.
- Memutar konfirmasi aman dan high-alert sebagai audio saja, tanpa popup tambahan, serta mempertahankan popup untuk interaksi mayor/kontraindikasi.
- Memigrasikan preferensi tiga suara lama tanpa menghapus file pilihan pengguna dan menjaga database E-MAS di ProgramData selama upgrade/uninstall.

## 0.32.2 - 2026-08-28

- Opsi installer UJI LOKAL CEPAT mengatur pemeriksaan setiap 1 detik pada database yang sama, dengan backup konfigurasi dan persetujuan eksplisit.
- Timer menjadwalkan ulang pada batas baca stabil, memperhitungkan waktu proses, dan mencegah worker bertumpuk. Minimum dua detik pembacaan stabil, backoff koneksi, dan deduplikasi tetap berlaku.
- Hapus kolom/status lengkap-tidak lengkap dari antrean pelayanan dan popup; catatan kendala pembacaan, pemetaan, dan pasangan belum dinilai tetap tersedia. Tidak mengubah hasil tersimpan menjadi SAFE/COMPLETE.
- Polling tanpa perubahan tidak menghapus pilihan resep setiap detik; pemeriksaan kesehatan UI dibatasi periodenya.
- Paket master/DDI dan koreksi pengguna dipertahankan. Konfirmasi validasi basis oleh pemilik dicatat dalam catatan rilis, tanpa mengarang audit reviewer atau mengubah approval aplikasi terpasang.
- Pemisahan wajib Rajal/Ranap dan suara konfirmasi tanpa popup tetap backlog terpisah; versi ini belum menerapkannya.

## 0.32.1 - 2026-08-28

- Pilihan installer untuk PC uji Khanza lokal memakai database E-MAS yang sama; tanpa membuat resep atau database dummy baru.
- Persetujuan eksplisit, batas loopback dan tanggal mulai, polling otomatis, serta pilihan kredensial Windows Machine tanpa menyalin password ke konfigurasi.
- DDI DRAFT dan pemetaan belum disetujui hanya dipakai sebagai hasil uji; status review klinis tidak diubah.
- Alarm uji lokal hanya mayor/kontraindikasi setelah validasi, dengan pembacaan stabil dan pencegahan duplikasi yang sama.
- Riwayat lama tetap terlihat, tetapi kegagalan sebelum tanggal uji tidak dimasukkan ke antrean uji baru.
- Latar halaman mengikuti tema terang aplikasi meski Windows memakai tema gelap.

## 0.32.0 - 2026-08-28

- E-MAS Farmasi identity; legacy data paths, configuration, audio preferences and installer AppId retained.
- Grouped pharmacist workflow navigation, explicit incomplete/failed results and separate administrative actions.
- Bundle 5,432 DRAFT DDI pairs with 221 source drug mappings and 192 pending reference corrections; append missing codes once without overwriting user data.
- Preserve validated compact popup, category sound, allowed dummy patient scope and deduplication behavior.
- Installation and upgrade require qualification; no automatic clinical approval.

## 0.31.1 - 2026-08-27

- Fix startup QtCore: exclude foreign app-local ICU DLLs collected from build PATH; use Windows ICU.
- Quarantine only the known incompatible 0.31.0 ICU hash during upgrade; preserve database/configuration.
- Require real frozen login GUI smoke and reject app-local ICU in release qualification.
- No schema or clinical workflow changes; 0.31.0 installer withdrawn due to GUI startup failure.


## 0.31.0 - 2026-08-27

- Prototipe pemantauan polling internal dengan consent eksplisit, antrean persisten terkini/histori, stabilitas lintas siklus, retry terarah, dan observasi sumber teraudit.
- Notifikasi per resep, deduplikasi per peristiwa validasi, popup berantre dan pemilihan audio lokal; konfirmasi tanpa interaksi ditahan untuk data tidak lengkap.
- Sinkronisasi master tanpa menimpa mapping; export workbook mapping untuk workflow preview/review yang sudah ada.
- Migrasi aditif 0027 mempertahankan observasi/checkpoint saat downgrade. Gate coverage dikoreksi dari konfigurasi 85 ke minimum historis 87.
- Belum merupakan UAT rumah sakit, izin produksi, push/CDC, atau persetujuan distribusi audio Mixkit.


## 0.30.0 - Bundled DDI Master Seed

- Membundel tepat 5.432 DDI pairs dan 159 zat aktif dari master
  `DDI-KHANZA-v1.0.0` yang sebelumnya dimasukkan pengguna.
- Memverifikasi checksum bundle, checksum semantik, jumlah record, canonical
  pair, severity mapping, dan status fail-closed sebelum data diterapkan.
- Menerapkan seed hanya ketika master DDI masih kosong dan administrator sudah
  tersedia; database/master yang sudah ada tidak ditimpa pada upgrade.
- Mempertahankan status knowledge base sebagai `DRAFT`, seluruh rule
  `is_enabled=false`, serta workflow review/persetujuan klinis aplikasi.
- Tidak membundel akun, audit, resep, atau identitas pasien; satu identitas
  validator pada data sumber telah direduksi menjadi penanda migrasi.
- Mempertahankan input rule manual, unduh template, preview, import, commit,
  backup pra-commit, export master, dan seluruh kontrol knowledge-base lama.
- Menambahkan migrasi `0026_bundled_ddi_master`, provenance ledger immutable,
  regression, rollback/re-upgrade, dan qualification contract untuk seed.
- Memvalidasi 256 test pada Python 3.13.15, branch coverage keseluruhan 88%,
  lifecycle `PASS`, binary/installer lokal `QUALIFIED`, dan negative signature
  gate tetap `FAILED` untuk artefak `NotSigned`.

## 0.29.0 - UAT Execution & Independent Acceptance

- Menambahkan execution session dari dossier `SEALED`, window 1–168 jam, dan
  sepuluh scenario klinis/teknis wajib yang terikat release candidate.
- Menyimpan setiap result attempt sebagai metadata/checksum append-only;
  latest result per scenario wajib `PASS` dan result baru mencabut sign-off.
- Menambahkan issue WARNING/CRITICAL dan remediasi ber-hash, dual sign-off
  independen, keputusan `ACCEPT`/`REJECT` pihak ketiga, revocation, dan expiry.
- Menambahkan acceptance receipt yang menyatakan UAT berasal dari evidence
  eksternal dan tidak memberikan production authorization.
- Menambahkan migrasi `0025_uat_execution_acceptance`, UI, immutable ledger,
  negative-path regression, dan rollback/re-upgrade test.
- Memvalidasi 248 test pada Python 3.13.15, branch coverage keseluruhan 88%,
  service UAT Release 93%, lifecycle `PASS`, serta binary/installer lokal
  `QUALIFIED`; negative signature gate tetap `FAILED` untuk `NotSigned`.
- Menghasilkan starter kit UAT yang terikat RC final dengan candidate `DRAFT`,
  execution `NOT_STARTED`, dan seluruh sepuluh result `NOT_RECORDED`.

## 0.28.0 - UAT Release-Candidate Dossier

- Menambahkan dossier UAT yang terikat exact ke qualification `QUALIFIED`,
  versi, Alembic schema, nama installer, dan SHA-256 installer.
- Menambahkan readiness evidence untuk site approval, test data anonim, named
  user roster, clean host, backup/restore, Khanza read-only, dan training/SOP.
- Menolak evidence stale, invalid, tidak cocok, atau memuat key identitas
  pasien; metadata/checksum evidence disimpan immutable.
- Menambahkan attestation klinis/teknis independen, expiry/revocation,
  hash-chain ledger, serta kit UAT dengan seluruh result `NOT_RECORDED`.
- Menambahkan migrasi `0024_uat_release_candidate_dossier`, UI, dokumentasi,
  regression, dan compatibility test terhadap seluruh data legacy.

## 0.27.0 - Verified Evidence Package & Manual Deployment Ceremony

- Menambahkan verifikasi ZIP evidence produksi yang aman dan terikat ke release,
  versi, schema, installer, checksum seluruh evidence Sprint 19, change approval,
  dan snapshot evidence kanonik.
- Menyimpan setiap hasil verifikasi `VALID`/`INVALID` secara append-only;
  verifikasi terbaru yang invalid atau stale menutup authorization fail-closed.
- Menambahkan deployment ceremony dalam window aktif dengan attestation teknis
  dan klinis oleh akun berbeda, serta abort beralasan yang disimpan sebagai hash.
- Memperluas independensi keputusan produksi agar decision maker berbeda dari
  verifier package, pembuat ceremony, dan kedua attestor.
- Menambahkan authorization receipt ber-checksum yang secara eksplisit mencatat
  `NOT_PERFORMED_BY_EMSS`; aplikasi tetap tidak memiliki executor deployment.
- Menambahkan migrasi `0023_verified_evidence_ceremony`, UI, audit/ledger
  immutable, regression, branch coverage, dan rollback/re-upgrade test.
- Memvalidasi 240 test pada Python 3.13.15, branch coverage keseluruhan 88%,
  service Evidence dan Production Release 94%, lifecycle `PASS`, serta
  binary/installer lokal `QUALIFIED`; negative signature gate tetap `FAILED`
  untuk artefak `NotSigned`.

## 0.26.0 - Production Release Record & Deployment Authorization

- Menambahkan production release record yang hanya dapat dibuat dari
  surveillance `PROMOTED` dan terikat immutable ke versi, schema, environment,
  nama installer, checksum installer, serta seluruh ledger upstream.
- Menambahkan intake paket JSON ber-checksum untuk Authenticode `Valid` atau
  waiver formal ber-expiry, clean-host install/upgrade/uninstall, preservasi
  data, dan rollback/restore; evidence tidak dapat diperbarui atau dihapus.
- Menambahkan change approval ber-hash dan deployment window; authorization
  hanya aktif di dalam window serta wajib diputuskan pihak berbeda dari
  pembuat record, seluruh recorder evidence, dan approver perubahan.
- Menambahkan revocation, expiry, emergency rollback order, audit, serta ledger
  produksi append-only. Tidak ada service atau UI yang mengeksekusi deployment.
- Menambahkan migrasi `0022_production_release_authorization`, UI Production
  Release, regression, branch coverage, dan rollback/re-upgrade test.
- Memvalidasi 233 test pada Python 3.13.15, branch coverage keseluruhan 88%,
  service Production Release 95%, lifecycle `PASS`, serta binary/installer lokal
  `QUALIFIED`; negative signature gate tetap `FAILED` untuk artefak NotSigned.

## 0.25.0 - Early-Life Surveillance & Release Promotion Evidence

- Menambahkan surveillance yang hanya dapat dibuat dari limited rollout
  `COMPLETED` dan terikat pada versi/schema aktif serta ledger upstream valid.
- Menyimpan snapshot agregat non-MOCK: resep, CRITICAL, alert CRITICAL belum
  diakui, intervensi terbuka, kegagalan polling, health, dan validitas audit.
- Mewajibkan jumlah snapshot, rentang observasi, dan freshness minimum; data
  kosong/basi, health tidak READY, atau operational backlog menutup promotion.
- Menambahkan isu WARNING/CRITICAL dan remediasi dengan teks yang hanya disimpan
  sebagai SHA-256; isu terbuka mencabut attestation dan menahan promotion.
- Mewajibkan attestation klinis/teknis yang independen dan keputusan PROMOTE
  oleh Direktur/Super Admin independen; ROLLBACK tersedia sebagai fail-safe.
- Menambahkan migrasi `0021_early_life_surveillance`, trigger immutable, ledger
  append-only, UI surveillance, regression, dan rollback test.
- Memvalidasi 225 test pada Python 3.13.15 dengan branch coverage 87%; binary,
  installer, data-lifecycle drill, health smoke, dan manifest lokal lulus.

## 0.24.0 - Limited Production Rollout & Operational Guardrails

- Menambahkan rollout terbatas yang hanya dapat dibuat dari acceptance `GO`
  yang masih berlaku dan terikat pada versi/schema aplikasi aktif.
- Membatasi scope berdasarkan maksimum workstation dan wave berurutan; hanya
  satu wave dapat aktif pada satu waktu.
- Menambahkan pause, resume, emergency halt, pencatatan insiden, dan `AUTO_HALT`
  saat ambang total/CRITICAL tercapai atau binding release kedaluwarsa.
- Menyimpan ringkasan insiden sebagai SHA-256 tanpa identitas pasien; severity
  dan jumlah workstation terdampak tetap tersedia untuk audit operasional.
- Mewajibkan attestation closeout klinis dan teknis yang berbeda, kemudian
  keputusan `COMPLETE` oleh Direktur/Super Admin independen; `ROLLBACK` tersedia
  sebagai jalur fail-safe pada seluruh status non-final.
- Menambahkan ledger operasional append-only, trigger immutable, migrasi
  `0020_limited_rollout`, UI Limited Rollout, regression dan rollback test.
- Memvalidasi 218 test pada Python 3.13.15 dengan branch coverage 87%; binary,
  installer, data-lifecycle drill, health smoke, dan manifest lokal lulus.

## 0.23.0 - Go-Live Readiness & Acceptance Evidence

- Menambahkan sesi go-live acceptance yang terikat pada versi aplikasi, schema,
  checksum `release-qualification.json`, dan checksum installer final.
- Menyediakan delapan checklist clean-host, preservasi ProgramData, rollback,
  Authenticode/waiver, UAT klinis, alert-fatigue, serta SOP/pelatihan.
- Mewajibkan file bukti ber-checksum untuk setiap PASS; perubahan evidence
  mencabut attestation fungsi terkait secara fail-safe.
- Mewajibkan attestation klinis dan teknis oleh pengguna berbeda serta keputusan
  GO oleh Direktur/Super Admin yang independen dari kedua attestor.
- Mencatat GO maupun NO-GO pada ledger SHA-256 append-only dan audit utama;
  expiry, perubahan versi/schema, atau kerusakan ledger selalu menahan GO.
- Menambahkan migrasi `0019_go_live_acceptance`, trigger immutable, UI go-live
  readiness, rollback test, dan data-lifecycle drill dari schema 0018.
- Menambahkan gate Authenticode opsional fail-closed melalui
  `EMSS_REQUIRE_SIGNATURE=1`; kebijakan unsigned tetap tercatat eksplisit.
- Memvalidasi regresi akhir: 212 test lulus dengan branch coverage 87%; binary,
  installer, data-lifecycle drill, dan manifest release lulus gate lokal.

## 0.22.0 - Release Qualification & Deployment Evidence

- Menambahkan release preflight fail-closed untuk Python 3.13 64-bit,
  PyInstaller, Inno Setup 6, konsistensi versi, dan satu Alembic head.
- Menghasilkan laporan JSON mesin-baca dengan status `QUALIFIED`, `BLOCKED`,
  atau `FAILED`; toolchain yang tidak tersedia tidak pernah dianggap lulus.
- Memverifikasi struktur ONEDIR, menolak symlink/berkas kunci, dan menghitung
  SHA-256 setiap file binary serta installer sebagai manifest distribusi.
- Menjalankan health smoke pada executable dengan konfigurasi dan database
  sementara sampai state `READY` dan schema revision sesuai.
- Menambahkan drill data-lifecycle terotomasi: backup/integrity, upgrade dari
  0017, restore dan forward migration, rollback, upgrade ulang, health, serta
  validasi audit chain.
- Mengintegrasikan preflight, regression/coverage, drill, PyInstaller smoke,
  dan qualification installer ke skrip build; setiap kegagalan menghentikan
  distribusi artefak.
- Memvalidasi regresi akhir: 199 test lulus dengan branch coverage 87%; binary,
  installer, dan data-lifecycle drill lulus gate mesin-baca.

## 0.21.0 - Evidence Verification & Chain of Custody

- Menambahkan verifikasi zero-trust paket bukti sesi pilot dari byte snapshot,
  termasuk format manifest, checksum file, rantai ledger, head hash, dan jumlah
  ledger/closeout.
- Menolak ZIP dengan entry tak dikenal/duplikat, path traversal, symlink,
  enkripsi, ukuran berlebih, atau rasio kompresi mencurigakan sebelum ekstraksi.
- Mencatat setiap hasil valid maupun invalid sebagai chain-of-custody append-only
  dengan kode error terkontrol serta event pada audit chain utama.
- Menambahkan migrasi `0018_evidence_verification` dan trigger database yang
  menolak UPDATE/DELETE pada riwayat verifikasi.
- Menambahkan UI pemilihan paket dan riwayat pemeriksaan tanpa mempercayai atau
  menampilkan metadata bebas dari arsip yang tidak valid.
- Menjaga kompatibilitas paket format `EMSS_PILOT_EVIDENCE_V1` lintas versi;
  versi aplikasi dan schema asal dicatat sebagai provenance.
- Memvalidasi regresi akhir: 183 test lulus dengan branch coverage 87%.

## 0.20.0 - Pilot Evidence Export & Ledger Integrity Quarantine

- Memverifikasi rantai ledger pada setiap evaluasi runtime Advisory Pilot dan
  mencabut aktivasi secara fail-safe bila integritas tidak valid.
- Menambahkan karantina ledger persisten yang menahan alert dan aktivasi baru;
  hanya IT Admin/Super Admin dapat membukanya setelah rantai kembali valid.
- Mencatat closeout forensik serta audit insiden tanpa menambahkan event baru ke
  rantai yang sudah tidak dapat dipercaya.
- Menambahkan ekspor ZIP bukti sesi pilot berisi manifest, ledger CSV, closeout
  CSV, checksum setiap file, head hash, versi aplikasi, dan schema revision.
- Memastikan paket bukti tidak memuat nama pasien, nomor rekam medis, nomor
  resep, pesan alert, atau catatan klinis bebas.
- Menambahkan migrasi `0017_pilot_ledger_quarantine`, UI ekspor/pemulihan,
  regression test tamper-recovery, dan rollback test kompatibilitas.
- Memvalidasi regresi akhir: 179 test lulus dengan branch coverage 87%.

## 0.19.0 - Shift Closeout & Pilot Session Ledger

- Menambahkan closeout shift oleh pemilik klinis aktif dengan catatan
  attestation wajib dan snapshot agregat alert/intervensi yang belum selesai.
- Memperketat handover menjadi tiga tahap: incoming attestation, outgoing
  attestation oleh pemilik shift lama, lalu pengesahan IT/Super Admin.
- Membatasi masa tugas pemilik shift maksimal 12 jam dan tidak pernah melewati
  expiry aktivasi; shift atau aktivasi kedaluwarsa dicabut secara fail-safe.
- Menambahkan ledger sesi pilot append-only berantai SHA-256, audit untuk setiap
  event, serta trigger database yang menolak UPDATE/DELETE ledger dan closeout.
- Menambahkan migrasi `0016_shift_closeout_ledger` yang backfill-safe, pengujian
  upgrade/downgrade/upgrade, UI closeout/handover, dan dokumentasi operasional.
- Memvalidasi regresi akhir: 176 test lulus dengan branch coverage 87%.

## 0.18.0 - Two-Person Authorization & Shift Handover

- Mengganti aktivasi satu pengguna dengan permintaan IT dan persetujuan kedua
  oleh Apoteker/KFT/Clinical Reviewer yang wajib memakai akun berbeda.
- Membatasi permintaan otorisasi selama 30 menit dan membatalkannya jika gate,
  kampanye, sesi UAT, atau timestamp sign-off berubah sebelum persetujuan.
- Menetapkan pemilik shift klinis pada setiap aktivasi dan menyediakan handover
  dua langkah: petugas pengganti mengajukan, lalu IT mengesahkan.
- Mempertahankan aktivasi lama selama handover menunggu; setelah disahkan,
  aktivasi lama dicabut atomik dan kepemilikan shift berpindah.
- Membatalkan seluruh permintaan tertunda ketika emergency stop dipicu.
- Memvalidasi regresi akhir: 171 test lulus dengan branch coverage 87%.

## 0.17.0 - Time-Bounded Authorization & Emergency Stop

- Membatasi aktivasi Advisory Pilot menjadi 4, 8, 12, 24, 72, atau 168 jam
  dan menahan alert secara otomatis setelah otorisasi kedaluwarsa.
- Menambahkan emergency-stop latch persisten yang dapat dipicu oleh peran
  klinis/IT dengan alasan wajib dan tetap aktif setelah restart aplikasi.
- Membatasi pembukaan latch kepada IT Admin/Super Admin dan tetap mewajibkan
  aktivasi ulang setelah emergency stop dibuka.
- Membedakan alasan penahanan runtime untuk aktivasi kedaluwarsa, emergency
  stop, gate gagal, dan aktivasi yang belum diberikan.
- Memvalidasi regresi akhir: 169 test lulus dengan branch coverage 87%.

## 0.16.0 - Controlled Advisory Pilot Activation

- Memisahkan kelulusan gate dari aktivasi operasional Advisory Pilot yang
  harus dilakukan secara eksplisit oleh IT Admin atau Super Admin.
- Mengikat aktivasi ke versi aplikasi, kampanye validasi, sesi UAT, serta
  timestamp kedua sign-off yang berlaku saat aktivasi.
- Mencabut aktivasi secara fail-safe bila gate atau ikatan bukti berubah dan
  mewajibkan aktivasi ulang setelah revalidasi.
- Menyediakan kontrol aktivasi/nonaktivasi di UI dan audit berantai-hash untuk
  setiap transisi manual maupun otomatis.
- Memvalidasi regresi akhir: 165 test lulus dengan branch coverage 87%.

## 0.15.0 - Campaign-Bound UAT Sign-off

- Mengikat sign-off Apoteker dan IT ke kampanye validasi klinis terbaru.
- Menolak persetujuan lama setelah workbook validasi baru diimpor, meskipun
  versi aplikasi belum berubah.
- Mencegah sign-off terhadap kampanye yang provenance aplikasinya, screening
  engine, knowledge base, atau kebijakan keselamatannya sudah tidak sesuai.
- Menyimpan ID kampanye dan checksum sumber pada audit persetujuan.
- Memvalidasi regresi akhir: 162 test lulus dengan branch coverage 87%.

## 0.14.0 - Clinical Validation Campaign Provenance

- Mengikat kampanye validasi klinis ke versi aplikasi, screening engine,
  knowledge base yang diuji, dan fingerprint kebijakan keselamatan obat.
- Mensyaratkan knowledge base tervalidasi yang sama telah `PUBLISHED` sebelum
  gate Advisory dapat terbuka.
- Menutup gate secara fail-safe ketika aplikasi, engine, knowledge base, atau
  kebijakan keselamatan berubah setelah workbook validasi diimpor.
- Menolak kampanye legacy tanpa provenance dan mewajibkan impor validasi ulang.
- Memvalidasi regresi akhir: 160 test lulus dengan branch coverage 87%.

## 0.13.0 - Version-Bound UAT Sign-off

- Mengikat persetujuan Apoteker dan IT ke versi aplikasi yang sedang berjalan.
- Menolak sign-off legacy, tanpa metadata versi, atau dari versi aplikasi lama
  sebelum gate Advisory dapat terbuka.
- Menyimpan versi aplikasi pada audit persetujuan dan membersihkannya saat
  bukti terkait berubah.
- Menyelaraskan versi runtime Python, metadata paket, installer, dan changelog.
- Memvalidasi regresi akhir: 158 test lulus dengan branch coverage 87%.

## 0.12.4 - UAT Approval Freshness Gate

- Memverifikasi identitas dan waktu sign-off saat setiap evaluasi gate, bukan
  hanya mempercayai flag persetujuan yang tersimpan.
- Menolak persetujuan yang lebih lama daripada bukti pengujian terbaru atau
  tidak memiliki metadata approver lengkap.
- Menampilkan blocker khusus untuk data persetujuan lama/inkonsisten dan tetap
  mewajibkan sign-off ulang sebelum Advisory Pilot aktif.
- Memvalidasi regresi akhir: 156 test lulus dengan branch coverage 87%.

## 0.12.3 - UAT Approval Revocation

- Mencabut persetujuan Apoteker atau IT secara otomatis ketika status, hasil,
  bukti, atau identitas penguji pada checklist miliknya berubah.
- Membersihkan identitas dan waktu persetujuan lama agar bukti yang diubah
  wajib ditandatangani ulang sebelum gate Advisory dapat terbuka kembali.
- Mencatat pencabutan pada audit berantai dengan kode item dan alasan, tanpa
  menyimpan isi bukti UAT di detail audit.
- Memvalidasi regresi akhir: 155 test lulus dengan branch coverage 87%.

## 0.12.2 - Advisory Alert Suppression Persistence

- Menyimpan status `SUPPRESSED` saat alert ditahan oleh Silent Pilot, gate
  Advisory yang belum lulus, atau kegagalan evaluasi gate.
- Mencegah alert lama tampil kemudian akibat sinyal skrining berulang setelah
  gate berubah menjadi siap.
- Mencatat alasan penahanan alert pada audit berantai tanpa menyimpan identitas
  pasien di detail audit.
- Memvalidasi regresi akhir: 154 test lulus dengan branch coverage 87%.

## 0.12.1 - Advisory Runtime Gate Revalidation

- Memeriksa ulang gate sebelum setiap alert Advisory Pilot, bukan hanya saat
  aplikasi dibuka.
- Menahan alert secara fail-safe bila status gate berubah atau evaluasi gate
  gagal, sambil tetap menyimpan hasil skrining dan memperbarui ringkasan.
- Memperbarui banner Advisory agar mengikuti status gate terbaru.

## 0.12.0 - Advisory Pilot Gate Enforcement

- Menonaktifkan alert operasional bila `advisory_pilot` dipilih sebelum gate
  validasi klinis dan UAT lulus, sambil tetap menyimpan hasil skrining.
- Menampilkan banner yang membedakan advisory terkunci dan advisory siap.

## 0.11.0 - Pilot Monitoring & Alert Fatigue Evidence

- Menambahkan tab **Monitoring Pilot** pada Validasi Klinis & UAT dengan
  periode 7, 30, 90 hari, atau satu tahun.
- Menghitung resep non-MOCK, CRITICAL/HIGH_RISK, alert per 100 resep,
  acknowledgement rate, median waktu respons, CRITICAL yang belum diakui,
  penyelesaian intervensi, dan acceptance rate.
- Menambahkan ekspor CSV agregat tanpa nomor resep, nomor RM, nama pasien,
  dokter, atau identitas klinis lainnya; ekspor dicatat pada audit.
- Monitoring tidak mengubah environment dan tidak dapat membuka gate advisory.
- Memvalidasi regresi akhir: 150 test lulus dengan branch coverage 87%.

## 0.10.2 - DDI Checker Brand Alignment

- Mengadaptasi logo pilihan pemilik produk menjadi ikon kapsul, centang, dan
  bingkai pemindai yang tebal serta terbaca pada ukuran taskbar/system tray.
- Menyelaraskan identitas **e-MSS Farmasi — DDI Checker** pada title bar,
  halaman login, header utama, menu tray, tooltip, dan alert fullscreen.
- Mempertahankan nama executable serta identitas instalasi lama agar shortcut
  dan konfigurasi workstation yang sudah ada tetap kompatibel.
- Memvalidasi regresi akhir: 148 test lulus dengan branch coverage 87%.

## 0.10.1 - Ready for Clinical Validation

- Mengganti identitas visual dengan ikon kapsul–medis–sirkuit yang lebih tebal,
  memenuhi bidang ikon, dan tetap terbaca pada ukuran taskbar/system tray.
- Membuat ICO multi-resolusi 16–256 piksel serta PNG khusus taskbar dan tray.
- Menambahkan notifikasi in-app top-most yang tidak mencuri fokus dan tetap
  terlihat di atas aplikasi fullscreen, sebagai pendamping balloon Windows.
- Membedakan warna CRITICAL/ERROR, persistent, dan review; klik notifikasi
  langsung membuka tab **Antrean & Alert**.
- Silent pilot tetap menonaktifkan seluruh notifikasi operasional.
- Menambahkan tombol uji alert tertunda tiga detik pada development/test tanpa
  membuat resep atau menyimpan data pasien.
- Memvalidasi regresi akhir: 148 test lulus dengan branch coverage 87%.

## 0.10.0 - Ready for Clinical Validation

- Menambahkan schema `0009_sprint10` untuk kampanye validasi klinis, kasus
  expected-vs-actual, checklist UAT, serta sign-off apoteker dan IT.
- Menambahkan menu **Validasi Klinis & UAT**, import hasil, perhitungan match
  oleh aplikasi, gate advisory pilot, dan daftar blocker eksplisit.
- Menambahkan template Excel validasi klinis sintetis dan UAT dengan petunjuk,
  codebook, pembatasan kategori, serta peringatan privasi.
- Menambahkan `silent_pilot` yang menyimpan hasil screening tanpa memanggil
  notifikasi tray/popup dan menyembunyikan antrean/intervensi dari pengguna
  farmasi rutin.
- Menambahkan konfigurasi serta launcher silent pilot lokal tanpa menyimpan
  password MySQL.
- Mempertahankan integrasi Khanza read-only dan melarang perubahan mode otomatis
  setelah evaluasi gate.
- Memvalidasi 147 test dengan branch coverage 87%; status tetap Ready for
  Clinical Validation sampai UAT dan silent pilot rumah sakit selesai.

## 0.9.0 - Development

- Mengimpor 22 pasangan DDI tambahan ke versi DRAFT tanpa menduplikasi pasangan
  yang sudah ada; total master menjadi 5.432 rule.
- Menambahkan export Excel lengkap untuk master DDI beserta sheet impor ulang
  DRAFT, arsip seluruh field, zat aktif, mapping Khanza, codebook, checksum,
  kontrol role, audit ekspor, dan perlindungan formula injection.
- Menambahkan backup manual dan harian, manifest SHA-256, snapshot konfigurasi
  nonsensitif, verifikasi integritas/schema, riwayat, dan retensi.
- Menambahkan restore fail-safe dengan safety backup otomatis, rollback saat
  gagal, audit, penghentian polling, serta restart wajib setelah berhasil.
- Menambahkan tab admin **Backup & Restore** dan perintah CLI terkait.
- Menambahkan definisi PyInstaller ONEDIR, konfigurasi produksi, dan installer
  Inno Setup x64 yang mempertahankan data di ProgramData.
- Memvalidasi seluruh regresi (144 test) dan latihan restore terhadap salinan
  database 5.432 rule tanpa menyentuh database aktif.

## 0.8.0 - Development

- Menambahkan schema `0008_sprint8` untuk kebijakan polifarmasi, profil kelas
  terapi, master high-alert per unit, pasangan LASA, dan severity issue.
- Mendeteksi duplikasi zat aktif pada item berbeda serta duplikasi kelas terapi
  yang memerlukan review klinis.
- Menghitung polifarmasi dari zat aktif unik dengan default 5 dan
  hiperpolifarmasi 10; ambang dapat divalidasi ulang oleh administrator.
- Menambahkan master high-alert dan LASA yang hanya aktif setelah dikonfigurasi
  berdasarkan kebijakan rumah sakit.
- Memasukkan sidik konfigurasi keselamatan ke identitas skrining agar perubahan
  kebijakan menghasilkan revisi baru, bukan memakai ulang hasil lama.
- Menambahkan tab **Keselamatan Obat**, audit perubahan master, severity pada
  detail antrean, serta agregat Sprint 8 pada dashboard dan laporan CSV.
- Memperbaiki seluruh permukaan scroll dashboard agar eksplisit memakai tema
  terang pada Windows dengan palet gelap.

## 0.7.0 - Development

- Menetapkan panjang password minimal 6 karakter sesuai keputusan pemilik
  produk; password sangat umum, username di dalam password, dan password lebih
  dari 128 karakter tetap ditolak.
- Menetapkan tema terang eksplisit untuk editor teks multi-baris, menu utama,
  popup, tooltip, spinbox, dan kontrol input agar tidak mengikuti palet gelap
  Windows secara tidak terbaca.
- Merombak dashboard manajemen dengan filter bulanan, triwulanan, tahunan, dan
  seluruh data; perbandingan periode; persentase risiko; indikator tindak
  lanjut; tren 12 bulan; serta agregat per unit/depo.
- Menambahkan schema `0007_sprint7` untuk intervensi apoteker dan detail
  temuan klinis.
- Menambahkan formulir intervensi dari antrean dengan identitas apoteker,
  keputusan, komunikasi, hasil, alasan terapi diteruskan, dan status selesai.
- Mewajibkan dokumentasi lengkap untuk HIGH_RISK/CRITICAL dan mencegah review
  sederhana menggantikan intervensi klinis.
- Menambahkan audit klinis intervensi, dashboard agregat tanpa identitas
  pasien, metrik acceptance rate, serta ekspor CSV yang diaudit.
- Menambahkan tab **Intervensi Apoteker**, **Dashboard & Laporan**, dan menu
  **Akun → Ganti Password Admin**.
- Memperbaiki kontras dialog detail DDI, indikator dropdown, serta feedback
  visual tombol saat ditekan/fokus.

## 0.6.0 - Development

- Menambahkan identitas visual e-MSS Farmasi berupa kapsul/e, simbol medis,
  dan sirkuit digital pada ikon jendela serta system tray.
- Memperbaiki kontras warna menu system tray untuk tema Windows gelap/terang.
- Menambahkan kontrak adapter Khanza dan implementasi mock/MySQL berbasis view.
- Memaksa session MySQL read-only dan hanya menyediakan query SELECT
  parameterized dengan timeout, `pool_pre_ping`, `LIMIT`, dan keyset cursor.
- Menambahkan polling worker non-GUI, stability fingerprint, deteksi revisi,
  reconnect eksponensial, serta histori polling lokal.
- Menambahkan status fail-safe `INCOMPLETE`, `ERROR`, dan `DISCONNECTED` yang
  tidak pernah disamarkan sebagai `SAFE`.
- Menambahkan panel **Integrasi Khanza** dan simulasi end-to-end melalui adapter.
- Menambahkan schema `0006_sprint6` untuk `integration_state` dan `polling_run`.

## 0.5.0 - Development

- Menambahkan processing queue, filter depo/status, detail hasil, retry manual,
  dan dead-letter queue.
- Menambahkan alert router per resep untuk SAFE, INFO, REVIEW, HIGH_RISK,
  CRITICAL, NOT_ASSESSED, UNMAPPED, INCOMPLETE, dan ERROR.
- Menambahkan HOLD RECOMMENDED untuk CRITICAL tanpa memblokir atau menulis ke
  Khanza.
- Menambahkan panel **Antrean & Alert**, system tray, minimize-to-tray, dan
  pemulihan panel.
- Menambahkan tombol pengujian langsung **Simulasikan CRITICAL** pada antrean.
- Menambahkan single-instance guard untuk mencegah worker dan ikon tray ganda.
- Menambahkan Mode Farmasi tanpa password dengan fungsi perubahan master tetap
  terkunci.
- Menambahkan skrip install/remove autostart Windows.
- Memperkuat timestamp rantai audit agar selalu monoton pada event cepat.
- Menambahkan schema `0005_sprint5` untuk `processing_queue` dan `alert_event`.

## 0.4.0 - Development

- Menambahkan DDI engine dengan canonical pair dan satu batch query per resep.
- Menambahkan prescription hash, reuse idempoten, revision detection, serta
  riwayat hasil skrining yang tidak ditimpa.
- Menambahkan dukungan komponen obat kombinasi/racikan tanpa membandingkan
  komponen dalam item yang sama.
- Memisahkan status risiko dari kelengkapan asesmen.
- Mempertahankan quick-closure, NOT_ASSESSABLE, EXCLUDED, dan rule yang tidak
  ditemukan sebagai `PAIR_NOT_ASSESSED`, bukan SAFE.
- Menambahkan simulator resep **MODE MOCK** yang hanya aktif pada
  development/test.
- Menambahkan schema `0004_sprint4` untuk resep, revisi, hasil, pair, dan issue.
- Menambahkan perubahan password mandiri dari UI dengan verifikasi password
  saat ini dan audit tanpa menyimpan isi password.

## 0.3.0 - Development

- Menambahkan master DDI dengan canonical pair dan constraint unik per versi.
- Menambahkan importer XLSX/CSV untuk workbook sumber dan template DDI.
- Menambahkan backup otomatis sebelum commit impor DDI.
- Menambahkan input DDI langsung dan pembaruan draft melalui form.
- Menambahkan versioning, duplikasi versi, review, approval, publication,
  retirement, rollback, serta audit transisi.
- Menambahkan UI Knowledge Base, Master DDI, Import DDI, dan template unduhan.
- Memuat `DDI-KHANZA-v1.0.0` sebagai DRAFT: 5.410 rule, 164 HOLD, 0 aktif.

## 0.2.0 - Development

- Menambahkan skema master obat, alias, bahan aktif, komponen mapping, batch
  impor, dan staging.
- Menambahkan pembaca XLSX/CSV lokal yang hanya-baca, dengan pembatasan ukuran,
  perlindungan ZIP/XML, dan penolakan formula pada data impor.
- Menambahkan validasi lintas-sheet, preview persisten, commit transaksional,
  serta persetujuan mapping sebagai langkah terpisah.
- Menambahkan UI pencarian master obat, status review, impor, dan persetujuan
  batch sesuai role.
- Memvalidasi workbook awal DDI-KHANZA v1.0.0 tanpa mengubah berkas sumber.

## 0.1.0 - Development

- Membuat skeleton aplikasi Sprint 1.
- Menambahkan konfigurasi, database SQLite, Alembic, pengguna, role, audit,
  health check, CLI, dan UI login dasar.

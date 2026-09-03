# e-MSS Farmasi — DDI Checker

Electronic Medication Safety System (e-MSS) adalah aplikasi desktop Windows
yang berjalan berdampingan dengan SIMRS Khanza. Khanza tetap menjadi sistem
utama. e-MSS mempunyai database lokal sendiri dan, pada sprint integrasi,
hanya akan membaca database Khanza menggunakan akun `SELECT` saja.

## Status

`0.31.1 — hotfix startup QtCore untuk UAT lokal; bukan Production Ready`

Installer 0.31.0 ditarik karena DLL ICU asing menyebabkan GUI gagal dibuka.
Rilis 0.31.1 memakai ICU Windows, mengarantina DLL lama hanya jika hash cocok,
dan mewajibkan smoke test login GUI frozen. Lihat `docs/HOTFIX_QTCORE_0.31.1.md`.

Head: `0027_durable_monitor`. Monitor otomatis setelah enable dan persetujuan
polling internal, lane terkini/histori, retry persisten, peristiwa validasi,
popup per hasil, audio lokal, serta sinkronisasi master/workbook mapping.
Default consent tetap false; konfigurasi RS tidak diubah. Kontrak item FINAL,
persetujuan klinis dan izin bundling audio masih terbuka. Pengguna telah menyetujui
polling internal 3 detik untuk UAT lokal (docs/POLLING_CONSENT_20260827.md);
config RS dan default installer tetap tidak diubah.
Panduan: `docs/UAT_LOCAL_031_20260827.md`; status tiap kebutuhan:
`docs/BACKLOG_STATUS_031_20260827.md`; bukti angka terbaru:
`docs/TEST_REPORT_031_20260827.md`.

Versi 0.30.0 membundel 5.432 DDI pairs dan 159 zat aktif dari master
`DDI-KHANZA-v1.0.0`. Pada database baru, seed diterapkan setelah administrator
pertama dibuat. Seed hanya berjalan bila master DDI kosong, tidak pernah
menimpa master yang sudah ada, tidak membawa akun/resep/identitas pasien, dan
tetap `DRAFT`/nonaktif sampai workflow klinis diselesaikan. Input manual,
template, preview/import, export, dan workflow knowledge base tetap tersedia.
Panduan: `docs/SPRINT_23_BUNDLED_DDI_MASTER.md`.

Sprint 22 menambahkan **UAT Execution & Independent Acceptance**: sepuluh
scenario wajib, result attempt append-only, issue/remediasi ber-hash, dual
sign-off independen, keputusan pihak ketiga, revocation/expiry, dan receipt
yang tidak memberikan production authorization. Panduan:
`docs/SPRINT_22_UAT_EXECUTION_ACCEPTANCE.md`.

Sprint 21 menambahkan **UAT Release-Candidate Dossier** yang mengikat
qualification/installer, readiness evidence eksternal, attestation independen,
ledger immutable, serta kit dengan status awal `NOT_STARTED`/`NOT_RECORDED`.
Panduan: `docs/SPRINT_21_UAT_RELEASE_CANDIDATE_DOSSIER.md`.

Sprint 20 menambahkan **Verified Production Evidence Package & Manual
Deployment Ceremony**. Paket ZIP diverifikasi aman dan diikat ke checksum
evidence Sprint 19, hasil verifikasi disimpan append-only, dan hasil terbaru
yang invalid menutup gate. Ceremony membutuhkan attestation teknis dan klinis
independen di dalam deployment window sebelum keputusan produksi pihak ketiga.
Authorization receipt hanya merekam keputusan dan selalu menyatakan deployment
tidak dilakukan oleh e-MSS. Panduan:
`docs/SPRINT_20_VERIFIED_EVIDENCE_CEREMONY.md`.

Sprint 19 menambahkan **Production Release Record & Deployment Authorization**
yang fail-closed: intake evidence Authenticode/waiver, clean-host, preservasi
data, rollback/restore, change approval, deployment window, keputusan
independen, expiry, revocation, emergency rollback order, dan ledger immutable.
Fitur ini tidak menjalankan deployment atau rollback otomatis. Bukti dan
persetujuan rumah sakit aktual belum tersedia dan tidak disimulasikan sebagai
bukti produksi. Panduan: `docs/SPRINT_19_PRODUCTION_RELEASE_AUTHORIZATION.md`.
Hasil verifikasi lokal tersedia di `docs/TEST_REPORT_SPRINT_19.md`.

Sprint 18 menambahkan **Early-Life Surveillance** dengan snapshot agregat
non-MOCK, freshness gate, remediasi isu ber-hash, ledger immutable, serta
keputusan PROMOTE/ROLLBACK tiga pihak. Promotion adalah bukti keputusan dan tidak
mengubah konfigurasi produksi secara otomatis. Panduan:
`docs/SPRINT_18_EARLY_LIFE_SURVEILLANCE.md`.

Sprint 17 menambahkan **Limited Rollout** yang terikat acceptance GO, scope dan
wave terbatas, pause/emergency halt, auto-halt berbasis ambang insiden, ledger
operasional immutable, serta closeout tiga pihak. Fitur ini tidak mengubah
workstation atau mengaktifkan produksi secara otomatis. Panduan lengkap:
`docs/SPRINT_17_LIMITED_ROLLOUT.md`.

Sprint 10 menyediakan seluruh fondasi Sprint 1–9 serta:

- struktur proyek Python/PySide6;
- konfigurasi lokal tanpa kredensial;
- database SQLite melalui SQLAlchemy dan Alembic;
- role dan pengguna lokal;
- password Argon2id;
- audit login berantai-hash;
- health check CLI dan UI dasar;
- master obat, alias, bahan aktif, dan mapping komponen;
- impor master obat XLSX/CSV dengan preview serta validasi;
- staging sebelum commit dan persetujuan mapping secara terpisah;
- status `PENDING_REVIEW` dan `APPROVED` yang dapat ditinjau di UI.
- master DDI berbasis pasangan zat aktif kanonik;
- input DDI langsung serta impor XLSX/CSV;
- template DDI dengan codebook dan validasi input;
- knowledge base versioning;
- workflow `DRAFT → REVIEWED → APPROVED → PUBLISHED → RETIRED`;
- rollback versi, audit transisi, dan backup sebelum commit impor DDI;
- pemisahan interaksi, no-interaction, not-assessable, serta excluded.
- DDI engine dengan batch query terhadap seluruh canonical pair resep;
- prescription hash, reuse hasil identik, dan revisi saat resep berubah;
- dukungan obat kombinasi serta komponen racikan;
- status risiko dan kelengkapan asesmen sebagai dua dimensi;
- klasifikasi eksplisit `INTERACTION_FOUND`, `ASSESSED_NO_INTERACTION`,
  `PAIR_NOT_ASSESSED`, `DRUG_UNMAPPED`, dan `DATA_INCOMPLETE`;
- simulator resep berlabel **MODE MOCK** untuk development/test.
- antrean hasil skrining yang diurutkan berdasarkan prioritas dan waktu;
- filter unit/depo, status, nomor resep, RM, atau nama pasien;
- satu alert gabungan per resep dan detail pasangan/issue;
- HOLD RECOMMENDED untuk hasil CRITICAL tanpa mengubah Khanza;
- retry manual serta dead-letter queue untuk kegagalan proses;
- system tray, minimize-to-tray, dan pemulihan panel;
- single-instance agar tidak terjadi tray atau worker ganda;
- Mode Farmasi tanpa password untuk akses operasional terbatas;
- skrip pemasangan dan penghapusan autostart Windows.
- kontrak `KhanzaPrescriptionAdapter` yang tidak mengasumsikan tabel lokal;
- `MockKhanzaAdapter` dan `MySQLKhanzaAdapter` berbasis empat view integrasi;
- session MySQL read-only, query parameterized, timeout, `pool_pre_ping`,
  pagination `LIMIT`, dan cursor `(changed_at, no_resep)`;
- polling resep otomatis pada worker non-GUI;
- pembacaan ulang dan fingerprint untuk memastikan resep stabil;
- status `INCOMPLETE` untuk snapshot yang terus berubah;
- status koneksi, reconnect eksponensial, serta histori setiap polling;
- panel **Integrasi Khanza** dengan polling manual/otomatis dan simulasi adapter.
- formulir intervensi apoteker yang terhubung ke resep pada antrean;
- validasi wajib untuk HIGH_RISK/CRITICAL dan alasan terapi diteruskan;
- status intervensi belum selesai/selesai serta snapshot temuan klinis;
- audit klinis intervensi dalam rantai audit lokal;
- dashboard agregat tanpa identitas pasien;
- filter dashboard bulanan, triwulanan, tahunan, dan seluruh data;
- persentase risiko tinggi/CRITICAL, kelengkapan, tindak lanjut, acceptance
  rate, tren 12 bulan, dan ringkasan per unit/depo;
- ekspor laporan mutu agregat CSV dengan audit ekspor;
- menu **Akun → Ganti Password Admin**.
- deteksi duplikasi zat aktif dan kelas terapi dengan konteks rute/racikan;
- pemantauan polifarmasi berbasis zat aktif unik dengan ambang lokal 5/10;
- master high-alert per obat dan unit/depo dengan kebutuhan double-check;
- master pasangan LASA dalam enam kategori dan rekomendasi lokal;
- validasi/audit perubahan master keselamatan serta sidik konfigurasi yang
  memaksa skrining ulang setelah kebijakan berubah;
- ringkasan duplicate therapy, polifarmasi, high-alert, dan LASA pada dashboard
  serta ekspor agregat.
- backup manual dan harian melalui SQLite online-backup API;
- manifest SHA-256, pemeriksaan integritas/schema, snapshot konfigurasi tanpa
  password, riwayat, serta retensi 30 hari/30 backup;
- restore fail-safe dengan verifikasi sebelum restore, safety backup otomatis,
  rollback jika gagal, audit, dan kewajiban restart aplikasi;
- menu admin **Backup & Restore** serta perintah CLI untuk backup, verifikasi,
  daftar riwayat, dan restore;
- tombol **Export Master DDI Lengkap** yang menghasilkan workbook berisi
  ringkasan, sheet pemulihan DRAFT, arsip seluruh field, master zat aktif,
  mapping obat Khanza, codebook, serta checksum SHA-256;
- definisi build PyInstaller ONEDIR dan installer Inno Setup x64 yang tidak
  menghapus database/backup di ProgramData saat update atau uninstall.
- schema validasi klinis, kampanye kasus, checklist UAT, dan dual sign-off;
- workbook resmi validasi klinis sintetis dan UAT yang dapat diunduh;
- evaluasi gate menuju advisory pilot dengan blocker yang eksplisit;
- silent mode yang tetap memproses resep tetapi menonaktifkan alert tray/popup;
- penyembunyian antrean/intervensi bagi pengguna farmasi rutin selama silent
  pilot, sementara reviewer berwenang tetap dapat membandingkan hasil.
- ikon e-MSS baru yang memenuhi bidang taskbar/tray dan paket ICO multi-resolusi;
- kartu alert top-most tanpa mengambil fokus, sebagai pendamping notifikasi
  Windows ketika aplikasi lain berjalan fullscreen; klik membuka antrean.
- tab monitoring pilot agregat untuk resep non-MOCK dengan periode 7/30/90/365
  hari, alert per 100 resep, acknowledgement, waktu respons, intervensi, dan
  acceptance rate;
- ekspor CSV bukti pilot tanpa identitas pasien serta audit checksum.
- revalidasi gate sebelum setiap alert Advisory Pilot dan penahanan fail-safe
  bila gate berubah atau tidak dapat dievaluasi;
- status alert yang ditahan dipersistenkan serta diaudit agar sinyal skrining
  berulang tidak menampilkan alert lama setelah gate berubah.
- perubahan bukti checklist UAT otomatis mencabut sign-off pemilik item terkait
  sehingga gate tidak dapat memakai persetujuan lama setelah bukti diperbarui.
- setiap evaluasi gate memeriksa freshness timestamp dan kelengkapan identitas
  sign-off agar data legacy yang inkonsisten tetap ditolak secara fail-safe.
- sign-off UAT diikat ke versi aplikasi; upgrade aplikasi mewajibkan
  persetujuan ulang sebelum mode Advisory dapat aktif kembali.
- kampanye validasi menyimpan provenance aplikasi, screening engine, knowledge
  base, dan kebijakan keselamatan; perubahan salah satunya menutup gate.
- sign-off UAT menunjuk kampanye validasi tertentu; impor kampanye baru
  mewajibkan kedua pemilik memberi persetujuan ulang.
- kelulusan gate tidak langsung membuka alert Advisory; IT Admin/Super Admin
  harus melakukan aktivasi eksplisit yang terikat pada kampanye, sesi UAT,
  versi aplikasi, dan timestamp kedua sign-off terbaru;
- aktivasi otomatis dicabut jika gate atau bukti berubah, sehingga alert tetap
  tertahan sampai revalidasi, sign-off, dan aktivasi ulang selesai.
- aktivasi Advisory memiliki masa berlaku terpilih 4 jam sampai 7 hari;
  otorisasi kedaluwarsa menahan alert dan mewajibkan aktivasi baru.
- emergency stop persisten dapat dipicu reviewer klinis/Apoteker/KFT/IT dengan
  alasan wajib; hanya IT Admin/Super Admin yang dapat membuka latch, dan
  pembukaan latch tidak mengaktifkan Advisory secara otomatis.
- aktivasi memakai prinsip dua-orang: IT membuat permintaan 30 menit, kemudian
  Apoteker/KFT/Clinical Reviewer dengan akun berbeda menyetujui dan menjadi
  pemilik shift klinis;
- pergantian shift dilakukan melalui handover dua langkah oleh petugas klinis
  pengganti dan IT; aktivasi lama tetap berlaku sampai handover disahkan lalu
  dicabut secara atomik.
- handover shift memakai incoming attestation, outgoing attestation pemilik
  lama, dan pengesahan IT; ringkasan agregat alert/intervensi outstanding
  terikat checksum dan tidak memuat identitas pasien;
- pemilik klinis aktif dapat melakukan closeout shift eksplisit dengan catatan
  wajib; closeout mencabut aktivasi dan membatalkan permintaan yang tertunda;
- shift baru berlaku maksimal 12 jam dan tidak pernah melewati expiry aktivasi;
  expiry salah satunya menahan alert Advisory secara fail-safe;
- ledger sesi pilot append-only berantai SHA-256 merekam pembukaan shift,
  attestation, handover, dan closeout serta dilindungi dari UPDATE/DELETE.
- rantai ledger diverifikasi pada setiap evaluasi runtime Advisory; kegagalan
  integritas mencabut aktivasi, menahan alert, dan mengaktifkan karantina;
- karantina tidak dapat dibuka sampai rantai kembali valid dan hanya dapat
  dikendalikan IT Admin/Super Admin dengan referensi pemulihan yang diaudit;
- subtab Ledger menyediakan ekspor ZIP bukti tanpa PHI berisi manifest,
  ledger/closeout CSV, checksum file, dan head hash.
- release preflight memvalidasi Python 3.13 64-bit, PyInstaller, Inno Setup,
  kontrak versi, dan satu Alembic head secara fail-closed;
- manifest distribusi mencatat SHA-256 seluruh ONEDIR/installer dan menolak
  berkas kunci, symlink, atau struktur paket yang tidak lengkap;
- binary health smoke serta drill upgrade/backup/restore/rollback menghasilkan
  laporan JSON qualification yang wajib berstatus `QUALIFIED`/`PASS`.

Release gate yang masih harus dijalankan pada komputer build:

- build dan smoke test binary memakai Python 3.13 64-bit;
- kompilasi installer memakai Inno Setup 6 pada Windows bersih.
- pelaksanaan kasus validasi klinis, silent pilot, dan UAT nyata;
- persetujuan apoteker/validator klinis dan IT;
- evaluasi alert fatigue sebelum limited advisory pilot.

Runbook dan arti laporan qualification tersedia di
`docs/SPRINT_15_RELEASE_QUALIFICATION.md`.

## Validasi klinis dan UAT Sprint 10

Login memakai akun bernama lalu buka **Validasi Klinis & UAT**. Unduh template,
gunakan hanya kasus sintetis/anonim, isi expected result sebelum pengujian,
kemudian isi actual result serta reviewer. Import hasil dan selesaikan checklist
UAT. Aplikasi menghitung gate; import tidak mengubah mode maupun mempublikasikan
master DDI.

Untuk pengujian tanpa alert operasional, tutup aplikasi development lalu jalankan
`scripts\run_silent_local.bat`. Panduan lengkap ada di
`docs/SPRINT_10_CLINICAL_VALIDATION_UAT.md`.

## Closeout shift dan ledger sesi pilot

Pada tab **Validasi Klinis, UAT & Gate Pilot**, subtab **Ledger Sesi Pilot**
menampilkan urutan event, waktu, aktivasi, aktor, dan hash. Petugas incoming
memulai **Ambil Alih Shift Klinis**; pemilik shift lama memeriksa ringkasan lalu
memilih **Attestasi Outgoing Shift**; IT/Super Admin menyelesaikan dengan
**Sahkan Handover IT**. Pemilik shift juga dapat memilih **Tutup Shift Klinis**
untuk closeout tanpa pengganti.

Panduan peran, attestation, fail-safe, privasi snapshot, dan rollback tersedia
di `docs/SPRINT_12_SHIFT_CLOSEOUT_LEDGER.md`.

## Bukti sesi pilot dan karantina integritas

Gunakan **Ekspor Paket Bukti** pada subtab **Ledger Sesi Pilot** untuk membuat
arsip ZIP yang dapat diverifikasi tanpa menyalin identitas pasien. Bila rantai
ledger rusak, aplikasi mengaktifkan karantina dan menahan Advisory. Pulihkan
backup yang telah diverifikasi terlebih dahulu; setelah rantai valid, IT/Super
Admin memakai **Buka Karantina Ledger** dan memasukkan referensi insiden.
Aktivasi Advisory baru tetap wajib setelah pemulihan.

Panduan respons insiden, isi paket, checksum, dan rollback tersedia di
`docs/SPRINT_13_PILOT_EVIDENCE_INTEGRITY.md`.

## Verifikasi bukti dan chain of custody

Gunakan **Verifikasi Paket Bukti** untuk memeriksa arsip ZIP dari media atau
workstation lain. Aplikasi menghitung checksum dari snapshot byte, menolak
struktur ZIP berbahaya sebelum membaca isinya, menghitung ulang rantai ledger,
dan mencocokkan manifest. Hasil `VALID` maupun `INVALID` selalu ditambahkan ke
riwayat immutable; hanya nama file lokal dan kode error terkontrol yang dicatat.

Status `VALID` membuktikan konsistensi internal paket terhadap checksum dan
rantai SHA-256. Status ini bukan tanda tangan digital dan tidak menggantikan
kontrol akses, media transfer resmi, atau pencatatan checksum pada saat serah
terima. Prosedur lengkap dan batasan kepercayaan tersedia di
`docs/SPRINT_14_EVIDENCE_VERIFICATION.md`.

## Persyaratan

- Windows 64-bit yang masih didukung;
- Python 3.13 64-bit;
- virtual environment;
- dependency dalam `requirements.lock`.

Runtime pengembangan sementara di workspace Codex menggunakan Python 3.12
untuk menjalankan test awal. Verifikasi penuh Python 3.13 merupakan release
gate sebelum build.

## Menjalankan mode pengembangan

```powershell
cd emss-farmasi
py -3.13 -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[test]"
```

Setelah dependency terpasang, gunakan `scripts\run_dev.bat`.

Inisialisasi database pengembangan:

```powershell
scripts\run_dev.bat --config config.example.toml init-db
```

Buat administrator pertama. Password diminta secara tersembunyi dan tidak
diterima sebagai argumen command line:

```powershell
scripts\run_dev.bat --config config.example.toml create-admin
```

Health check:

```powershell
scripts\run_dev.bat --config config.example.toml health
```

UI:

```powershell
scripts\run_dev.bat --config config.example.toml gui
```

## Mengubah password

Administrator dapat membuka **Akun → Ganti Password Admin** atau memakai
tombol **Ganti Password Admin** di kanan nama pengguna. Pengguna bernama lain
dapat memakai menu **Akun → Ubah Password**. Masukkan password saat ini,
password baru minimal 6 karakter, lalu ulangi password baru. Password yang
sangat umum tetap ditolak.
Perubahan dicatat pada audit tanpa menyimpan isi password.

## Memasukkan master obat DDI

1. Login menggunakan role `SUPER_ADMIN`, `KNOWLEDGE_ADMIN`, atau
   `CLINICAL_REVIEWER`.
2. Buka tab **Import** lalu pilih workbook sumber.
3. Klik **Validasi & Preview**. Tinjau jumlah valid/invalid serta semua pesan.
4. Bila tidak ada baris invalid, klik **Commit ke Master**.
5. Buka tab **Master Obat & Mapping** dan tinjau hasil yang masih
   `PENDING_REVIEW`.
6. Kembali ke tab **Import**, pilih batch, lalu klik **Setujui Batch** hanya
   setelah validasi klinis selesai.

Preview tidak mengubah master. Commit tidak langsung mengaktifkan mapping.
Workbook sumber dibuka hanya-baca dan tidak dimodifikasi. Petunjuk lengkap ada
di `docs/DRUG_MAPPING_IMPORT_GUIDE.md`.

## Mengelola master DDI

Workbook awal dan 22 pasangan tambahan telah dimuat sebagai versi
`DDI-KHANZA-v1.0.0` berstatus `DRAFT`. Totalnya 5.432 rule tanpa pasangan
duplikat; 174 HOLD belum selesai dan satu sudah selesai. Tidak ada rule aktif.
Buka tab **Knowledge Base & Master DDI** untuk meninjau pasangan dan status
klinis sebelum versi dapat bergerak ke `REVIEWED`.

Untuk data tambahan, gunakan **Unduh Template DDI** pada tab **Import DDI**,
kemudian jalankan preview dan simpan sebagai draft. Petunjuk lengkap ada di
`docs/DDI_KNOWLEDGE_BASE_GUIDE.md`.

Untuk mempelajari atau mencadangkan konten master dalam Excel, klik **Export
Master DDI Lengkap** pada tab **Import DDI**. Sheet `DDI_IMPORT` dapat dipakai
untuk pemulihan konten melalui preview dan selalu kembali sebagai DRAFT;
`DDI_EXPORT_LENGKAP` mempertahankan seluruh field aplikasi untuk audit. Restore
operasional penuh tetap menggunakan backup SQLite. Petunjuk ada di
`docs/DDI_EXPORT_LENGKAP_GUIDE.md`.

## Menguji DDI engine

1. Jalankan UI pada environment `development`.
2. Login sebagai pengguna lokal.
3. Buka tab **Simulator DDI (MOCK)**.
4. Pilih skenario, lalu klik **Simulasikan Resep Masuk**.
5. Tinjau **Risiko klinis** dan **Kelengkapan asesmen** secara terpisah.

Simulator dapat memakai knowledge base DRAFT dan mapping pending agar data awal
dapat diuji. Semua resep simulasi berawalan `MOCK-`, tidak berasal dari pasien
nyata, dan tidak boleh dipakai untuk keputusan klinis. Pada mode normal, engine
hanya menerima knowledge base PUBLISHED dan mapping APPROVED/aktif.

Hasil simulasi otomatis masuk ke tab **Antrean & Alert**. Alert dikelompokkan
per resep; aplikasi tidak membuat satu pop-up untuk setiap pasangan.
Untuk pengujian cepat, klik **Simulasikan CRITICAL** langsung dari tab
**Antrean & Alert**.

## Menghubungkan E-MAS ke database Khanza

Panduan ini adalah prosedur yang dipakai pada PC uji E-MAS. Struktur tabel
Khanza rumah sakit telah dikonfirmasi sama dengan struktur MariaDB 10.4 yang
diuji. Pada uji lokal, nama database adalah `sik_emss_uji_lokal`; pada server
Khanza sebenarnya biasanya `sik`. Pastikan IT/DBA mengganti nama database,
host, dan alamat workstation sesuai lingkungan rumah sakit.

E-MAS tidak menulis ke tabel Khanza. Integrasi hanya membaca empat view dengan
akun yang memperoleh hak `SELECT`. Normalisasi kode obat Khanza menjadi lima
digit dilakukan di E-MAS dan tidak membutuhkan `UPDATE` terhadap kode barang
atau data historis Khanza.

### 1. Persiapan dan pemeriksaan DBA

1. Buat backup database Khanza dan uji prosedur pada clone terlebih dahulu.
2. Pastikan tabel berikut tersedia: `resep_obat`, `resep_dokter`,
   `resep_dokter_racikan`, `resep_dokter_racikan_detail`, `databarang`,
   `reg_periksa`, `pasien`, `dokter`, dan `poliklinik`.
3. Pastikan server menggunakan MariaDB 10.4 atau versi kompatibel dan waktu
   server/workstation benar.
4. Jalankan pekerjaan DDL dengan akun DBA. Akun operasional E-MAS tidak boleh
   diberi hak DDL atau akses langsung ke tabel dasar.

### 2. Membuat empat view integrasi

Pilih database target, lalu jalankan **seluruh isi** script resmi
`templates/khanza_integration_views_mariadb104.sql`. Script memakai
`CREATE OR REPLACE VIEW`, tidak berisi `INSERT`, `UPDATE`, atau `DELETE`.

Contoh melalui MariaDB client untuk database uji:

```sql
USE sik_emss_uji_lokal;
SOURCE C:/path-ke-source/emas-farmasi/templates/khanza_integration_views_mariadb104.sql;
```

Contoh untuk database Khanza sebenarnya setelah disetujui DBA:

```sql
USE sik;
SOURCE C:/path-ke-source/emas-farmasi/templates/khanza_integration_views_mariadb104.sql;
```

Script harus menghasilkan tepat empat view berikut:

- `vw_emss_prescription_header` untuk header, pasien, unit, dokter, status,
  token validasi, kelengkapan komposisi, dan waktu perubahan resep;
- `vw_emss_prescription_item` untuk obat reguler;
- `vw_emss_compound_item` untuk komponen racikan;
- `vw_emss_drug_master` untuk kode dan nama barang aktif/nonaktif.

Verifikasi setelah script selesai:

```sql
SHOW FULL TABLES
WHERE Table_type = 'VIEW'
  AND Tables_in_sik LIKE 'vw_emss_%';

SELECT COUNT(*) FROM vw_emss_prescription_header;
SELECT COUNT(*) FROM vw_emss_prescription_item;
SELECT COUNT(*) FROM vw_emss_compound_item;
SELECT COUNT(*) FROM vw_emss_drug_master;

SELECT no_resep, status_resep, item_basis, composition_complete, changed_at
FROM vw_emss_prescription_header
ORDER BY changed_at DESC
LIMIT 10;
```

Untuk database clone, ganti `Tables_in_sik` pada query pertama dengan
`Tables_in_sik_emss_uji_lokal`. Jangan menjalankan
`templates/khanza_final_items_candidate_mariadb104.sql`; file tersebut hanya
draft penelitian ekstraksi dan bukan kontrak aplikasi yang aktif.

### 3. Membuat akun read-only E-MAS

Ganti `IP_WORKSTATION` dengan IP tetap PC E-MAS dan gunakan password kuat yang
disimpan oleh IT. Jangan menggunakan host `%`. Contoh lengkap juga tersedia di
`templates/khanza_readonly_grants.example.sql`.

```sql
CREATE USER 'emss_readonly'@'IP_WORKSTATION'
IDENTIFIED BY 'PASSWORD_KUAT_DARI_DBA';

GRANT SELECT ON sik.vw_emss_prescription_header
TO 'emss_readonly'@'IP_WORKSTATION';
GRANT SELECT ON sik.vw_emss_prescription_item
TO 'emss_readonly'@'IP_WORKSTATION';
GRANT SELECT ON sik.vw_emss_compound_item
TO 'emss_readonly'@'IP_WORKSTATION';
GRANT SELECT ON sik.vw_emss_drug_master
TO 'emss_readonly'@'IP_WORKSTATION';

FLUSH PRIVILEGES;
```

Untuk uji di PC yang sama, host dapat berupa `127.0.0.1` dan nama database pada
empat `GRANT` adalah `sik_emss_uji_lokal`. Buktikan pembatasannya dengan akun
tersebut: `SELECT` pada empat view harus berhasil, sedangkan `SELECT` langsung
pada tabel seperti `resep_obat` harus ditolak.

### 4. Menyimpan password di Windows

Simpan password sebagai environment variable Windows tingkat **Machine**
bernama `EMSS_KHANZA_PASSWORD`. Gunakan dialog **System Properties → Advanced
→ Environment Variables** atau mekanisme secrets resmi rumah sakit. Jangan
menulis password di `config.toml`, source code, screenshot, log, atau README.
Tutup penuh E-MAS termasuk proses tray, lalu buka kembali agar proses baru
membaca environment variable tersebut.

### 5. Mengatur konfigurasi E-MAS

Backup terlebih dahulu
`C:\ProgramData\eMSSFarmasi\config.toml`, kemudian atur bagian Khanza seperti
berikut. Untuk server sebenarnya, ganti host dan database sesuai hasil DBA.

```toml
khanza_adapter = "mysql"
khanza_polling_enabled = true
khanza_internal_polling_consent = true
khanza_recent_days = 2
khanza_monitor_batch_size = 30
khanza_poll_interval_seconds = 1
khanza_page_size = 100
khanza_stability_interval_seconds = 2.0
khanza_stability_max_attempts = 3
khanza_reconnect_base_seconds = 5
khanza_reconnect_max_seconds = 300
khanza_host = "IP_SERVER_KHANZA"
khanza_port = 3306
khanza_database = "sik"
khanza_username = "emss_readonly"
khanza_connect_timeout_seconds = 5
khanza_query_timeout_seconds = 10
khanza_header_view = "vw_emss_prescription_header"
khanza_item_view = "vw_emss_prescription_item"
khanza_compound_view = "vw_emss_compound_item"
khanza_drug_view = "vw_emss_drug_master"
```

Pada PC uji lokal gunakan `khanza_host = "127.0.0.1"` dan
`khanza_database = "sik_emss_uji_lokal"`. Nilai `environment` harus mengikuti
tahap rollout yang telah disetujui rumah sakit; jangan mengubah label menjadi
production hanya untuk menghilangkan penanda uji. Mode lama
`khanza_adapter = "mysql_local_test"` tidak lagi digunakan.

### 6. Verifikasi dari aplikasi

1. Jalankan kembali E-MAS dan login dengan akun yang berwenang.
2. Buka tab **Integrasi Khanza** dan pastikan status koneksi berhasil.
3. Jalankan **Periksa & Poll Sekarang**, lalu periksa cursor dan jumlah resep.
4. Jalankan sinkronisasi master obat dan tinjau konflik kode/nama/kandungan;
   konflik tidak boleh dipetakan otomatis.
5. Buat satu resep reguler dan satu racikan pada Khanza uji, lanjutkan melalui
   status validasi yang biasa digunakan, lalu pastikan keduanya muncul pada
   **Antrean & Alert**.
6. Verifikasi kode seperti `000003795`, `03795`, dan `3795` dibaca sebagai
   identitas kanonik `03795`. Data historis Khanza harus tetap tidak berubah.
7. Untuk hasil `SAFE · COMPLETE`, pastikan seluruh obat terpetakan, semua
   pasangan dinilai, serta tidak ada interaksi, duplikasi, high-alert, atau
   kendala kelengkapan. Suara aman hanya diputar sekali setelah skrining selesai.
8. Tinjau log E-MAS bila koneksi gagal, tetapi jangan menyalin password atau
   identitas pasien ke tiket dukungan.

Sebelum operasional sebenarnya, apoteker/clinical reviewer tetap harus
menyetujui master mapping dan knowledge base DDI. Keberhasilan koneksi database
tidak dengan sendirinya merupakan persetujuan penggunaan klinis.

## Menguji adapter dan polling dengan mock

1. Pastikan `khanza_adapter = "mock"` dan
   `khanza_polling_enabled = false` di konfigurasi pengembangan.
2. Buka tab **Integrasi Khanza**.
3. Klik **Tambahkan Resep Uji ke Adapter**.
4. Klik **Periksa & Poll Sekarang**.
5. Tinjau status koneksi/cursor lalu buka **Antrean & Alert**.

## Mencatat intervensi dan membuka dashboard Sprint 7

1. Login menggunakan akun bernama dengan role `APOTEKER`, `SUPER_ADMIN`, atau
   `CLINICAL_REVIEWER`; Mode Farmasi tidak dapat mencatat identitas petugas.
2. Buka **Antrean & Alert**, pilih satu resep, lalu klik
   **Catat Intervensi Apoteker**.
3. Untuk HIGH_RISK/CRITICAL, lengkapi keputusan, media komunikasi, hasil
   komunikasi, dan dokter/pihak yang dihubungi.
4. Jika terapi diteruskan, alasan klinis wajib dicatat.
5. Centang **Tandai intervensi selesai** hanya setelah komunikasi dan keputusan
   selesai, lalu simpan.
6. Riwayat tersedia pada tab **Intervensi Apoteker**. Ringkasan tanpa identitas
   pasien tersedia pada **Dashboard & Laporan**.
7. Pilih periode **Bulanan**, **Triwulanan**, **Tahunan**, atau **Seluruh data**.
   Tabel **Tren Bulanan** menampilkan hasil Januari–Desember dan persentasenya;
   tabel **Per Unit/Depo** membantu membandingkan area pelayanan.

Ekspor CSV agregat hanya tersedia bagi role manajemen/admin yang berwenang dan
setiap ekspor dicatat pada audit.

## Mode Farmasi dan system tray

Pada layar login, klik **Mode Farmasi (tanpa password)** untuk membuka panel
operasional. Mode ini hanya tersedia bila `allow_workstation_mode = true` dan
administrator pertama sudah dibuat. Import, perubahan master, review knowledge
base, serta konfigurasi tetap terkunci dan membutuhkan login akun berwenang.

Menutup jendela akan menyembunyikan aplikasi ke system tray. Gunakan menu ikon
tray untuk membuka panel, menyembunyikan panel, atau benar-benar keluar.

Autostart Windows dapat dipasang atau dilepas dengan:

```powershell
scripts\install_autostart.bat
scripts\remove_autostart.bat
```

## Backup dan restore Sprint 9

Login sebagai `SUPER_ADMIN` atau `IT_ADMIN`, lalu buka tab **Backup & Restore**.
Backup harian dibuat satu kali per hari saat aplikasi berjalan. Gunakan
**Buat Backup Sekarang** sebelum perubahan besar, pilih satu baris lalu klik
**Verifikasi Terpilih** untuk memeriksa checksum/integritas, atau **Restore
Terpilih** untuk pemulihan. Restore selalu membuat safety backup dan menutup
aplikasi setelah berhasil; jalankan kembali aplikasi sesudahnya.

Panduan operasional dan latihan pemulihan ada di
`docs/BACKUP_RESTORE_SPRINT_9.md`.

## Lokasi produksi

- Database: `C:\ProgramData\eMSSFarmasi\Database\emss.db`
- Backup: `C:\ProgramData\eMSSFarmasi\Backups\`
- Export: `C:\ProgramData\eMSSFarmasi\Exports\`
- Log: `C:\ProgramData\eMSSFarmasi\Logs\`

Database aktif tidak boleh ditempatkan di folder jaringan bersama.

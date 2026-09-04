# E-MAS Farmasi — Panduan Instalasi, Koneksi SIMRS Khanza, dan Penggunaan

E-MAS Farmasi adalah aplikasi desktop Windows yang berjalan berdampingan dengan SIMRS Khanza untuk melakukan skrining keselamatan obat, termasuk Drug–Drug Interaction (DDI). Khanza tetap menjadi sistem utama. E-MAS membaca data Khanza melalui empat view integrasi dengan akun MySQL/MariaDB khusus yang hanya memiliki hak `SELECT`.

> **Prinsip penting:** E-MAS tidak mengubah, menghapus, atau menambahkan data pada tabel pelayanan Khanza. Integrasi ke Khanza bersifat **read-only**.

Panduan ini disusun agar proses pemasangan awal dapat dilakukan oleh staf IT rumah sakit secara berurutan tanpa harus memahami source code atau proses pengembangan aplikasi.

---

# 1. Instalasi E-MAS Farmasi di PC Client

## 1.1. Persiapan

Sebelum instalasi, pastikan:

- Windows 64-bit;
- PC client dapat terhubung ke server SIMRS Khanza melalui jaringan rumah sakit;
- alamat IP server Khanza diketahui;
- port MariaDB/MySQL diketahui, umumnya `3306`;
- nama database pelayanan Khanza diketahui, umumnya `sik`;
- IT/DBA memiliki akses administrator database untuk membuat view dan akun read-only;
- PC E-MAS mempunyai alamat IP yang tetap/reservasi DHCP agar hak akses database tidak berubah.

## 1.2. Pasang aplikasi

1. Jalankan file installer E-MAS Farmasi dari rilis resmi.
2. Bila Windows meminta izin **User Account Control (UAC)**, pilih **Yes**.
3. Ikuti proses instalasi sampai selesai.
4. Jalankan E-MAS Farmasi satu kali.
5. Tutup kembali aplikasi sebelum melakukan konfigurasi koneksi Khanza.
6. Pastikan E-MAS benar-benar keluar. Bila ikon masih berada di **system tray**, klik kanan ikon E-MAS lalu pilih **Keluar/Exit**.

Data operasional E-MAS disimpan di:

```text
C:\ProgramData\eMSSFarmasi\
```

Lokasi utama:

```text
Database : C:\ProgramData\eMSSFarmasi\Database\emss.db
Backup   : C:\ProgramData\eMSSFarmasi\Backups\
Export   : C:\ProgramData\eMSSFarmasi\Exports\
Log      : C:\ProgramData\eMSSFarmasi\Logs\
Config   : C:\ProgramData\eMSSFarmasi\config.toml
```

> Jangan menempatkan database aktif E-MAS pada folder jaringan bersama.

---

# 2. Memasukkan Master Obat dan Pemetaan

1. Login menggunakan akun yang mempunyai kewenangan pengelolaan master, misalnya `SUPER_ADMIN`, `KNOWLEDGE_ADMIN`, atau `CLINICAL_REVIEWER`.
2. Buka menu **Impor Pemetaan Obat / Import**.
3. Pilih workbook sumber pemetaan obat.
4. Klik **Validasi & Preview**.
5. Periksa jumlah data valid, invalid, duplikasi, dan pesan validasi.
6. Bila tidak ada baris invalid, klik **Commit ke Master**.
7. Buka **Master Obat & Mapping**.
8. Tinjau pemetaan yang masih berstatus `PENDING_REVIEW`.
9. Pastikan setiap kode obat Khanza telah terhubung ke zat aktif yang benar.
10. Setujui mapping setelah diverifikasi.

Preview tidak mengubah master. Commit tidak otomatis menjadikan mapping aktif. Mapping operasional harus berstatus **APPROVED/aktif** agar dapat digunakan oleh DDI engine.

## 2.1. Perhatian terhadap kode obat Khanza

E-MAS melakukan normalisasi identitas kode obat. Contoh:

```text
000003795
03795
3795
```

harus dikenali sebagai identitas kanonik yang sama:

```text
03795
```

Jika resep berhasil terbaca tetapi muncul pesan:

```text
Kode obat belum dipetakan ke zat aktif
```

periksa **mapping kode obat**, bukan hanya keberadaan nama obat pada master. Pastikan kode tersebut mempunyai hubungan ke zat aktif dan berstatus `APPROVED/aktif`.

---

# 3. Mengelola Master DDI

Master DDI menggunakan pasangan zat aktif kanonik.

Workflow publikasi:

```text
DRAFT → REVIEWED → APPROVED → PUBLISHED → RETIRED
```

Untuk data tambahan:

1. Buka menu **Import Data Interaksi / Import DDI**.
2. Gunakan template DDI yang disediakan aplikasi.
3. Jalankan **Validasi & Preview**.
4. Periksa seluruh pasangan dan informasi klinis.
5. Simpan/commit sebagai draft.
6. Lakukan review dan approval sesuai kewenangan rumah sakit.
7. Pastikan knowledge base yang akan digunakan secara operasional berstatus `PUBLISHED`.

Untuk pencadangan atau audit master, gunakan **Export Master DDI Lengkap**.

> Pada mode operasional normal, DDI engine menggunakan knowledge base `PUBLISHED` dan mapping obat `APPROVED/aktif`.

---

# 4. Menguji DDI Engine

Sebelum menghubungkan resep pelayanan nyata, fungsi DDI engine dapat diperiksa dari simulator aplikasi.

1. Login ke E-MAS.
2. Buka **Simulator DDI (MOCK)**.
3. Pilih skenario.
4. Klik **Simulasikan Resep Masuk**.
5. Buka **Antrean & Alert**.
6. Periksa:
   - hasil skrining;
   - risiko klinis;
   - kelengkapan asesmen;
   - pasangan interaksi yang ditemukan;
   - tampilan alert;
   - suara peringatan.

Untuk uji cepat kondisi risiko tinggi, gunakan **Simulasikan CRITICAL** pada menu **Antrean & Alert** bila fitur tersebut tersedia pada rilis yang dipasang.

Semua data `MOCK` hanya untuk pengujian dan bukan data pasien nyata.

---

# 5. Menghubungkan E-MAS ke Database SIMRS Khanza

Bagian ini merupakan tahapan utama pemasangan di lingkungan pelayanan.

Urutan yang disarankan:

```text
Periksa tabel Khanza
        ↓
Buat 4 view integrasi
        ↓
Buat akun emss_readonly
        ↓
Simpan password di Windows
        ↓
Atur config.toml
        ↓
Restart E-MAS
        ↓
Tes koneksi dan polling
        ↓
Sinkronisasi/pemetaan obat
        ↓
Uji resep pelayanan
        ↓
Operasional
```

## 5.1. Pastikan tabel Khanza tersedia

Pada database Khanza yang digunakan pelayanan, pastikan tabel berikut tersedia:

```text
resep_obat
resep_dokter
resep_dokter_racikan
resep_dokter_racikan_detail
databarang
reg_periksa
pasien
dokter
poliklinik
```

Pastikan juga MariaDB/MySQL pada server Khanza dapat diakses dari PC E-MAS.

E-MAS hanya membaca data melalui empat view integrasi dan akun `SELECT`. E-MAS tidak mempunyai mekanisme untuk melakukan `INSERT`, `UPDATE`, atau `DELETE` terhadap tabel pelayanan Khanza.

---

# 6. Membuat Empat View Integrasi E-MAS

> **Tahap ini wajib dilakukan pada database Khanza sebelum E-MAS dapat membaca resep.**

Login ke MariaDB/MySQL menggunakan akun DBA/administrator database, lalu pilih database Khanza:

```sql
USE sik;
```

Kemudian jalankan SQL berikut secara lengkap.

```sql
CREATE OR REPLACE SQL SECURITY DEFINER VIEW vw_emss_prescription_header AS
SELECT
    ro.no_resep AS no_resep,
    ro.no_rawat AS no_rawat,
    ro.status AS asal_layanan,
    rp.no_rkm_medis AS no_rm,
    ps.nm_pasien AS nama_pasien,
    COALESCE(NULLIF(pl.nm_poli, ''), NULLIF(rp.kd_poli, ''), ro.status) AS unit_depo,
    COALESCE(NULLIF(dr.nm_dokter, ''), ro.kd_dokter) AS dokter,
    CASE
        WHEN NULLIF(CAST(ro.tgl_penyerahan AS CHAR), '0000-00-00') IS NOT NULL
            THEN 'DISERAHKAN'
        WHEN NULLIF(CAST(ro.tgl_perawatan AS CHAR), '0000-00-00') IS NOT NULL
            THEN 'DIPROSES_FARMASI'
        ELSE 'DIRESEPKAN'
    END AS status_resep,
    CASE
        WHEN NULLIF(CAST(ro.tgl_penyerahan AS CHAR), '0000-00-00') IS NOT NULL
          OR NULLIF(CAST(ro.tgl_perawatan AS CHAR), '0000-00-00') IS NOT NULL
        THEN SHA2(
            CONCAT_WS(
                '|',
                CONVERT(ro.no_resep USING utf8mb4),
                CAST(ro.tgl_perawatan AS CHAR),
                CAST(ro.jam AS CHAR),
                CAST(ro.tgl_penyerahan AS CHAR),
                CAST(ro.jam_penyerahan AS CHAR)
            ),
            256
        )
        ELSE ''
    END AS validation_token,
    CASE
        WHEN NULLIF(CAST(ro.tgl_penyerahan AS CHAR), '0000-00-00') IS NOT NULL
          OR NULLIF(CAST(ro.tgl_perawatan AS CHAR), '0000-00-00') IS NOT NULL
        THEN 'FINAL'
        ELSE 'PRESCRIBED'
    END AS item_basis,
    CASE
        WHEN NULLIF(CAST(ro.tgl_penyerahan AS CHAR), '0000-00-00') IS NOT NULL
          OR NULLIF(CAST(ro.tgl_perawatan AS CHAR), '0000-00-00') IS NOT NULL
        THEN 1
        ELSE 0
    END AS composition_complete,
    CASE
        WHEN NULLIF(CAST(ro.tgl_penyerahan AS CHAR), '0000-00-00') IS NOT NULL
            THEN STR_TO_DATE(
                CONCAT(
                    CAST(ro.tgl_penyerahan AS CHAR),
                    ' ',
                    CAST(ro.jam_penyerahan AS CHAR)
                ),
                '%Y-%m-%d %H:%i:%s'
            )
        WHEN NULLIF(CAST(ro.tgl_perawatan AS CHAR), '0000-00-00') IS NOT NULL
            THEN STR_TO_DATE(
                CONCAT(
                    CAST(ro.tgl_perawatan AS CHAR),
                    ' ',
                    CAST(ro.jam AS CHAR)
                ),
                '%Y-%m-%d %H:%i:%s'
            )
        ELSE STR_TO_DATE(
            CONCAT(
                CAST(ro.tgl_peresepan AS CHAR),
                ' ',
                CAST(ro.jam_peresepan AS CHAR)
            ),
            '%Y-%m-%d %H:%i:%s'
        )
    END AS changed_at
FROM resep_obat AS ro
LEFT JOIN reg_periksa AS rp
    ON rp.no_rawat = ro.no_rawat
LEFT JOIN pasien AS ps
    ON ps.no_rkm_medis = rp.no_rkm_medis
LEFT JOIN dokter AS dr
    ON dr.kd_dokter = ro.kd_dokter
LEFT JOIN poliklinik AS pl
    ON pl.kd_poli = rp.kd_poli;


CREATE OR REPLACE SQL SECURITY DEFINER VIEW vw_emss_prescription_item AS
SELECT
    rd.no_resep AS no_resep,
    CONCAT(
        'R:',
        rd.kode_brng,
        ':',
        CONVERT(LEFT(SHA2(COALESCE(rd.aturan_pakai, ''), 256), 16) USING latin1)
    ) AS source_item_key,
    rd.kode_brng AS kode_brng,
    COALESCE(NULLIF(db.nama_brng, ''), rd.kode_brng) AS nama_brng,
    SUM(rd.jml) AS jumlah,
    rd.aturan_pakai AS aturan_pakai,
    CAST('' AS CHAR(1)) AS rute
FROM resep_dokter AS rd
LEFT JOIN databarang AS db
    ON db.kode_brng = rd.kode_brng
GROUP BY
    rd.no_resep,
    rd.kode_brng,
    COALESCE(NULLIF(db.nama_brng, ''), rd.kode_brng),
    rd.aturan_pakai;


CREATE OR REPLACE SQL SECURITY DEFINER VIEW vw_emss_compound_item AS
SELECT
    rdd.no_resep AS no_resep,
    CONCAT('C:', rdd.no_racik, ':', rdd.kode_brng) AS source_item_key,
    rdd.kode_brng AS kode_brng,
    COALESCE(NULLIF(db.nama_brng, ''), rdd.kode_brng) AS nama_brng,
    rdd.jml AS jumlah,
    COALESCE(rr.aturan_pakai, '') AS aturan_pakai,
    CAST('' AS CHAR(1)) AS rute,
    rdd.no_racik AS no_racik
FROM resep_dokter_racikan_detail AS rdd
LEFT JOIN resep_dokter_racikan AS rr
    ON rr.no_resep = rdd.no_resep
   AND rr.no_racik = rdd.no_racik
LEFT JOIN databarang AS db
    ON db.kode_brng = rdd.kode_brng;


CREATE OR REPLACE SQL SECURITY DEFINER VIEW vw_emss_drug_master AS
SELECT
    db.kode_brng AS kode_brng,
    db.nama_brng AS nama_brng,
    CASE
        WHEN db.status = '1' THEN 1
        ELSE 0
    END AS aktif
FROM databarang AS db;
```

Empat view yang harus terbentuk:

```text
vw_emss_prescription_header
vw_emss_prescription_item
vw_emss_compound_item
vw_emss_drug_master
```

## 6.1. Verifikasi empat view

Jalankan:

```sql
SHOW FULL TABLES
WHERE Table_type = 'VIEW'
  AND Tables_in_sik LIKE 'vw_emss_%';
```

Lalu:

```sql
SELECT COUNT(*) FROM vw_emss_prescription_header;
SELECT COUNT(*) FROM vw_emss_prescription_item;
SELECT COUNT(*) FROM vw_emss_compound_item;
SELECT COUNT(*) FROM vw_emss_drug_master;
```

Periksa resep terbaru:

```sql
SELECT
    no_resep,
    status_resep,
    item_basis,
    composition_complete,
    changed_at
FROM vw_emss_prescription_header
ORDER BY changed_at DESC
LIMIT 10;
```

Bila empat view dapat di-query tanpa error, lanjutkan ke pembuatan akun read-only.

---

# 7. Membuat Akun Read-Only E-MAS

## 7.1. Tentukan IP PC E-MAS

Pada PC E-MAS:

1. Tekan **Windows + R**.
2. Ketik:

```text
cmd
```

3. Tekan Enter.
4. Jalankan:

```cmd
ipconfig
```

5. Catat **IPv4 Address** PC E-MAS, contoh:

```text
192.168.1.25
```

Gunakan IP tersebut pada `IP_WORKSTATION`.

> Disarankan menggunakan IP statis atau DHCP reservation. Jangan menggunakan host `%`.

## 7.2. Buat user dan hak SELECT

Pada server MariaDB/MySQL, jalankan:

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

Contoh bila IP PC E-MAS adalah `192.168.1.25`:

```sql
CREATE USER 'emss_readonly'@'192.168.1.25'
IDENTIFIED BY 'PASSWORD_KUAT_DARI_DBA';

GRANT SELECT ON sik.vw_emss_prescription_header
TO 'emss_readonly'@'192.168.1.25';

GRANT SELECT ON sik.vw_emss_prescription_item
TO 'emss_readonly'@'192.168.1.25';

GRANT SELECT ON sik.vw_emss_compound_item
TO 'emss_readonly'@'192.168.1.25';

GRANT SELECT ON sik.vw_emss_drug_master
TO 'emss_readonly'@'192.168.1.25';

FLUSH PRIVILEGES;
```

`PASSWORD_KUAT_DARI_DBA` adalah **placeholder**. Ganti dengan password sebenarnya yang ditentukan IT/DBA.

Contoh konsep:

```text
PASSWORD_KUAT_DARI_DBA
        ↓ ganti dengan
password sebenarnya milik akun emss_readonly
```

Password yang sama persis akan digunakan pada langkah **Environment Variable Windows**.

---

# 8. Menyimpan Password Khanza di Windows

> **Tahap ini wajib bila E-MAS menggunakan akun `emss_readonly` yang mempunyai password.**

Password **tidak ditulis** di `config.toml`.

E-MAS membaca password dari Environment Variable Windows tingkat **Machine/System** dengan nama:

```text
EMSS_KHANZA_PASSWORD
```

## 8.1. Cara memasukkan password

Pada PC tempat E-MAS diinstal:

1. Tekan **Windows + R**.
2. Ketik:

```text
sysdm.cpl
```

3. Tekan **Enter**.
4. Buka tab **Advanced**.
5. Klik **Environment Variables...**
6. Pada bagian bawah **System variables**, klik **New...**

Isi:

```text
Variable name:
EMSS_KHANZA_PASSWORD

Variable value:
PASSWORD_KUAT_DARI_DBA
```

**PENTING:** nilai `PASSWORD_KUAT_DARI_DBA` harus diganti dengan **password sebenarnya yang sama persis** dengan password ketika membuat user:

```sql
'emss_readonly'@'IP_WORKSTATION'
```

Contoh hubungan password:

```text
MariaDB/MySQL
CREATE USER ... IDENTIFIED BY 'PasswordAsli123!';

                    HARUS SAMA

Windows System Variable
EMSS_KHANZA_PASSWORD = PasswordAsli123!
```

7. Klik **OK** pada dialog pembuatan variabel.
8. Klik **OK** pada jendela **Environment Variables**.
9. Klik **OK** pada jendela **System Properties**.

Dengan kata lain: **OK → OK → OK**.

Jangan menyimpan atau menyalin password tersebut ke:

- `config.toml`;
- source code;
- README;
- screenshot;
- log;
- tiket dukungan.

## 8.2. Memastikan variabel sudah tersedia tanpa menampilkan password

Buka PowerShell, lalu jalankan:

```powershell
if ([Environment]::GetEnvironmentVariable("EMSS_KHANZA_PASSWORD","Machine")) {
    "EMSS_KHANZA_PASSWORD tersedia"
} else {
    "EMSS_KHANZA_PASSWORD BELUM tersedia"
}
```

Hasil yang diharapkan:

```text
EMSS_KHANZA_PASSWORD tersedia
```

Setelah membuat atau mengubah environment variable:

1. tutup E-MAS sepenuhnya;
2. pastikan tidak tersisa di system tray;
3. jalankan kembali E-MAS.

Proses E-MAS yang baru akan membaca password dari Windows.

---

# 9. Mengatur `C:\ProgramData\eMSSFarmasi\config.toml`

Sebelum mengubah file, buat salinan cadangan:

```text
C:\ProgramData\eMSSFarmasi\config.toml
```

Contoh:

```text
config.toml.bak
```

Gunakan konfigurasi berikut.

> Bagian dengan tanda `<<< UBAH >>>` adalah bagian yang harus disesuaikan oleh IT dengan lingkungan Khanza rumah sakit.

```toml
environment = "test"
app_name = "E-MAS Farmasi"
data_dir = "C:/ProgramData/eMSSFarmasi"
database_filename = "emss.db"
log_level = "INFO"

session_timeout_minutes = 15
login_max_attempts = 5
login_lock_minutes = 15
sqlite_busy_timeout_ms = 5000

allow_workstation_mode = true
workstation_label = "Farmasi"

tray_enabled = true
minimize_to_tray = true
single_instance = true

backup_daily_enabled = true
backup_retention_days = 30
backup_retention_count = 30

# Koneksi SIMRS Khanza normal dalam mode read-only
khanza_adapter = "mysql"
khanza_polling_enabled = true
khanza_internal_polling_consent = true

# Pemeriksaan resep setiap 1 detik
khanza_poll_interval_seconds = 1
khanza_recent_days = 2
khanza_monitor_batch_size = 30
khanza_page_size = 100

# Menunggu komposisi resep stabil sebelum skrining
khanza_stability_interval_seconds = 2.0
khanza_stability_max_attempts = 3

khanza_reconnect_base_seconds = 5
khanza_reconnect_max_seconds = 300

# ============================================================
# BAGIAN YANG HARUS DISESUAIKAN OLEH IT
# ============================================================

# <<< UBAH >>> Isi dengan IP server SIMRS Khanza
# Contoh: khanza_host = "192.168.1.10"
khanza_host = "IP_SERVER_KHANZA"

# <<< CEK >>> Port MariaDB/MySQL Khanza. Umumnya 3306.
khanza_port = 3306

# <<< UBAH BILA BERBEDA >>> Nama database Khanza pelayanan
khanza_database = "sik"

# Username akun read-only yang dibuat pada langkah sebelumnya
khanza_username = "emss_readonly"

# ============================================================

khanza_connect_timeout_seconds = 5
khanza_query_timeout_seconds = 10

# Nama 4 view integrasi — jangan diubah bila menggunakan SQL README ini
khanza_header_view = "vw_emss_prescription_header"
khanza_item_view = "vw_emss_prescription_item"
khanza_compound_view = "vw_emss_compound_item"
khanza_drug_view = "vw_emss_drug_master"

# Password Khanza TIDAK ditulis di file ini.
# Password dibaca dari Windows System Environment Variable:
# EMSS_KHANZA_PASSWORD
```

## 9.1. Yang biasanya perlu diubah

Dalam pemasangan normal, IT terutama perlu memastikan tiga parameter berikut:

```toml
khanza_host = "IP_SERVER_KHANZA"
khanza_port = 3306
khanza_database = "sik"
```

Contoh:

```toml
khanza_host = "192.168.1.10"
khanza_port = 3306
khanza_database = "sik"
```

Username tetap:

```toml
khanza_username = "emss_readonly"
```

Password **jangan** ditambahkan ke `config.toml`.

> `127.0.0.1` hanya berarti database berada pada komputer E-MAS itu sendiri. Bila server Khanza berada pada komputer/server lain, gunakan **IP server Khanza yang sebenarnya**.

Setelah selesai:

1. simpan `config.toml`;
2. tutup editor;
3. tutup E-MAS sepenuhnya bila masih berjalan;
4. buka kembali E-MAS.

---

# 10. Verifikasi Koneksi dari E-MAS

Setelah empat view, akun read-only, password Windows, dan `config.toml` selesai:

1. Jalankan E-MAS.
2. Login dengan akun yang berwenang.
3. Buka **Koneksi Khanza / Integrasi Khanza**.
4. Periksa indikator koneksi.
5. Jalankan **Periksa & Poll Sekarang**.
6. Pastikan tidak muncul error:
   - host tidak ditemukan;
   - access denied;
   - database tidak ditemukan;
   - view tidak ditemukan;
   - timeout koneksi.
7. Periksa cursor/pembacaan terakhir dan jumlah resep yang ditemukan.

Bila status menunjukkan:

```text
Terhubung ke Khanza
Pemeriksaan otomatis aktif
```

maka koneksi dasar sudah berhasil.

---

# 11. Sinkronisasi dan Pemeriksaan Mapping Obat Khanza

Setelah koneksi berhasil:

1. Jalankan sinkronisasi master obat dari Khanza.
2. Buka **Master Obat / Impor Pemetaan Obat**.
3. Tinjau kode obat yang belum mempunyai zat aktif.
4. Jangan memetakan otomatis bila nama/kandungan tidak yakin.
5. Pastikan mapping yang benar berstatus `APPROVED/aktif`.
6. Periksa khusus obat yang muncul pada resep pelayanan.

Contoh:

```text
Kode Khanza   : 000003215
Nama          : LEVOFLOXACIN 500 MG
Kode kanonik  : 03215
Zat aktif     : Levofloxacin
Status mapping: APPROVED
```

dan:

```text
Kode Khanza   : 000003800
Nama          : CEFIXIME 100 MG
Kode kanonik  : 03800
Zat aktif     : Cefixime
Status mapping: APPROVED
```

Jika nama obat ada pada master tetapi resep tetap menyatakan:

```text
Kode obat belum dipetakan ke zat aktif
```

periksa hubungan **kode Khanza → zat aktif → status mapping**, bukan hanya nama obat.

Setelah memperbaiki mapping, gunakan **Coba Periksa Ulang** pada resep.

---

# 12. Uji Resep dari Khanza Pelayanan

Setelah koneksi dan mapping siap, lakukan uji terkontrol bersama petugas pelayanan.

## 12.1. Resep reguler

1. Masukkan satu resep reguler melalui workflow Khanza seperti biasa.
2. Lanjutkan resep sampai status yang dibaca E-MAS.
3. Tunggu polling otomatis atau klik **Periksa & Poll Sekarang**.
4. Buka **Antrean & Alert**.
5. Pastikan:
   - nomor resep benar;
   - pasien/unit/dokter terbaca sesuai view;
   - seluruh obat terbaca;
   - mapping zat aktif berhasil;
   - hasil skrining muncul.

## 12.2. Resep racikan

Lakukan prosedur yang sama dengan satu resep racikan dan pastikan komponen racikan muncul di E-MAS.

## 12.3. Verifikasi hasil SAFE

Untuk hasil:

```text
SAFE · COMPLETE
```

pastikan:

- seluruh obat terpetakan;
- semua pasangan sudah dinilai;
- tidak ada interaksi yang ditemukan;
- tidak ada issue kelengkapan;
- suara aman, bila diaktifkan oleh aplikasi, berjalan sesuai konfigurasi.

## 12.4. Verifikasi hasil interaksi

Gunakan kombinasi obat yang memang terdapat pada master DDI untuk memastikan:

- `INTERACTION_FOUND` muncul;
- severity sesuai master;
- alert muncul;
- suara peringatan berjalan;
- detail pasangan dapat dibuka.

---

# 13. Penggunaan Harian di Client Farmasi

Setelah konfigurasi awal selesai, penggunaan rutin tidak memerlukan pengaturan database berulang.

Alur harian:

```text
Windows menyala
      ↓
E-MAS berjalan
      ↓
Terhubung ke Khanza
      ↓
Polling resep otomatis
      ↓
Resep stabil dibaca
      ↓
Kode obat dipetakan ke zat aktif
      ↓
DDI engine melakukan skrining
      ↓
Hasil masuk ke Antrean & Alert
      ↓
Popup/suara sesuai hasil skrining
```

Petugas farmasi dapat menggunakan **Mode Farmasi** untuk akses operasional terbatas bila fitur tersebut diaktifkan pada konfigurasi:

```toml
allow_workstation_mode = true
```

Perubahan master, mapping, knowledge base, atau konfigurasi tetap harus dilakukan oleh akun yang mempunyai kewenangan.

---

# 14. Mencatat Intervensi Apoteker

1. Buka **Antrean & Alert**.
2. Pilih resep.
3. Klik **Catat Intervensi Apoteker**.
4. Lengkapi informasi yang diperlukan.
5. Untuk hasil risiko tinggi/critical, dokumentasikan keputusan dan tindak lanjut.
6. Bila terapi diteruskan, masukkan alasan klinis sesuai workflow aplikasi.
7. Tandai intervensi selesai setelah komunikasi/keputusan benar-benar selesai.
8. Riwayat dapat diperiksa pada menu intervensi dan dashboard.

---

# 15. Suara Peringatan

Buka:

```text
Pengaturan → Suara Peringatan
```

Periksa bahwa suara yang diperlukan aktif.

Jika skrining berhasil tetapi suara/pop-up tidak muncul:

1. pastikan hasil resep benar-benar sudah selesai diproses;
2. pastikan mapping obat lengkap;
3. periksa pengaturan suara;
4. periksa apakah aplikasi masih berjalan di system tray;
5. lakukan uji dengan **Simulasikan CRITICAL** bila tersedia;
6. periksa log E-MAS bila masih gagal.

---

# 16. Backup dan Restore

Login menggunakan akun dengan kewenangan backup/restore, lalu buka:

```text
Pencadangan & Pemulihan
```

Backup harian disimpan di:

```text
C:\ProgramData\eMSSFarmasi\Backups\
```

Sebelum perubahan besar pada master, mapping, atau konfigurasi:

1. buat backup;
2. verifikasi backup;
3. lakukan perubahan;
4. bila restore dilakukan, jalankan kembali E-MAS setelah proses selesai.

---

# 17. Autostart dan System Tray

E-MAS dapat berjalan di system tray.

Menutup jendela utama dapat hanya menyembunyikan aplikasi. Untuk benar-benar menghentikan E-MAS:

1. cari ikon E-MAS pada system tray;
2. klik kanan;
3. pilih **Keluar/Exit**.

Hal ini penting setelah:

- mengubah `config.toml`;
- membuat/mengubah `EMSS_KHANZA_PASSWORD`;
- mengubah koneksi server;
- melakukan restore.

Setelah perubahan tersebut, buka kembali E-MAS agar konfigurasi baru dibaca.

---

# 18. Troubleshooting Koneksi

## 18.1. `Access denied for user 'emss_readonly'`

Periksa:

- username di `config.toml`;
- IP PC E-MAS pada akun MySQL;
- password `EMSS_KHANZA_PASSWORD`;
- password harus sama persis dengan password pada `CREATE USER`;
- hak `GRANT SELECT` pada empat view.

## 18.2. `Can't connect` / timeout

Periksa:

- `khanza_host`;
- port `3306` atau port yang digunakan rumah sakit;
- firewall;
- service MariaDB/MySQL;
- routing/VLAN jaringan;
- apakah PC E-MAS dapat menjangkau server Khanza.

Contoh uji PowerShell:

```powershell
Test-NetConnection IP_SERVER_KHANZA -Port 3306
```

Contoh:

```powershell
Test-NetConnection 192.168.1.10 -Port 3306
```

## 18.3. View tidak ditemukan

Pada database `sik`, jalankan:

```sql
SHOW FULL TABLES
WHERE Table_type = 'VIEW'
  AND Tables_in_sik LIKE 'vw_emss_%';
```

Harus ada tepat:

```text
vw_emss_prescription_header
vw_emss_prescription_item
vw_emss_compound_item
vw_emss_drug_master
```

## 18.4. Resep terbaca tetapi obat belum terpetakan

Masalah berada pada mapping E-MAS, bukan koneksi database.

Periksa:

```text
Kode obat Khanza
→ normalisasi kode
→ zat aktif
→ status APPROVED/aktif
```

## 18.5. Password baru tidak terbaca

Setelah mengubah `EMSS_KHANZA_PASSWORD`:

1. keluar penuh dari E-MAS;
2. pastikan proses tray berhenti;
3. buka kembali E-MAS.

## 18.6. Khanza gagal menyimpan tanggal `0000-00-00`

Masalah ini berasal dari konfigurasi MariaDB/MySQL Khanza, bukan dari empat view E-MAS.

Contoh pesan:

```text
Data truncation: Incorrect date value: '0000-00-00'
```

Minta DBA memeriksa `sql_mode` MariaDB/MySQL yang digunakan Khanza sebelum melakukan perubahan pada database pelayanan.

---

# 19. Checklist Instalasi untuk IT

Gunakan checklist ini pada setiap PC E-MAS baru.

```text
[ ] E-MAS sudah terinstal
[ ] PC E-MAS mempunyai IP tetap/reservasi
[ ] IP server Khanza diketahui
[ ] Port database diketahui
[ ] Database Khanza = sik atau nama aktual sudah dikonfirmasi

[ ] 9 tabel Khanza yang diperlukan tersedia
[ ] vw_emss_prescription_header tersedia
[ ] vw_emss_prescription_item tersedia
[ ] vw_emss_compound_item tersedia
[ ] vw_emss_drug_master tersedia

[ ] User emss_readonly dibuat untuk IP PC E-MAS
[ ] SELECT diberikan hanya pada 4 view
[ ] Password akun emss_readonly dicatat aman oleh IT

[ ] EMSS_KHANZA_PASSWORD dibuat sebagai System/Machine variable
[ ] Nilai password sama persis dengan password emss_readonly

[ ] config.toml sudah dibackup
[ ] khanza_adapter = "mysql"
[ ] khanza_polling_enabled = true
[ ] khanza_host sudah sesuai IP server
[ ] khanza_port sudah benar
[ ] khanza_database sudah benar
[ ] khanza_username = "emss_readonly"
[ ] nama 4 view sesuai

[ ] E-MAS sudah direstart penuh
[ ] Status Terhubung ke Khanza
[ ] Periksa & Poll Sekarang berhasil
[ ] Sinkronisasi master obat berhasil
[ ] Mapping obat pelayanan diperiksa
[ ] Resep reguler terbaca
[ ] Resep racikan terbaca
[ ] DDI engine menghasilkan hasil
[ ] Popup diuji
[ ] Suara diuji
[ ] Backup awal dibuat
```

---

# 20. Ringkasan Instalasi Cepat

Untuk IT yang sudah memahami jaringan dan MariaDB/MySQL:

```text
1. Install E-MAS.
2. Pastikan 9 tabel Khanza tersedia.
3. Jalankan SQL pembuatan 4 view pada database sik.
4. Buat emss_readonly@IP_PC_EMAS.
5. GRANT SELECT hanya pada 4 view.
6. Buat System Variable Windows:
      EMSS_KHANZA_PASSWORD
   dengan nilai password yang SAMA dengan akun emss_readonly.
7. Edit:
      C:\ProgramData\eMSSFarmasi\config.toml
8. Sesuaikan:
      khanza_host
      khanza_port
      khanza_database
      khanza_username
9. Tutup penuh dan buka kembali E-MAS.
10. Buka Integrasi Khanza → Periksa & Poll Sekarang.
11. Sinkronisasi/pastikan mapping obat APPROVED.
12. Uji resep reguler + racikan.
13. Pastikan DDI, popup, dan suara bekerja.
14. Operasional.
```

---

## Catatan Keamanan

- E-MAS harus menggunakan akun database khusus read-only.
- Jangan menggunakan akun `root` atau akun operasional Khanza pada E-MAS.
- Jangan menggunakan host `%` untuk akun `emss_readonly`.
- Jangan menyimpan password database di `config.toml`.
- Jangan mengirim password atau identitas pasien melalui screenshot/log/tiket dukungan.
- Perubahan master DDI dan pemetaan obat hanya dilakukan oleh petugas yang berwenang.

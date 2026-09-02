# Kontrak View Integrasi Khanza — Sprint 6

## Prinsip keselamatan

e-MSS memakai akun MySQL/MariaDB khusus yang hanya mendapat `SELECT` pada
empat view di bawah. Aplikasi tidak membutuhkan dan tidak boleh diberi
`INSERT`, `UPDATE`, `DELETE`, `CREATE`, `ALTER`, `DROP`, `TRIGGER`, atau
`EXECUTE`. Pembuatan view dilakukan oleh IT rumah sakit dengan akun admin DB;
e-MSS sendiri tidak membuat atau mengubah view.

Arsip `D:\KhanzaHMSWindows.zip` tidak tersedia pada sesi verifikasi Sprint 6.
Karena kustomisasi tabel Khanza dapat berbeda, IT wajib memetakan nama tabel
lokal ke kontrak kolom berikut di database uji terlebih dahulu. Jangan
menjalankan contoh terhadap produksi sebelum ditinjau DBA.

## View wajib

### `vw_emss_prescription_header`

Satu baris terbaru per resep:

| Kolom | Tipe | Keterangan |
|---|---|---|
| `no_resep` | VARCHAR | Kunci resep, tidak null |
| `no_rawat` | VARCHAR | Kunci kunjungan |
| `no_rm` | VARCHAR | Nomor rekam medis |
| `nama_pasien` | VARCHAR | Nama pasien |
| `unit_depo` | VARCHAR | Unit/depo farmasi |
| `dokter` | VARCHAR | Nama/kode dokter |
| `status_resep` | VARCHAR | Status lokal resep |
| `changed_at` | DATETIME(6) | Waktu perubahan monotonik |

Indeks sumber minimum: `(changed_at, no_resep)` dan unik pada `no_resep`.
`changed_at` harus ikut berubah saat header, obat reguler, atau racikan berubah.
Jika instalasi Khanza tidak memiliki timestamp revisi, IT perlu menyediakan
sumber perubahan yang sah; waktu pembuatan resep saja hanya mampu mendeteksi
resep baru, bukan revisi.

### `vw_emss_prescription_item`

| Kolom | Tipe |
|---|---|
| `no_resep` | VARCHAR |
| `source_item_key` | VARCHAR, unik dalam satu resep |
| `kode_brng` | VARCHAR |
| `nama_brng` | VARCHAR |
| `jumlah` | VARCHAR/DECIMAL |
| `aturan_pakai` | VARCHAR |
| `rute` | VARCHAR |

Indeks sumber minimum: `(no_resep, source_item_key)`.

### `vw_emss_compound_item`

Kolom sama dengan item reguler, ditambah `no_racik`. Setiap komponen racikan
harus menjadi satu baris dan `source_item_key` harus stabil serta unik dalam
satu resep. Indeks sumber minimum: `(no_resep, source_item_key)`.

### `vw_emss_drug_master`

| Kolom | Tipe |
|---|---|
| `kode_brng` | VARCHAR, unik |
| `nama_brng` | VARCHAR |
| `aktif` | BOOLEAN/TINYINT |

Indeks sumber minimum: `(kode_brng, aktif)`.

## Pembuatan akun read-only

Contoh ini harus disesuaikan DBA untuk host workstation yang tepat. Jangan
memakai `%` sebagai host dan jangan menaruh password dalam source code.

```sql
CREATE USER 'emss_readonly'@'IP_WORKSTATION' IDENTIFIED BY 'PASSWORD_KUAT_DARI_DBA';
GRANT SELECT ON sik.vw_emss_prescription_header TO 'emss_readonly'@'IP_WORKSTATION';
GRANT SELECT ON sik.vw_emss_prescription_item TO 'emss_readonly'@'IP_WORKSTATION';
GRANT SELECT ON sik.vw_emss_compound_item TO 'emss_readonly'@'IP_WORKSTATION';
GRANT SELECT ON sik.vw_emss_drug_master TO 'emss_readonly'@'IP_WORKSTATION';
```

Password hanya diberikan ke e-MSS melalui environment Windows
`EMSS_KHANZA_PASSWORD`; tidak disimpan dalam TOML, SQLite, log, atau laporan.

## Query e-MSS

Deteksi memakai keyset pagination, bukan full scan:

```sql
WHERE changed_at > :changed_at
   OR (changed_at = :changed_at AND no_resep > :no_resep)
ORDER BY changed_at, no_resep
LIMIT :limit
```

Setiap resep dibaca dua kali dengan jeda singkat. Hanya snapshot identik yang
diproses. Resep yang terus berubah menjadi `INCOMPLETE`; koneksi yang putus
menjadi `DISCONNECTED` dan dijadwalkan reconnect eksponensial. Dalam kedua
kondisi itu e-MSS tidak mengeluarkan status `SAFE` baru.

# E-MAS Farmasi

**Electronic Medication Alert System** untuk membantu apoteker melakukan
skrining *drug–drug interaction* (DDI) dari resep yang sedang dibuka di SIMRS
Khanza.

Khanza tetap menjadi sistem utama. E-MAS tidak mengubah resep, obat, pasien,
atau transaksi Khanza. Pembacaan resep melalui Desktop/Java Access Bridge (JAB)
bersifat read-only. MySQL Khanza tetap tersedia sebagai fallback read-only dan
tidak boleh aktif bersamaan dengan Desktop/JAB.

## Rilis 1.0.6

Rilis ini menyertakan `KhanzaBridge.exe` dan modul overlay Khanza secara
langsung pada installer Windows. Overlay tetap opt-in: instalasi baru memulai
dengan overlay nonaktif, sedangkan workstation yang telah lulus UAT dan sudah
memiliki `khanza_desktop_overlay_poc = true` mempertahankan konfigurasi tersebut
saat upgrade.

Fitur utama yang tersedia:

- pembacaan resep Khanza melalui Desktop/JAB;
- skrining DDI menggunakan Knowledge Base yang Published;
- popup ringkas, audio, dan penandaan baris obat sebagai UX tambahan;
- registry obat belum dipetakan dan workflow mapping;
- pengelolaan Knowledge Base, versi, provenance, publish, dan rollback;
- backup/restore lokal, paket update KB, status workstation, dashboard kualitas,
  serta status operasional;
- profil commissioning Rawat Jalan (RALAN) atau Rawat Inap (RANAP).

## Instalasi Windows

1. Jalankan installer resmi sebagai administrator.
2. Pada instalasi baru, selesaikan commissioning dan pilih profil **RALAN** atau
   **RANAP** yang sesuai dengan workstation.
3. Buka **Persiapan Instalasi** lalu jalankan Compatibility/Deployment Wizard.
4. Buka **Status Operasional & Pemulihan** untuk memastikan Database Lokal,
   Knowledge Base DDI, Prescription Source, Khanza/JAB, dan KhanzaBridge siap.
5. Jalankan UAT resep sebelum dipakai untuk pelayanan.

Lokasi data persisten:

```text
C:\ProgramData\eMSSFarmasi\
├── Database\emss.db
├── Backups\
├── Exports\
├── Logs\
└── config.toml
```

Upgrade aplikasi menjaga database lokal, mapping, registry unmapped,
Knowledge Base, audit, konfigurasi, dan profil commissioning. Uninstall tidak
menghapus data persisten tanpa konfirmasi eksplisit.

## Koneksi Khanza: Desktop/JAB (utama)

Mode produksi saat ini adalah Desktop/JAB. Jalankan E-MAS dan Khanza pada sesi
Windows pengguna yang sama, kemudian atur `config.toml`:

```toml
khanza_adapter = "desktop"
khanza_polling_enabled = true
khanza_internal_polling_consent = true
khanza_poll_interval_seconds = 1
khanza_stability_interval_seconds = 2.0
khanza_stability_max_attempts = 3
```

Jangan menetapkan `khanza_desktop_bridge_path` ke executable UAT sementara.
Installer sudah memasang `KhanzaBridge.exe` bersama aplikasi.

Overlay hanya diaktifkan setelah UAT workstation membuktikan baris yang tepat
disorot pada skala Windows 100%, 125%, atau 150%:

```toml
khanza_desktop_overlay_poc = true
```

Jika pembacaan Desktop/JAB atau koordinat tabel tidak dapat dibuktikan aman,
overlay disembunyikan. Popup dan audio tetap dapat berjalan; overlay bukan jalur
klinis utama.

## Koneksi Khanza: MySQL fallback

MySQL hanya dipakai jika disetujui dan Desktop/JAB tidak digunakan:

```toml
khanza_adapter = "mysql"
khanza_host = "IP_SERVER_KHANZA"
khanza_port = 3306
khanza_database = "sik"
khanza_username = "emss_readonly"
khanza_polling_enabled = true
khanza_internal_polling_consent = true
```

Gunakan akun `emss_readonly` yang hanya memperoleh `SELECT` pada empat view
integrasi. Password **tidak** boleh ditulis pada `config.toml`; simpan sebagai
Windows Machine Environment Variable `EMSS_KHANZA_PASSWORD`.

SQL resmi view dan contoh hak akses tersedia di:

- [templates/khanza_integration_views_mariadb104.sql](templates/khanza_integration_views_mariadb104.sql)
- [templates/khanza_readonly_grants.example.sql](templates/khanza_readonly_grants.example.sql)
- [docs/KHANZA_VIEW_CONTRACT_SPRINT_6.md](docs/KHANZA_VIEW_CONTRACT_SPRINT_6.md)

> Invariant: `Desktop/JAB XOR MySQL`. Jangan mengaktifkan dua sumber resep
> sekaligus.

## Penggunaan operasional

1. Pastikan status sistem menunjukkan **SIAP DIGUNAKAN**.
2. Buka resep pada Khanza sampai detail resep dan daftar obat tampil stabil.
3. E-MAS membaca resep, melakukan mapping, lalu mengevaluasi DDI pada KB aktif.
4. Hasil dibedakan menjadi DDI ditemukan, nol DDI dengan asesmen lengkap,
   partial/unmapped, atau gangguan teknis. Kondisi belum lengkap tidak pernah
   diberi label SAFE.
5. Apoteker meninjau popup/antrean dan mencatat intervensi sesuai kebijakan RS.

Menu Admin/KFT mengelola mapping, Knowledge Base, dashboard kualitas, backup,
paket update KB, dan status operasional. Mode Farmasi hanya menggunakan KB
production dan tidak dapat publish, rollback, restore, atau mengubah konfigurasi.

## Knowledge Base DDI dan mapping

- Hanya satu KB Published/Active dipakai untuk skrining production.
- Draft tidak memengaruhi skrining production.
- Provenance Medscape dan Drugs.com dipertahankan per rule; perbedaan severity
  menjadi conflict/review, bukan overwrite diam-diam.
- `DrugComponentMapping` aktif tidak berarti knowledge DDI lengkap. Obat mapped
  tetapi KB belum lengkap tidak boleh menjadi SAFE.
- Gunakan menu **Obat Belum Dipetakan** untuk obat Khanza baru dan lakukan review
  sebelum mapping diaktifkan.

## Backup, pemulihan, dan update KB

Login sebagai Admin/Super Admin untuk:

- membuat dan memverifikasi backup lokal;
- melihat ringkasan sebelum restore dan melakukan restore terkonfirmasi;
- memasang paket update KB yang telah divalidasi checksum/manifesnya;
- melihat status workstation RALAN/RANAP terhadap versi KB target.

Backup diletakkan di `C:\ProgramData\eMSSFarmasi\Backups\`. Backup dan update
KB tidak berada pada jalur kritis skrining resep.

## Pengembangan dan pengujian

Persyaratan: Windows 64-bit dan Python 3.13 64-bit.

```powershell
py -3.13 -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[test]"
scripts\run_dev.bat --config config.example.toml init-db
scripts\run_dev.bat --config config.example.toml gui
```

Jalankan test terarah sesuai perubahan. Contoh test rilis installer:

```powershell
.venv\Scripts\python.exe -m pytest tests\test_release_config.py -q
```

## Mengunggah pembaruan ke GitHub

Repository ini sudah terhubung ke:
<https://github.com/fauzi170290/E--MAS-Farmasi-V-1-2026>

Unggah **source repository ini**, bukan seluruh folder build. Yang perlu masuk
ke GitHub adalah folder/file source berikut bila berubah:

```text
src/
tests/
migrations/
native/
installer/
templates/
docs/
seed/
scripts/
AGENTS.md
README.md
CHANGELOG.md
pyproject.toml
emss-farmasi.spec
.gitignore
```

Jangan unggah `.venv/`, `.vb/`, `.pytest-*/`, `.tmp-*/`, `build*/`, `dist*/`,
`outputs/`, `toolchain/`, `*.db`, `*.log`, `config.toml`, password, atau data
pasien. Aturan ini sudah tercantum di `.gitignore`.

Gunakan Git untuk memperbarui repository yang sudah ada:

```powershell
Set-Location "C:\Users\ozie1\Documents\Codex\2026-08-28\files-pasted-by-the-user-prompt\work\emas-farmasi"
git status
git add -A
git status
git commit -m "Release 1.0.6: bundle Khanza bridge and overlay"
git push origin main
```

Sebelum `git commit`, periksa `git status` dan pastikan tidak ada folder cache,
database, config lokal, atau output installer yang ikut masuk.

## Keamanan dan batasan

- Jangan menyimpan password Khanza, secret, atau data pasien di source, README,
  GitHub, screenshot, atau log dukungan.
- E-MAS tidak menggantikan keputusan klinis apoteker/KFT.
- Kegagalan audio atau overlay tidak boleh menghentikan evaluasi DDI dan popup.
- Bila sumber resep, KB aktif, mapping, atau data resep tidak dapat dinilai
  lengkap, sistem harus menunjukkan kondisi perlu perhatian/gangguan, bukan SAFE.
# Release Qualification & Deployment Evidence

Versi 0.22.0 mengubah build Windows dari rangkaian perintah manual menjadi gate
fail-closed yang menghasilkan bukti mesin-baca. Artefak hanya boleh diedarkan
bila `release-qualification.json` berstatus `QUALIFIED` dan
`data-lifecycle-drill.json` berstatus `PASS`.

## Tahapan build

Jalankan `scripts\build_installer.bat` pada Windows build resmi. Skrip akan:

1. menemukan virtual environment proyek;
2. menjalankan preflight Python 3.13 64-bit, PyInstaller, Inno Setup 6,
   konsistensi versi, dan satu Alembic head;
3. menjalankan seluruh regression test dan branch coverage;
4. menjalankan drill data-lifecycle pada database sementara;
5. membangun PyInstaller ONEDIR;
6. memeriksa struktur ONEDIR, membuat SHA-256 per file, dan menjalankan health
   smoke pada executable;
7. mengompilasi installer Inno Setup;
8. menghitung checksum installer dan menghasilkan qualification final.

Setiap langkah menghentikan build dengan exit code nonzero bila gagal.

## Laporan qualification

Folder `outputs\qualification` berisi:

- `preflight.json`: gate toolchain untuk binary;
- `installer-preflight.json`: gate toolchain termasuk Inno Setup;
- `data-lifecycle-drill.json`: bukti upgrade/restore/rollback;
- `binary-qualification.json`: struktur, checksum, dan smoke ONEDIR;
- `release-qualification.json`: manifest final termasuk installer.

Format qualification adalah `EMSS_RELEASE_QUALIFICATION_V1`. Status:

- `QUALIFIED`: seluruh check lulus;
- `BLOCKED`: toolchain wajib tidak tersedia atau salah arsitektur/versi;
- `FAILED`: kontrak source, artefak, checksum manifest, atau smoke gagal.

`BLOCKED` tidak boleh diubah manual menjadi lulus. Jalankan ulang pada host yang
memenuhi syarat dan simpan laporan baru bersama artefak final.

## Kontrol artefak

Qualification mewajibkan executable, `alembic.ini`, migration, template, dan
asset UI pada ONEDIR. Seluruh file dicatat dengan path relatif, ukuran, dan
SHA-256. Symlink serta file `.env`, private key, PEM, PFX, atau nama secret umum
ditolak. Manifest tidak menyimpan path data pasien, password, atau isi database.

Health smoke memakai folder sementara, integrasi Khanza disabled, tray mati,
dan single-instance mati. Binary harus mengembalikan state `READY` dengan
schema revision yang sama dengan satu Alembic head source. Hasil health ditulis
atomik ke file JSON agar executable GUI tidak bergantung pada stdout.

Tree packaging mengecualikan `__pycache__`, bytecode `.pyc`, artefak inspeksi,
serta modul testing Alembic. Modul dinamis runtime yang diperlukan dicantumkan
secara eksplisit dan diverifikasi oleh binary smoke.

## Drill data-lifecycle

Drill membuat data sintetis pada schema 0017, membuat dan memverifikasi backup,
upgrade ke head 0018, restore backup lama dan forward-migrate, downgrade ke
0017, lalu upgrade kembali. Pengguna sintetis harus bertahan dan health/audit
chain harus valid. Database drill tidak memakai data rumah sakit.

Drill otomatis tidak menggantikan latihan pada salinan data representatif RS.
Sebelum limited pilot, IT tetap wajib menjalankan upgrade, backup, restore, dan
rollback di lingkungan staging dengan volume dan kebijakan akses sebenarnya.

## Toolchain build yang telah diverifikasi

- Python 3.13.15 64-bit;
- PyInstaller 6.22.0;
- Inno Setup 6.7.3;
- laporan binary dan installer berstatus `QUALIFIED`.

## Gate eksternal yang tersisa

- Windows 64-bit bersih atau image build yang disetujui;
- smoke instal, upgrade, start, autostart opsional, dan uninstall;
- konfirmasi ProgramData/database/backup tidak terhapus saat upgrade/uninstall;
- penandatanganan kode bila diwajibkan kebijakan RS; artefak build lokal saat
  ini belum memiliki signature Authenticode.

Jangan menyatakan production-ready hanya berdasarkan laporan otomatis. UAT
klinis/IT, latihan insiden, dan persetujuan go-live Sprint 16 tetap wajib.

# Test Report — Sprint 5

## Ringkasan

- Tanggal: 3 Agustus 2026
- Platform: Windows 64-bit
- Runtime verifikasi sementara: Python 3.12.13
- PySide6/Qt: 6.11.1
- Pytest: 9.1.1
- Hasil: 104 lulus, 0 gagal
- Coverage core: 87%
- Target: minimal 85%

## Cakupan

- Migrasi schema baru dan migrasi dari `0004_sprint4`.
- Routing alert seluruh status risiko/kelengkapan.
- Alert gabungan satu per resep.
- CRITICAL dan HOLD RECOMMENDED.
- NOT_ASSESSED/UNMAPPED/ERROR tidak menjadi SAFE.
- Enqueue idempoten, filter unit/status, detail pair/issue, dan summary.
- Acknowledge/review dengan identitas pengguna.
- Retry manual dan dead-letter queue.
- Mode Farmasi tanpa password dan identitas sistem tidak dapat login biasa.
- System tray menu dan ringkasan status.
- Single-instance dan activation request.
- Panel UI, filter, warna status, dan detail hasil.
- Timestamp audit monoton serta regresi Sprint 1–4.

## Validasi visual

Panel diuji dengan resep MOCK CRITICAL pada resolusi 1280×760:

- satu baris antrean;
- risiko CRITICAL dan kelengkapan COMPLETE terlihat terpisah;
- detail menampilkan HOLD RECOMMENDED;
- pasangan DDI tampil pada tabel detail;
- tidak ada kolom hitam atau popup per pasangan.

## Release gate

Python 3.13 64-bit tetap wajib diverifikasi sebelum build produksi. Adapter
Khanza dan polling belum tersedia; antrean produksi tidak boleh diaktifkan
sampai Sprint 6 selesai dan akun MySQL read-only tervalidasi.

## Database pengguna

- Backup pramigrasi: `pre-sprint5-20260803-092340-emss.db`.
- SHA-256 backup cocok dengan database sumber.
- Schema aktif: `0005_sprint5`.
- Health: `READY`.
- `PRAGMA integrity_check`: `ok`.
- `PRAGMA foreign_key_check`: tanpa temuan.
- Rantai audit: valid.
- Rule DDI tetap: 5.410.
- Antrean/alert aktif setelah migrasi: 0/0 (tidak ada data uji disisipkan).
- Mode Farmasi: aktif melalui konfigurasi.
- Khanza: `NOT_CONFIGURED`.

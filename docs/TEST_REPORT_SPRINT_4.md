# Test Report — Sprint 4

## Ringkasan

- Tanggal: 31 Juli 2026
- Platform: Windows 64-bit
- Runtime verifikasi sementara: Python 3.12.13
- PySide6/Qt: 6.11.1
- Pytest: 9.1.1
- Hasil: 85 lulus, 0 gagal
- Coverage core: 87%
- Target coverage core: minimal 85%

## Cakupan

- Migrasi schema baru dan migrasi dari `0003_sprint3`.
- Prescription hash dan perubahan field klinis.
- Canonical pair, deduplikasi, obat kombinasi, dan komponen racikan.
- Batch lookup rule DDI.
- Interaksi positif dan severity tertinggi.
- Perbedaan assessed-no-interaction dengan pair-not-assessed.
- Quick-closure, NOT_ASSESSABLE, EXCLUDED, dan missing rule.
- Obat belum dipetakan dan data komponen tidak lengkap.
- Reuse hasil identik dan pembuatan revision baru.
- Pemisahan risiko dan kelengkapan asesmen.
- Pembatasan mode MOCK pada development/test.
- UI simulator dan regression Sprint 1–3.

## Validasi database pengguna

Pengujian awal dilakukan pada salinan database pengguna:

- migrasi `0003_sprint3 → 0004_sprint4` berhasil;
- skenario CRITICAL menghasilkan `CRITICAL + COMPLETE`;
- skenario HIGH_RISK menghasilkan `HIGH_RISK + COMPLETE`;
- skenario belum dinilai menghasilkan `SAFE + NOT_ASSESSED`;
- skenario unmapped menghasilkan `SAFE + UNMAPPED`;
- perubahan resep menghasilkan revision 2;
- database Khanza tidak dibaca atau diubah.

Database lokal aktif kemudian dimigrasikan setelah proses aplikasi dipastikan
tertutup:

- backup: `pre-sprint4-20260731-095325-emss.db`;
- checksum backup SHA-256 cocok dengan sumber;
- schema aktif: `0004_sprint4`;
- health: `READY`;
- `PRAGMA integrity_check`: `ok`;
- `PRAGMA foreign_key_check`: tanpa temuan;
- rantai audit: valid;
- resep/screening MOCK pada database aktif: 0;
- koneksi Khanza: `NOT_CONFIGURED`.

## Release gate

Runtime Codex yang tersedia masih Python 3.12.13. Pengujian ulang pada Python
3.13 64-bit wajib dilakukan sebelum executable/installer produksi. Integrasi
baca Khanza, antrean, alert klinis, dan system tray berada di sprint berikutnya.

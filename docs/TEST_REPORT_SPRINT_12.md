# Test Report 0.19.0 — Shift Closeout & Pilot Session Ledger

## Hasil quality gate

- 176 test lulus.
- Branch coverage keseluruhan 87% (`fail_under = 85`).
- Tidak ada regression failure.
- Dua warning berasal dari adapter datetime SQLite bawaan Python 3.12 pada
  contract test MySQL; bukan kegagalan aplikasi.

Perintah verifikasi:

```powershell
python -m coverage erase
python -m coverage run -m pytest -q
python -m coverage report
```

## Cakupan 0.19.0

- closeout hanya oleh pemilik klinis aktif;
- snapshot agregat alert CRITICAL/alert lain/intervensi outstanding;
- incoming dan outgoing attestation dengan akun berbeda;
- larangan pengesahan IT sebelum outgoing attestation;
- handover atomik dan pembuatan shift baru;
- shift expiry terpisah dari activation expiry;
- ledger berantai SHA-256 dan verifikasi rantai;
- trigger immutable menolak perubahan ledger;
- UI tombol closeout, outgoing attestation, serta tabel ledger;
- migrasi baru, backfill aktivasi 0.18.0, downgrade ke 0015, preservasi data,
  dan upgrade ulang ke 0016.

## Gate eksternal yang tetap wajib

- build dan smoke test binary Python 3.13 64-bit;
- kompilasi installer Inno Setup 6 pada Windows bersih;
- UAT pilot rumah sakit memakai akun bernama dan data sesuai kebijakan lokal;
- backup terverifikasi sebelum upgrade atau rollback produksi.

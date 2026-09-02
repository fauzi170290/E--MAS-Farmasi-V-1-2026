# Test Report 0.20.0 — Pilot Evidence & Ledger Integrity

## Hasil quality gate

- 179 test lulus.
- Branch coverage keseluruhan 87% (`fail_under = 85`).
- Alembic head `0017_pilot_ledger_quarantine`.
- Upgrade/downgrade menjaga data legacy dan tabel ledger 0.19.0.

## Skenario baru

- modifikasi payload ledger di luar jalur aplikasi terdeteksi;
- aktivasi dicabut dan closeout forensik dibuat tanpa memperpanjang rantai rusak;
- karantina persisten menolak alert dan aktivasi baru;
- pembukaan karantina ditolak selama rantai belum valid;
- pemulihan rantai dan pembukaan karantina diaudit serta tetap mewajibkan
  aktivasi ulang;
- ZIP bukti memuat manifest dan dua CSV dengan checksum yang cocok;
- paket tidak memiliki field identitas pasien atau nomor resep;
- UI menampilkan aksi ekspor dan pemulihan karantina;
- alasan suppression `ADVISORY_LEDGER_QUARANTINED` dipersistenkan;
- rollback melepas kolom karantina tanpa kehilangan data 0.18/0.19.

## Gate eksternal yang tetap wajib

- build/smoke test Python 3.13 64-bit;
- kompilasi installer Inno Setup 6;
- latihan restore dan respons insiden pada salinan data rumah sakit;
- persetujuan tata kelola penyimpanan paket bukti pilot.

# Test Report 0.21.0 — Evidence Verification & Chain of Custody

## Hasil quality gate

- 183 test lulus.
- Branch coverage keseluruhan 87% (`fail_under = 85`).
- Alembic head `0018_evidence_verification`.
- Upgrade/downgrade mempertahankan data legacy 0.18-0.20.

## Skenario baru

- paket ekspor asli lolos verifikasi checksum, manifest, chain, dan count;
- perubahan payload ledger ditolak meskipun ZIP masih dapat dibuka;
- file tak dikenal/path traversal, symlink, invalid ZIP, ukuran berlebih, dan
  compression bomb ditolak sebelum ekstraksi;
- manifest tidak dipercaya dan metadata bebas tidak masuk audit;
- setiap hasil valid/invalid dipersistenkan serta diaudit;
- UPDATE riwayat chain-of-custody ditolak oleh trigger immutable;
- UI menyediakan pemilihan paket dan tabel riwayat pemeriksaan;
- rollback melepas tabel 0018 tanpa kehilangan data 0.18-0.20.

## Gate eksternal yang tetap wajib

- build/smoke test Python 3.13 64-bit;
- kompilasi installer Inno Setup 6;
- latihan transfer media dan respons paket invalid pada lingkungan rumah sakit;
- persetujuan tata kelola retensi bukti serta audit chain-of-custody.

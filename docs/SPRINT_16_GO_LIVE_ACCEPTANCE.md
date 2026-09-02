# Sprint 16 — Go-Live Readiness & Acceptance Evidence

Versi 0.23.0 menyediakan workflow bukti dan keputusan go-live. Workflow ini
tidak mengaktifkan mode produksi secara otomatis dan tidak menggantikan
persetujuan rumah sakit.

## Prinsip kontrol

- Sesi hanya dapat dibuat IT Admin/Super Admin dari release qualification
  `QUALIFIED` dan installer yang checksum-nya sama dengan manifest.
- Binding versi aplikasi, Alembic head, report checksum, installer checksum,
  environment, dan expiry tidak dapat diubah.
- Satu sesi aktif per versi mencegah dua proses acceptance paralel yang rancu.
- PASS wajib menyertakan file bukti; aplikasi hanya menyimpan basename dan
  SHA-256, bukan path absolut atau isi bukti.
- FAIL/BLOCKED wajib alasan, tetap terlihat sebagai blocker, dan tidak dapat
  disulap menjadi readiness positif.
- Perubahan evidence mencabut attestation fungsi terkait.
- Attestor klinis dan teknis wajib pengguna berbeda. Pengambil keputusan GO
  wajib Direktur/Super Admin lain yang bukan salah satu attestor.
- NO-GO dapat dicatat lebih awal agar blocker menghasilkan keputusan formal.
- Keputusan final, identity evidence, dan ledger dilindungi trigger database.

## Checklist wajib

Teknis:

1. clean install dan health smoke pada Windows 64-bit bersih;
2. upgrade mempertahankan database, konfigurasi, dan backup ProgramData;
3. uninstall tidak menghapus database/backup;
4. restore dan rollback staging representatif;
5. signature Authenticode atau pengecualian kebijakan formal.

Klinis/operasional:

1. UAT klinis untuk release berjalan;
2. alert-fatigue review dan threshold operasional;
3. SOP, pelatihan, downtime, dan eskalasi insiden.

## Alur UI

1. Buka **Validasi Klinis & UAT → Go-Live Readiness**.
2. IT membuat sesi dan memilih `release-qualification.json` serta installer.
3. Pemilik fungsi memilih item, status, file bukti, dan catatan.
4. Setelah semua item fungsi PASS, klinis dan IT melakukan attestation.
5. Direktur/Super Admin independen mencatat GO atau NO-GO beserta alasan.
6. Simpan report release, installer, file bukti asli, dan backup bersama ledger
   sesuai kebijakan retensi rumah sakit.

## Collector clean-host

Setelah setiap tindakan pada mesin uji, jalankan collector tanpa memasukkan data
pasien ke command line. Contoh fase instalasi:

```bat
scripts\collect_clean_host_evidence.bat INSTALL ^
  --release-report C:\Evidence\release-qualification.json ^
  --installer C:\Evidence\e-MSS-Farmasi-RS-Setup-0.23.0-x64.exe ^
  --install-dir "C:\Program Files\eMSS Farmasi RS" ^
  --data-dir C:\ProgramData\eMSSFarmasi ^
  --output C:\Evidence\clean-install.json
```

Fase `UPGRADE` dan `UNINSTALL` wajib `--baseline` dari laporan PASS fase
sebelumnya. UPGRADE juga mewajibkan minimal satu backup. UNINSTALL mewajibkan
executable sudah tidak ada tetapi database, konfigurasi, dan backup ProgramData
tetap tersedia. Collector hanya memeriksa hasil; instalasi/uninstalasi tetap
dijalankan oleh petugas pada clean-host yang disetujui.

## Authenticode

Set `EMSS_REQUIRE_SIGNATURE=1` saat menjalankan
`scripts\build_installer.bat` bila code-signing diwajibkan. Qualification final
akan memeriksa binary dan installer memakai Windows Authenticode dan gagal bila
status bukan `Valid`.

Build unsigned tanpa flag tetap menghasilkan check
`AUTHENTICODE_POLICY=NOT_REQUIRED_BY_BUILD_POLICY`. Kondisi tersebut bukan
persetujuan keamanan; checklist `TECH-SIGNING` tetap memerlukan bukti waiver
formal sebelum dapat PASS.

Build lokal 0.23.0 pada 2026-08-11 berstatus `QUALIFIED`, tetapi binary dan
installer masih `NotSigned`. Jangan menandai `TECH-SIGNING` PASS hanya karena
qualification lokal lulus tanpa flag signature.

## Fail-safe

GO ditolak bila sesi kedaluwarsa, versi/schema berubah, evidence belum PASS,
attestation belum lengkap/tidak independen, checksum release tidak cocok saat
pembuatan sesi, atau ledger hash-chain tidak valid. Catatan GO/NO-GO tidak
mengubah environment maupun aktivasi Advisory Pilot.

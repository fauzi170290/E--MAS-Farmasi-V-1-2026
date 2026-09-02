# Test Report — Sprint 8

## Hasil otomatis

- Seluruh suite: **128 passed**.
- Coverage: **87%**, melewati ambang wajib 85%.
- `compileall`: lulus.
- `pip check`: tidak ada dependency rusak.
- Uji visual offscreen dashboard dan master keselamatan: lulus; seluruh
  permukaan memakai tema terang.

## Backup dan simulasi migrasi data pengguna

- Backup pra-Sprint 8:
  `pre-sprint8-20260804-135938-emss.db`.
- SHA-256:
  `7F290A176AA141C6940B4143150F6E72DF9947A4776A53C894185C4376D97A99`.
- Migrasi dijalankan pada salinan konsisten database aktif.
- Schema awal/hasil: `0007_sprint7` → `0008_sprint8`.
- Data sebelum/sesudah tetap sama: 221 obat, 159 zat aktif, 5.410 rule DDI,
  4 revisi resep, 4 skrining, dan 1 intervensi.
- Health hasil migrasi: `READY`; rantai audit: valid.
- Database aktif tidak dimigrasikan saat proses aplikasi masih berjalan.

## Kasus Sprint 8 yang diverifikasi

- duplikasi zat aktif pada item berbeda menghasilkan `REVIEW`;
- duplikasi kelas terapi mempertahankan pesan bahwa kombinasi dapat disengaja;
- polifarmasi dihitung dari zat aktif unik dengan ambang default 5/10;
- perubahan ambang hanya dapat dilakukan role berwenang dan tercatat audit;
- high-alert berlaku berdasarkan kode obat dan cakupan unit/depo;
- LASA mendukung enam jenis dan kebutuhan double-check;
- perubahan master keselamatan memaksa revisi skrining baru;
- temuan tampil bersama DDI tanpa mengubah kelengkapan asesmen menjadi aman;
- dashboard dan CSV menghitung jumlah/persentase duplicate therapy,
  polifarmasi, high-alert, serta LASA;
- regresi DDI, antrean, intervensi, MySQL read-only, password, dan UI tetap
  lulus.

## Release gate

Daftar high-alert, LASA, dan kelas terapi rumah sakit masih harus dimasukkan
serta divalidasi oleh apoteker/KFT. Verifikasi Python 3.13 64-bit, silent pilot,
UAT, backup/restore, dan installer Windows bersih tetap wajib sebelum produksi.

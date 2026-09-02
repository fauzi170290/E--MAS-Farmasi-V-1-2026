# Laporan Pencocokan Master High-Alert

## Keputusan penggunaan sumber

- Kebijakan lokal RS tanggal 1 Agustus 2023 menjadi sumber aktivasi utama.
- Hanya halaman 2 (daftar high-alert) dan halaman 4 (elektrolit konsentrat)
  yang dipakai.
- Halaman 1 (LASA) dan halaman 3 (risiko jatuh) sengaja tidak diimpor.
- ISMP Acute Care 2024 dipakai untuk pemeriksaan selisih. Entri yang hanya
  berasal dari ISMP disimpan nonaktif sampai memperoleh persetujuan KFT.
- Severity aplikasi ditetapkan `REVIEW`: temuan memunculkan alert untuk
  double-check, tetapi tidak menjadi pasangan DDI, kontraindikasi, intervensi
  HIGH_RISK, atau HOLD.

## Hasil cocok dan aktif (18 produk)

| Kode | Obat RS | Kategori lokal |
|---|---|---|
| 3795 | ACARBOSE 100 MG | Antidiabetik oral |
| 1035 | METFORMIN 500 MG | Antidiabetik oral |
| 3895 | METFORMIN 850 MG | Antidiabetik oral |
| 3492 | GLIQUIDONE 30 MG TAB | Antidiabetik oral |
| 4427 | GLIMEPIRIDE 1 MG | Antidiabetik oral |
| 2947 | GLIMEPIRIDE 2 MG | Antidiabetik oral |
| 4056 | GLIMEPIRIDE 4 MG | Antidiabetik oral |
| 5719 | WARFARIN 2MG | Obat yang memengaruhi darah |
| 1176 | EPINEPHRIN INJ | Agonis adrenergik |
| 1375 | TIARYT TAB (amiodarone) | Antiaritmia |
| 221 | DIGOXINE 0,25 MG | Glikosida jantung |
| 3495 | NOVOMIX-30 FLEXPEN | Insulin |
| 5258 | RYZODEG FLEXPEN | Insulin |
| 5264 | SANSULIN LOG G DISPOPEN | Insulin |
| 3177 | SANSULIN RAPID | Insulin |
| 3452 | MST CONTINUS 10MG | Narkotika/opioid |
| 175 | CODEIN 15 MG | Narkotika/opioid |
| 176 | CODEIN 20 MG | Narkotika/opioid |

## Kandidat pembanding, belum aktif (2 produk)

| Kode | Obat RS | Alasan kandidat |
|---|---|---|
| 5758 | GLICLAZIDE 60MG | Sulfonilurea oral pada ISMP 2024; tidak tertulis pada daftar lokal 2023 |
| 771 | TRADOSIK CAP (tramadol) | Opioid semua rute pada ISMP 2024; tidak tertulis pada daftar narkotika lokal 2023 |

## Tidak dibuatkan entri

- Sediaan yang tidak ada di master 221 obat RS, termasuk elektrolit konsentrat
  injeksi, heparin, propofol, oksitosin, atrakurium, rokuronium, methotrexate,
  dan media kontras.
- ASAM TRANEKSAMAT tablet tidak dimasukkan karena daftar ISMP 2024 menyebut
  sediaan injeksi.
- ASAM FOLAT/KSR/ASPAR K tidak dianggap sebagai elektrolit konsentrat injeksi.
- Seluruh LASA dan obat risiko jatuh dikecualikan.

## Penerapan lokal

- Schema database aktif: `0008_sprint8`.
- Diimpor: 20 entri; 18 aktif dan 2 kandidat nonaktif.
- Validator/auditor lokal: akun `admin` (`Fauzi_pharmacist`).
- Backup sebelum impor:
  `pre-high-alert-import-20260804-141716-emss.db`.
- SHA-256 backup:
  `4A3B2E9EE752F611E6CAC4F2CC0ACD66746F0A7522B3C7E9373F335CC9A38AD6`.
- Uji salinan database: ACARBOSE menghasilkan `HIGH_ALERT / REVIEW`, dengan
  `pair_count = 0` dan `interaction_count = 0`; rantai audit tetap valid.

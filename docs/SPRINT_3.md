# Sprint 3 — Master DDI dan Knowledge Base

## Tujuan

Menyediakan pengelolaan master interaksi obat yang dapat diaudit, diimpor,
ditambah langsung, diberi versi, ditinjau, disetujui, dipublikasikan,
dinonaktifkan, dan di-rollback. Sprint ini belum menjalankan rule terhadap
resep; DDI engine dan prescription hash merupakan Sprint 4.

## Komponen

- `knowledge_base_version`: identitas dan lifecycle versi.
- `knowledge_base_transition`: riwayat keputusan workflow.
- `ddi_rule`: pasangan zat aktif kanonik dan isi klinis.
- `DdiImportService`: preview, validasi, staging, backup, dan commit.
- `KnowledgeBaseService`: input langsung, duplikasi versi, workflow, rollback.
- UI **Knowledge Base & Master DDI** serta **Import DDI**.
- `templates/ddi_import_template.xlsx`: template input yang dapat diunduh.

## Model keselamatan

- A+B identik dengan B+A dan disimpan satu kali.
- Import selalu menghasilkan DRAFT dan `is_enabled = false`.
- Rule HOLD wajib diselesaikan sebelum review versi.
- Hanya rule interaksi positif dalam versi PUBLISHED yang dapat aktif.
- No-interaction, NOT_ASSESSABLE, dan EXCLUDED tidak menjadi alert aktif.
- `NO_INTERACTION_QUICK_CLOSURE` tetap dibedakan dari bukti no-interaction
  terkonfirmasi dan tidak boleh sendirian menghasilkan SAFE.
- Publikasi versi baru me-retire versi published sebelumnya.
- Rollback membutuhkan role berwenang dan alasan yang diaudit.

## Severity

| Severity sumber | Rank | Status aplikasi |
|---|---:|---|
| NONE | 0 | tidak ada alert positif |
| MINOR | 1 | INFO |
| SIGNIFICANT | 2 | REVIEW |
| SERIOUS | 3 | HIGH_RISK |
| CONTRAINDICATED | 4 | CRITICAL |

Pemetaan ini tersimpan eksplisit dan dapat dikembangkan pada sprint berikutnya.

## Data awal

Workbook `MASTER_DDI_KHANZA_APLIKASI_v1.0.0_2026-07-24 (1).xlsx` telah dimuat:

- 221 master obat dan 159 bahan aktif;
- 240 mapping komponen masih `PENDING_REVIEW` dan inactive;
- 5.410 pasangan DDI sebagai `DRAFT`;
- 543 interaksi positif;
- 3.646 pasangan assessed-no-interaction, termasuk 1.141 quick-closure;
- 975 NOT_ASSESSABLE;
- 246 EXCLUDED;
- 164 HOLD belum selesai;
- 0 rule aktif.

Tidak ada mapping atau rule yang disetujui/dipublikasikan otomatis.

## Acceptance criteria

- Migrasi dari Sprint 2 mempertahankan akun dan data.
- Pasangan terbalik menghasilkan canonical pair yang sama.
- Duplikasi pasangan per versi ditolak.
- Severity dan status interaksi divalidasi konsisten.
- Referensi zat aktif yang tidak dikenal ditolak.
- Formula dan file tidak aman ditolak.
- Preview tidak mengubah master.
- Backup terverifikasi dibuat sebelum commit.
- Commit bersifat transaksional dan menghasilkan DRAFT.
- Workflow dan rollback berbasis role serta diaudit.
- Seluruh test lulus dan coverage core minimal 85%.

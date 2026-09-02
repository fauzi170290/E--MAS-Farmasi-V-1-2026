# Sprint 21 — UAT Release-Candidate Dossier

Versi 0.28.0 menambahkan dossier evidence-bound untuk menyiapkan UAT release
candidate. Dossier tidak menjalankan UAT dan tidak membuat bukti rumah sakit.

## Binding candidate

`IT_ADMIN`/`SUPER_ADMIN` memilih `release-qualification.json` berstatus
`QUALIFIED` dan installer final. Service memverifikasi format, versi, Alembic
schema aktif, artifact manifest, nama installer, dan SHA-256 isi installer.
Candidate terikat immutable ke environment UAT dan expiry 1–30 hari.

## Readiness evidence wajib

- `SITE_APPROVAL` — lokasi UAT disetujui;
- `TEST_DATA_APPROVAL` — data uji anonim/de-identified;
- `USER_ROSTER` — seluruh pengguna memakai named account;
- `CLEAN_HOST` — host representatif telah diverifikasi;
- `BACKUP_RESTORE` — prosedur backup/restore diverifikasi;
- `KHANZA_READ_ONLY` — hak akses hanya `SELECT`;
- `TRAINING_SOP` — pelatihan dan SOP tersedia.

Setiap JSON memakai format `EMSS_UAT_READINESS_EVIDENCE_V1`, status `PASS`,
binding versi/schema/installer, timestamp ber-timezone, field kontrol bernilai
`true`, dan optional `valid_until`. Evidence stale, expired, invalid, atau
memuat key identitas pasien ditolak. Isi evidence tidak disalin ke database;
hanya nama file, waktu, recorder, dan SHA-256 yang disimpan immutable.

## Attestation dan kit

Attestation klinis dan teknis diberikan akun berbeda yang bukan creator atau
recorder evidence. Snapshot evidence diikat saat attestation pertama dan harus
tetap sama. Setelah dua attestation tersedia, dossier menjadi `SEALED`.

Kit ZIP dapat diekspor sebelum eksekusi. Manifest selalu menyatakan:

```json
{
  "execution_status": "NOT_STARTED",
  "production_authorization": "NOT_GRANTED_BY_UAT_KIT"
}
```

Seluruh scenario mempunyai result `NOT_RECORDED`. Kit adalah rencana pengujian,
bukan bukti bahwa UAT telah dilaksanakan.

## Migrasi

Migrasi `0024_uat_release_candidate_dossier` menambah candidate, readiness
evidence, dan ledger hash-chain. Downgrade ke `0023` menghapus data Sprint 21
saja dan mempertahankan seluruh tabel serta ledger lama.

Status setelah Sprint 21 adalah **UAT dossier software-ready — external
readiness evidence pending**.

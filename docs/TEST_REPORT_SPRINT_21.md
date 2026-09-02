# Test Report 0.28.0 — UAT Release-Candidate Dossier

## Status

**SPRINT 21 SOFTWARE VERIFIED — EXTERNAL READINESS EVIDENCE PENDING**

Sprint 21 membuktikan candidate hanya dapat dibuat dari qualification
`QUALIFIED` dan installer dengan checksum exact. Readiness evidence wajib
lengkap, fresh, non-PHI, dan immutable sebelum dua attestation independen dapat
menjadikan dossier `SEALED`.

Regression Sprint 21 kemudian digabungkan ke final verification 0.29.0:

- seluruh test final: 248 lulus;
- total branch coverage: 88%;
- Alembic single head final: `0025_uat_execution_acceptance`;
- downgrade 0025→0024 mempertahankan dossier Sprint 21;
- downgrade 0024→0023 mempertahankan seluruh data legacy;
- lifecycle 0020→0025→0020→0025: PASS.

Kit UAT tidak memuat hasil sintetis. Manifest selalu `NOT_STARTED`, seluruh
scenario `NOT_RECORDED`, dan tidak memberikan production authorization.

Sprint 21 tidak menyatakan dossier rumah sakit `SEALED`; evidence serta akun
attestor aktual belum tersedia.

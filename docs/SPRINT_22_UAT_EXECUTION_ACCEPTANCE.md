# Sprint 22 — UAT Execution & Independent Acceptance

Versi 0.29.0 menyediakan workflow pencatatan UAT eksternal dari dossier
`SEALED`. Aplikasi tidak menjalankan langkah uji, tidak mengubah Khanza, tidak
memasang software, dan tidak mengisi PASS otomatis.

## Scenario wajib

Klinis:

- DDI CRITICAL;
- HIGH_RISK;
- duplicate therapy;
- high-alert dan LASA.

Teknis:

- Khanza read-only;
- polling dan reconnect;
- clean install;
- upgrade dan preservasi data;
- backup dan restore;
- silent mode, access control, dan audit.

Result JSON memakai format `EMSS_UAT_EXECUTION_RESULT_V1`, exact binding ke
candidate/session/release/installer, status `PASS`, `FAIL`, atau `BLOCKED`,
observed time di dalam window, serta ringkasan hasil. Ringkasan hanya disimpan
sebagai hash. Setiap attempt append-only; attempt terbaru per scenario yang
menentukan gate.

## Issue, sign-off, dan keputusan

Issue `WARNING`/`CRITICAL` menyimpan summary dan resolution sebagai SHA-256.
Issue baru, remediasi, atau result baru membatalkan sign-off lama.

Acceptance memerlukan:

- seluruh latest scenario result `PASS`;
- tidak ada issue terbuka;
- dossier dan kedua ledger valid serta belum expired;
- sign-off klinis dan teknis independen dari tester/creator;
- decision maker `DIREKTUR` berbeda dari semua preparer, tester, issue handler,
  attestor, dan signatory.

`REJECT` dapat dipilih sebagai fail-safe. Acceptance dapat dicabut dengan
alasan ber-hash. State terminal dan ledger dilindungi trigger database.

## Receipt dan batas kewenangan

Receipt hanya tersedia saat acceptance masih aktif dan memuat:

```json
{
  "execution_origin": "EXTERNAL_HOSPITAL_EVIDENCE",
  "production_authorization": "NOT_GRANTED_BY_UAT_ACCEPTANCE"
}
```

Receipt membuktikan apa yang dicatat dan diikat oleh workflow; receipt tidak
menjamin kebenaran bukti eksternal tanpa review rumah sakit dan bukan izin
produksi.

## Migrasi

Migrasi `0025_uat_execution_acceptance` menambah session, result attempts,
issues, dan execution ledger. Downgrade ke `0024` mempertahankan dossier Sprint
21; downgrade lanjutan ke `0023` tetap mempertahankan seluruh data legacy.

Status software setelah Sprint 22 adalah **Ready for external UAT execution**.
Status **UAT PASSED** hanya boleh dinyatakan setelah evidence aktual di-intake,
dua sign-off akun individual tersedia, dan pihak independen memilih `ACCEPT`.

# Sprint 4 — DDI Engine dan Prescription Revision

## Tujuan

Menjalankan master DDI terhadap resep lokal secara deterministik, menyimpan
hasil beserta riwayat revisinya, dan menyediakan simulator aman sebelum
integrasi baca SIMRS Khanza.

## Alur engine

1. Validasi semua item resep, termasuk kelompok racikan.
2. Ambil mapping obat untuk seluruh kode Khanza dalam satu query.
3. Uraikan obat kombinasi menjadi zat aktif.
4. Bentuk zat aktif unik dan pasangan `n(n-1)/2`.
5. Hilangkan pasangan dari item obat yang sama dan canonical-kan A+B = B+A.
6. Ambil seluruh rule pasangan dalam satu batch query.
7. Klasifikasikan pair, hitung risiko tertinggi, dan nilai kelengkapan.
8. Simpan resep, revision, item, hasil, pair, dan issue secara transaksional.

## Identitas dan revisi

Identitas hasil adalah:

`no_resep + prescription_hash + knowledge_base_version + mode`

Hash mencakup kode Khanza, zat aktif, jumlah, aturan pakai, rute, kelompok
racikan, dan komponen. Urutan item tidak memengaruhi hash.

- Hash dan versi yang sama: hasil lama digunakan ulang, tanpa duplikasi.
- Isi resep berubah: revision baru dibuat dan revision lama dipertahankan.
- Versi knowledge base berubah: skrining baru dibuat.

## Dua dimensi hasil

Risiko klinis:

`SAFE < INFO < REVIEW < HIGH_RISK < CRITICAL`

Kelengkapan asesmen:

`COMPLETE < NOT_ASSESSED < UNMAPPED < INCOMPLETE < ERROR`

Jika kelengkapan bukan `COMPLETE`, status utama memakai masalah kelengkapan,
sementara tingkat risiko tetap ditampilkan. Karena itu hasil seperti
`CRITICAL + UNMAPPED` dapat terlihat bersamaan.

## Batas keselamatan

- Mode normal hanya memakai knowledge base `PUBLISHED`.
- Mode normal hanya memakai mapping obat `APPROVED` dan komponen aktif.
- Quick-closure bukan bukti aman dan menjadi `PAIR_NOT_ASSESSED`.
- NOT_ASSESSABLE, EXCLUDED, rule tidak aktif, dan rule tidak ditemukan tidak
  boleh menghasilkan klaim SAFE.
- Komponen dalam obat kombinasi yang sama tidak diperiksa satu sama lain.
- Mode MOCK hanya aktif pada environment development/test.
- Semua nomor resep simulasi berawalan `MOCK-`.
- Simulator tidak membaca atau menulis database Khanza.

## Data tersimpan

- `prescription`
- `prescription_revision`
- `prescription_item`
- `screening`
- `screening_pair`
- `screening_issue`

Schema Alembic: `0004_sprint4`.

## Acceptance criteria

- Canonical hash stabil terhadap urutan item.
- Perubahan field klinis mengubah hash.
- Canonical pair terdeduplikasi.
- Query rule dilakukan secara batch.
- Interaksi tertinggi menentukan risiko.
- Kelengkapan dan risiko tersimpan terpisah.
- Hasil identik direuse; perubahan resep menghasilkan revision baru.
- Obat kombinasi/racikan ditangani tanpa self-pair.
- Mock DRAFT diblokir pada production.
- Seluruh regression test lulus dan coverage core minimal 85%.

# Sprint 1 — Fondasi

## Tujuan

Menyediakan fondasi lokal yang dapat dijalankan dan diuji sebelum master obat,
DDI, rule engine, serta integrasi Khanza ditambahkan.

## Komponen

- `config`: konfigurasi TOML nonsensitif dan struktur folder.
- `database`: SQLite, SQLAlchemy, pragma aman, dan Alembic.
- `security`: kebijakan serta hashing password Argon2id.
- `services`: pembuatan pengguna dan autentikasi.
- `audit`: pencatatan audit dengan hash berantai.
- `health`: status database, schema, folder, dan audit.
- `ui`: login serta health screen dasar.

## Batas keselamatan

- Tidak ada koneksi Khanza.
- Tidak ada fungsi menulis Khanza.
- Tidak ada status `SAFE`.
- Tidak ada rule klinis aktif.
- Tidak ada password bawaan.

## Acceptance criteria

- Migrasi dapat dijalankan dari database kosong.
- Sepuluh role sistem tersedia.
- Administrator pertama dibuat tanpa password command line.
- Password tidak tersimpan plaintext.
- Login benar berhasil dan login salah diaudit.
- Lock sementara aktif setelah batas kegagalan.
- Foreign key, WAL, dan busy timeout aktif.
- Health check menghasilkan `READY` setelah migrasi.
- Test otomatis lulus.


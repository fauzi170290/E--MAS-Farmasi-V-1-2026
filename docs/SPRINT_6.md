# Sprint 6 — Adapter Khanza, Polling, Reconnect, dan Stability Check

## Hasil

Sprint 6 selesai pada batas yang ditetapkan: `MockKhanzaAdapter`,
`MySQLKhanzaAdapter`, polling, reconnect, serta pemeriksaan stabilitas resep.
Tidak ada fungsi Sprint 7 (intervensi apoteker) yang ditambahkan.

## Alur operasional

1. Worker menguji koneksi read-only.
2. Worker membaca header baru/berubah memakai cursor `(changed_at, no_resep)`.
3. Header, item reguler, dan komponen racikan dibaca sebagai snapshot.
4. Setelah jeda singkat, snapshot dibaca kembali.
5. Fingerprint identik diproses oleh DDI engine dan masuk antrean Sprint 5.
6. Snapshot berubah diulang sampai batas; sesudah itu status `INCOMPLETE`.
7. Koneksi gagal menjadi `DISCONNECTED` dan reconnect dijadwalkan dengan
   exponential backoff 5, 10, 20, 40 detik hingga batas konfigurasi.

Cursor hanya maju setelah setiap resep telah diwakili oleh hasil, `INCOMPLETE`,
atau `ERROR`, sehingga kegagalan tidak dinyatakan aman dan tidak menyebabkan
full table scan berulang.

## Keamanan Khanza

- Semua query aplikasi diawali `SELECT` dan menggunakan parameter binding.
- Nama view divalidasi hanya berupa huruf, angka, dan underscore.
- Session MySQL disetel `TRANSACTION READ ONLY` pada setiap koneksi pool.
- e-MSS tidak memiliki method untuk menulis, menghapus, atau mengubah Khanza.
- Password hanya dibaca dari `EMSS_KHANZA_PASSWORD`.
- Pesan error disanitasi menjadi tipe error; URL/kredensial tidak disimpan.

Kontrak kolom dan prosedur DBA ada di
`docs/KHANZA_VIEW_CONTRACT_SPRINT_6.md`.

## Schema lokal

Alembic `0006_sprint6` menambahkan:

- `integration_state`: status koneksi, cursor, kegagalan beruntun, jadwal retry;
- `polling_run`: histori run dan jumlah terdeteksi/stabil/diproses/gagal.

Tidak ada kredensial dan tidak ada salinan tabel Khanza pada kedua tabel ini.

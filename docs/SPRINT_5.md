# Sprint 5 — Antrean, Alert, Panel, Tray, dan Single Instance

## Tujuan

Menyediakan panel operasional yang selalu tersedia berdampingan dengan Khanza,
mengelompokkan hasil skrining per resep, dan memberi alert sesuai prioritas
tanpa mengubah atau mengambil fokus dari SIMRS Khanza.

## Komponen

- `processing_queue`: status proses, review, prioritas, retry, dan dead-letter.
- `alert_event`: satu kejadian alert gabungan per resep.
- `ProcessingQueueService`: enqueue idempoten, filter, detail, review, retry.
- `route_alert`: routing risiko dan kelengkapan menjadi perilaku notifikasi.
- UI **Antrean & Alert**: daftar resep, filter depo/status, dan detail hasil.
- `SystemTrayController`: buka, sembunyikan, keluar, dan notifikasi ringan.
- `SingleInstanceGuard`: instance kedua meminta instance pertama tampil.
- `WorkstationAccessService`: Mode Farmasi tanpa password.
- Skrip autostart Windows.

## Logika alert

| Hasil | Perilaku |
|---|---|
| SAFE | status hijau, tanpa pop-up |
| INFO | riwayat saja |
| REVIEW | toast kuning, tidak mengambil fokus |
| HIGH_RISK | alert menetap pada antrean, review diperlukan |
| CRITICAL | alert merah dan HOLD RECOMMENDED |
| NOT_ASSESSED | belum dapat dinyatakan aman |
| UNMAPPED | alert menetap; obat perlu mapping |
| INCOMPLETE | alert menetap; data belum lengkap/stabil |
| ERROR | gagal proses; tidak boleh menampilkan SAFE |

Jika risiko dan kelengkapan sama-sama bermasalah, keduanya tetap disimpan dan
ditampilkan. Alert dipilih dari prioritas tertinggi. CRITICAL tetap membawa
HOLD RECOMMENDED, tetapi tidak membatalkan atau mengubah resep Khanza.

## Mode Farmasi

- Diaktifkan melalui `allow_workstation_mode = true`.
- Memerlukan administrator pertama sudah tersedia.
- Tidak meminta password untuk membuka panel operasional.
- Menggunakan identitas sistem terkunci yang tidak dapat login melalui form.
- Tidak dapat mencatat review atas nama apoteker tertentu.
- Import/perubahan master tetap read-only; login akun berwenang diperlukan.
- Intervensi klinis Sprint 7 tetap akan meminta identitas petugas.

## Ketahanan proses

- Screening yang sama hanya menghasilkan satu item antrean.
- Seluruh pasangan dan issue digabung pada satu detail resep.
- Kegagalan dapat dicatat sebagai ERROR.
- Retry manual dibatasi `max_attempts`.
- Percobaan melampaui batas menjadi `DEAD_LETTER`.
- Single-instance mencegah polling/tray ganda.

## Batas Sprint 5

Antrean saat ini menerima hasil simulator Sprint 4. Adapter MySQL Khanza,
polling, reconnect, cursor waktu, dan stability check merupakan Sprint 6.
Database Khanza tetap `NOT_CONFIGURED` dan tidak ditulis.

Schema Alembic: `0005_sprint5`.

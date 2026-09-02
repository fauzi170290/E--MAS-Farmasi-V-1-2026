# Shift Closeout & Pilot Session Ledger

Versi 0.19.0 menambahkan batas sesi operasional di atas aktivasi Advisory Pilot.
Aktivasi adalah otorisasi teknis; shift adalah masa tugas pemilik klinis. Shift
baru berlaku maksimal 12 jam dan selalu berakhir paling lambat pada expiry
aktivasi.

## Peran dan alur handover

1. Petugas incoming dengan role Apoteker, KFT, atau Clinical Reviewer memilih
   **Ambil Alih Shift Klinis**. Sistem mengambil snapshot agregat outstanding
   dan mencatat incoming attestation.
2. Pemilik klinis aktif meninjau jumlah alert, alert CRITICAL, dan intervensi
   terbuka lalu memilih **Attestasi Outgoing Shift**.
3. IT Admin atau Super Admin memilih **Sahkan Handover IT**. Dalam satu
   transaksi, sistem menutup shift lama, mencabut aktivasi lama, membuat
   aktivasi/shift baru, dan menulis ledger.

Ketiga tindakan wajib memakai akun sesuai peran. Incoming dan outgoing harus
berbeda; pengesah teknis juga berbeda dari pemilik klinis baru. Permintaan
berlaku 30 menit. Aktivasi lama tetap aktif sampai tahap ketiga berhasil.

## Closeout tanpa handover

Pemilik klinis aktif dapat memilih **Tutup Shift Klinis**, mengisi catatan
attestation 10-300 karakter, lalu mengonfirmasi. Sistem mencabut aktivasi,
membatalkan permintaan otorisasi yang masih tertunda, menyimpan snapshot
outstanding, dan menulis event `SHIFT_CLOSED`.

IT tetap dapat memakai **Nonaktifkan Advisory Pilot** untuk penghentian teknis.
Emergency stop tetap tersedia bagi role berwenang dan selalu lebih prioritas.

## Ringkasan outstanding dan privasi

Snapshot handover/closeout hanya memuat:

- jumlah alert non-MOCK berstatus `NEW` atau `SHOWN`;
- jumlah alert CRITICAL yang belum diakui;
- jumlah intervensi non-MOCK berstatus `OPEN`;
- waktu snapshot, scope, dan checksum SHA-256.

Nomor resep, rekam medis, nama pasien, unit, pesan alert, dan catatan klinis
tidak disalin ke ledger atau record closeout.

## Ledger immutable dan audit

Tabel `advisory_pilot_session_ledger` adalah append-only dan memakai rantai
`previous_hash`/`entry_hash`. Setiap append juga membuat event pada audit utama.
Constraint mencegah cabang rantai, sedangkan trigger SQLite menolak UPDATE dan
DELETE. Record closeout final dilindungi trigger yang sama. Verifikasi ledger
dilakukan sebelum daftar ledger ditampilkan di UI.

## Fail-safe expiry

Sebelum setiap alert Advisory, aplikasi mengevaluasi ulang status. Alert ditahan
dan aktivasi dicabut bila:

- expiry aktivasi telah lewat (`ACTIVATION_EXPIRED`); atau
- expiry shift telah lewat (`SHIFT_EXPIRED`); atau
- gate/binding bukti berubah; atau
- emergency stop aktif/status tidak dapat diverifikasi.

Shift yang kedaluwarsa tidak dapat di-attest atau disahkan. Handover baru atau
aktivasi baru wajib dilakukan sesuai status gate.

## Migrasi dan rollback

Upgrade ke `0016_shift_closeout_ledger` menambah kolom shift nullable, lalu
backfill aktivasi legacy menggunakan `activated_at` dan `expires_at`. Data
aktivasi 0.18.0 tidak dihapus atau diubah statusnya oleh migrasi.

Rollback teruji ke `0015_two_person_advisory`: trigger dan tabel baru dilepas,
kolom tambahan dihapus, sedangkan pengguna, kampanye, UAT, dan aktivasi legacy
tetap ada. Sebelum rollback produksi, buat backup terverifikasi dan hentikan
aplikasi pada seluruh workstation.

## Checklist UAT pilot

- Verifikasi tombol handover hanya aktif bagi petugas incoming yang bukan owner.
- Verifikasi IT tidak dapat menyahkan sebelum outgoing attestation.
- Cocokkan jumlah outstanding pada UI dengan antrean/intervensi non-MOCK.
- Verifikasi owner dapat closeout dan pengguna lain ditolak.
- Majukan waktu uji melewati shift expiry dan pastikan alert ditahan.
- Buka Ledger Sesi Pilot dan pastikan rantai dinyatakan valid.
- Jalankan backup, downgrade ke 0015, upgrade kembali ke 0016, lalu verifikasi
  data legacy dan audit.

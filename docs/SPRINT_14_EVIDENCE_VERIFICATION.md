# Evidence Verification & Chain of Custody

Versi 0.21.0 menambahkan pemeriksaan paket bukti sesi pilot sebelum arsip
dipakai dalam review klinis, audit internal, atau serah terima pilot. Verifier
tidak mengekstrak arsip ke filesystem dan tidak mempercayai nama, ukuran,
manifest, atau CSV sebelum seluruh batas keselamatan diperiksa.

## Alur verifikasi

1. Petugas berwenang memilih ZIP melalui **Verifikasi Paket Bukti**.
2. Aplikasi membaca satu snapshot byte dan menghitung SHA-256 paket.
3. Struktur ZIP diperiksa terhadap allowlist tiga file, batas 20 MiB, batas
   ukuran member, jumlah entry, symlink, enkripsi, dan rasio kompresi.
4. Manifest `EMSS_PILOT_EVIDENCE_V1` serta checksum kedua CSV divalidasi.
5. Header dan isi CSV diparse secara ketat. Sequence, `previous_hash`, payload
   JSON kanonik, `entry_hash`, head hash, dan jumlah entri dihitung ulang.
6. Header, waktu, angka agregat, ID unik, dan summary hash closeout diperiksa.
7. Hasil `VALID` atau `INVALID` disimpan dan diaudit secara append-only.

Verifier menerima provenance aplikasi/schema lama selama paket tetap memakai
format V1 dan seluruh kontrol integritas lulus. Ini mempertahankan kompatibilitas
data tanpa menganggap paket lama berasal dari runtime saat ini.

## Arti hasil

- `VALID`: paket konsisten secara internal dengan manifest dan hash chain.
- `INVALID`: satu atau lebih kontrol gagal; UI menampilkan hanya kode error yang
  ditentukan aplikasi, bukan metadata atau isi bebas dari paket.

SHA-256 chain tidak membuktikan identitas pembuat dan bukan tanda tangan
digital. Serah terima tetap harus memakai media resmi, kontrol akses, checksum
yang dicatat saat ekspor, serta prosedur organisasi.

## Chain of custody dan audit

Tabel `pilot_evidence_verification` menyimpan nama file dasar, checksum paket,
provenance manifest yang tervalidasi tipenya, head hash, jumlah data, hasil,
kode error, petugas, dan waktu. Trigger SQLite menolak UPDATE dan DELETE.
Event `PILOT_EVIDENCE_PACKAGE_VERIFIED` juga ditambahkan ke audit chain utama.

Input bebas dari ZIP tidak pernah dimasukkan ke audit. Paket hilang, tidak bisa
dibaca, terlalu besar, atau bukan ZIP tetap menghasilkan catatan `INVALID`
dengan kode terkontrol bila permintaan dilakukan oleh petugas berwenang.

## Operasional dan rollback

- Jangan membuka paket invalid dengan aplikasi arsip pada workstation klinis.
- Isolasi media sumber dan simpan checksum hasil verifikasi untuk insiden.
- Paket invalid tidak mengubah ledger lokal, aktivasi, atau status karantina.
- Backup database terverifikasi wajib sebelum migrasi atau rollback produksi.

Migrasi `0018_evidence_verification` hanya menambah tabel dan trigger baru.
Rollback ke `0017_pilot_ledger_quarantine` menghapus riwayat verifikasi, tetapi
tidak mengubah pengguna, aktivasi, ledger, closeout, atau karantina 0.20.0.
Ekspor riwayat audit sesuai kebijakan retensi sebelum rollback bila diperlukan.

## Checklist UAT

- Verifikasi paket asli dan cocokkan checksum dengan hasil ekspor.
- Ubah satu byte ledger; pastikan hasil invalid dan audit tetap valid.
- Uji arsip dengan extra/path traversal, symlink, dan data sangat kompresibel.
- Pastikan tidak ada file yang diekstrak ke filesystem.
- Pastikan riwayat valid/invalid tidak dapat diubah atau dihapus.
- Upgrade dari 0017, downgrade ke 0017, lalu upgrade kembali pada salinan data.

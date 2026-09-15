# Backlog alert asesmen belum lengkap dan overlay resep

Tanggal pencatatan: 15 September 2026  
Status: **IMPLEMENTED — THREE DELTAS (15 September 2026); installer tidak dibangun**

Dokumen ini adalah catatan hasil pemeriksaan production lokal yang dilakukan
read-only. Pencatatan ini tidak mengubah database E-MAS, data Khanza, mapping,
knowledge base, konfigurasi, status publikasi, atau binary terpasang.

## 1. Hasil skrining belum lengkap perlu indikator visual

### Temuan

Satu resep yang diperiksa selesai diproses oleh Desktop/JAB dan menghasilkan
zero DDI positif, tetapi terdapat obat belum dipetakan dan pasangan yang belum
dapat dinilai. Mesin sudah fail-safe: hasilnya `UNMAPPED`, bukan `SAFE`.

Aturan notifikasi saat ini mengirim kondisi ini sebagai `AUDIO` saja dengan
judul **Asesmen belum lengkap**. Ledger mencatat audio diterima backend, tetapi
tidak ada popup visual. Akibatnya pengguna yang tidak mendengar audio tidak
mendapat konfirmasi bahwa resep telah diskrining namun belum lengkap.

### Perubahan yang diminta untuk tahap berikutnya

Tambahkan popup visual khusus **ASESMEN BELUM LENGKAP** untuk hasil tanpa DDI
positif yang berstatus `UNMAPPED` atau `NOT_ASSESSED`.

- Popup harus menyatakan bahwa skrining dilakukan tetapi belum lengkap.
- Popup bukan popup DDI positif dan tidak boleh menggunakan wording SAFE,
  `NO_INTERACTION`, atau "tidak ada interaksi".
- Audio incomplete yang sudah ada tetap dipertahankan; popup adalah kanal
  visual tambahan, bukan pengganti suara.
- Tampilkan alasan yang tersedia secara terstruktur, misalnya jumlah obat
  belum dipetakan dan pasangan belum dinilai, tanpa menciptakan fakta klinis
  baru.
- Hormati deduplikasi resep/revisi, gate operasional, silent pilot, RBAC, dan
  prinsip satu notifikasi utama per evaluasi.

### Kriteria penerimaan minimum

1. `UNMAPPED`/`NOT_ASSESSED` dengan nol DDI positif menghasilkan audio
   incomplete dan popup visual incomplete.
2. Hasil tersebut tidak pernah diklasifikasikan atau ditampilkan sebagai SAFE.
3. DDI positif tetap memakai popup klinisnya sendiri dengan prioritas lebih
   tinggi.
4. Kegagalan audio tidak menghilangkan popup visual; popup tidak bergantung
   pada persepsi bahwa suara terdengar.
5. Tambahkan regression test untuk routing audio + popup incomplete.

### Implementasi delta 1

- Untuk Desktop/JAB, hasil `UNMAPPED` atau `NOT_ASSESSED` tanpa DDI positif
  kini merutekan satu popup **ASESMEN BELUM LENGKAP** dan satu audio
  `screening-incomplete`.
- Pesan hanya menerangkan fakta tersimpan: jumlah obat belum dipetakan dan/atau
  pasangan belum dinilai. Tidak ada wording SAFE atau teks klinis baru.
- Popup tetap independen dari keberhasilan audio.

## 2. Overlay tidak terlihat meski popup DDI ditampilkan

### Bukti yang tersedia

Resep terakhir yang diperiksa memiliki lima DDI positif dan menghasilkan popup
persisten serta audio. Event alert tersimpan sebagai `SHOWN`. Konfigurasi
terpasang menyatakan sumber `desktop` dan `khanza_desktop_overlay_poc = true`;
binary bridge x86/x64 juga tersedia pada instalasi yang baru.

Karena itu, masalah ini bukan kegagalan skrining, publikasi knowledge base, atau
gagalnya popup.

### Penyebab teknis yang terisolasi

Overlay adalah lapisan presentasi sekunder yang hanya hidup di memori proses.
Setelah popup, overlay baru boleh digambar jika bridge masih mengirim geometri
tabel resep yang stabil, identitas resep/fingerprint cocok, baris DDI dapat
dicocokkan, dan guard fokus/window/DPI lulus. Bila salah satu bukti itu berubah
atau tidak dapat diverifikasi, overlay sengaja disembunyikan agar tidak
menandai baris yang salah.

Pada instalasi ini, alasan `overlay_clear`/`overlay_hidden` runtime tidak
dipersistenkan. Log aplikasi juga kosong untuk periode kejadian. Dengan bukti
saat ini, penyebab spesifik (geometri tidak tersedia, identitas tidak cocok,
seleksi Khanza berubah, atau guard fokus/DPI) tidak dapat dibedakan setelah
kejadian. Kesenjangan observabilitas tersebut adalah bagian dari backlog.

### Perubahan yang diminta untuk tahap berikutnya

1. Pertahankan hasil overlay yang sudah lolos untuk resep dan fingerprint
   aktif selama tampilan resep Khanza masih terbukti sama; jangan hilangkan
   hanya karena popup/audio dipresentasikan.
2. Tetap fail-closed: sembunyikan overlay segera bila identitas, geometri,
   fokus window, DPI, atau baris resep tidak lagi dapat dibuktikan aman.
3. Tambahkan telemetry minimal non-PHI untuk tiap keputusan overlay, misalnya
   reason-code, no-resep yang di-hash, fingerprint yang di-hash, jumlah baris
   geometri/proyeksi/match, dan waktu. Jangan merekam nama pasien, nama obat,
   credential, atau isi JAB mentah.
4. Tambahkan status kesehatan overlay yang membedakan `GEOMETRY_READY`,
   `PROJECTION_READY`, `VISIBLE`, dan reason-code penolakan terakhir.
5. Uji end-to-end menggunakan resep uji yang memiliki DDI positif: popup,
   audio, dan penanda baris tetap muncul bersamaan; lalu uji perubahan seleksi,
   pindah resep, DPI berbeda, dan geometri ambigu untuk membuktikan overlay
   menghilang secara aman.

### Batas keselamatan

Overlay tidak boleh menjadi syarat munculnya popup/audio, tidak boleh
menghambat jalur klinis utama, dan tidak boleh memakai klik, input, OCR,
screenshot extraction, atau write ke Khanza.

### Implementasi delta 2

- Event JAB *selection* tidak lagi menghapus overlay yang telah lolos validasi
  untuk resep, fingerprint, dan geometri yang sama. Event tersebut tetap
  meminta rescan.
- Perubahan data terlihat, model tabel, atau nilai tetap menghapus overlay;
  guard identitas, geometri, fokus window, DPI, dan kecocokan baris tetap
  fail-closed.
- Telemetri persistensi reason-code yang dicatat pada rencana di atas belum
  termasuk dalam tiga delta ini dan tetap backlog terpisah.

## 3. Riwayat Pemeriksaan memakai snapshot Efek Klinis published

### Implementasi delta 3

- Kolom visual `Unit/Depo` dan `Peringatan` dihapus dari tabel antrean dan
  Riwayat Pemeriksaan.
- Kolom `Efek Klinis` ditambahkan pada detail pasangan obat. Nilainya adalah
  snapshot `clinical_effect` yang tersimpan saat skrining dari KB PUBLISHED;
  field kosong tetap kosong dan aplikasi tidak menyusun teks klinis fallback.
- Identitas Khanza, mapping, engine DDI, status publikasi, dan master KB tidak
  diubah oleh delta ini.

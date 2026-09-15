# Backlog pengelolaan DDI dan status koneksi Khanza

Tanggal pencatatan: 3 September 2026

Status implementasi: **SELESAI — rilis 1.0.3**

Dokumen ini mencatat permintaan dan hasil implementasi rilis 1.0.3. Perubahan
tidak mengubah keputusan klinis, data historis, atau struktur menu utama.

## 1. Filter dan pengurutan status pasangan interaksi obat

Pada **Data Referensi → Pasangan Interaksi Obat**, pengguna KFT dan
`SUPER_ADMIN` perlu dapat menyaring serta mengurutkan pasangan berdasarkan
status **Aktif** dan **Nonaktif** agar proses peninjauan dan pemeliharaan lebih
cepat.

Kriteria penerimaan awal:

- tersedia filter `Semua`, `Aktif`, dan `Nonaktif`;
- kolom status dapat diurutkan tanpa mengubah status pasangan;
- filter/pengurutan tidak menghilangkan data dan tidak mengubah hasil skrining;
- hak aktivasi/nonaktivasi tetap mengikuti role dan audit yang berlaku;
- pengujian mencakup pasangan aktif, nonaktif, hasil kosong, dan perpindahan
  filter setelah data diperbarui.

Hasil: tersedia filter `Semua status`, `Aktif`, dan `Nonaktif`; header tabel
tetap dapat dipakai untuk pengurutan. Ringkasan membedakan jumlah keseluruhan
dari jumlah yang sedang ditampilkan.

## 2. Tombol tertutup pada tampilan layar penuh

Pada tampilan layar penuh **Data Referensi → Pasangan Interaksi Obat**, masih
ada tombol yang tertutup atau keluar dari area yang dapat digunakan. Layout
perlu disesuaikan secara responsif tanpa mengubah struktur menu lain.

Kriteria penerimaan awal:

- seluruh tombol terlihat dan dapat diklik pada resolusi kerja rumah sakit;
- layout tetap dapat digunakan ketika Windows display scaling aktif;
- bila ruang vertikal tidak cukup, area konten menyediakan scroll yang benar;
- pengujian visual mencakup layar normal, layar penuh, dan scaling representatif.

Hasil: delapan aksi ditempatkan pada grid dua kolom dan halaman tetap berada
dalam scroll area utama. Pengujian UI memastikan empat baris tombol tetap
terlihat pada lebar kerja 1100 piksel.

## 3. Penanda warna koneksi Khanza

Status koneksi perlu terlihat langsung pada panel:

- **Terhubung**: panel/badge berwarna hijau;
- **Tidak terhubung**: panel/badge berwarna merah.

Warna tidak boleh menjadi satu-satunya informasi. Teks status dan, bila
tersedia, ikon tetap ditampilkan agar dapat dipahami pengguna dengan gangguan
penglihatan warna. Status transisi seperti menghubungkan ulang dapat memakai
warna netral dan tidak boleh dilaporkan sebagai terhubung.

Hasil: banner utama dan panel Koneksi Khanza memakai hijau untuk `CONNECTED`
serta merah untuk seluruh status belum/tidak terhubung. Teks status tetap
ditampilkan sehingga warna bukan satu-satunya penanda.

## 4. Catatan portabilitas backup lokal E-MAS

Backup E-MAS dapat dipindahkan untuk memulihkan database lokal pada PC lain,
dengan syarat versi aplikasi tujuan sama atau lebih baru dan paket backup tetap
lengkap. Paket terdiri dari file `.db`, `.manifest.json`, dan `.config.json`
dengan nama dasar yang sama.

Yang ikut dipulihkan adalah data dalam SQLite E-MAS, termasuk master, mapping,
knowledge base DDI, akun lokal, audit, hasil skrining, dan intervensi yang ada
pada saat backup. Restore menjalankan verifikasi checksum, pemeriksaan
integritas, safety backup, dan migrasi schema yang diperlukan.

Yang tidak ikut dipulihkan:

- database SIMRS Khanza;
- password koneksi `EMSS_KHANZA_PASSWORD`;
- environment variable Windows;
- konfigurasi jaringan/host yang harus disesuaikan pada PC tujuan;
- instalasi aplikasi dan izin Windows.

Sebelum pemindahan, buat dan verifikasi backup melalui aplikasi. Pada PC tujuan,
instal versi E-MAS yang kompatibel, salin ketiga file paket ke folder backup,
atur ulang konfigurasi serta credential Khanza, lalu lakukan **Verifikasi
Terpilih** dan **Restore Terpilih**. Setelah restart, periksa revisi schema,
jumlah master/mapping, akun, audit, dan koneksi Khanza. Jangan menyalin file
database aktif ketika aplikasi masih berjalan.

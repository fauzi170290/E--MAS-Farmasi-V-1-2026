# Persetujuan polling internal untuk UAT lokal

27 Agustus 2026. Setelah penjelasan interval 3 detik dan batasnya, pengguna menjawab **“ya setuju”** pada task ini.

Disetujui: e-MSS memeriksa sumber secara berkala setiap sekitar 3 detik, otomatis tanpa klik, dengan pemeriksaan kestabilan dua observasi minimal 2 detik. Ini polling internal, bukan push atau jaminan popup dalam 3 detik. Antrean popup, pemrosesan dan waktu query tetap dapat menambah latensi.

Persetujuan ini adalah keputusan desain untuk UAT lokal. Bukan persetujuan klinis/KFT, persetujuan deployment, izin mengubah database/view Khanza, atau aktivasi runtime RS. Tidak ada akun atau approval klinis yang dibuat sebagai pengganti persetujuan tersebut.

Konfigurasi terpisah tersedia di `config.uat-polling-3s.toml`: consent dan jadwal polling disetel, tetapi adapter tetap `disabled` sampai target clone sintetis dan mode yang sah ditetapkan. Tidak terhubung ke `sik`, tidak memakai mock, dan belum dijalankan. Environment `test` hanya untuk data sintetis terisolasi; jangan digunakan untuk meloloskan data pasien dari gate klinis. Default installer dan config RS tidak diubah.

Masih diperlukan: target clone/backup dan kontrak item FINAL, mapping/KB yang sah, izin distribusi dan uji persepsi audio, serta signature/waiver dan izin deployment sesuai lingkup berikutnya.

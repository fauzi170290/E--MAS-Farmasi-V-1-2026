# Uji Khanza lokal pada instalasi yang sama — 0.32.1

Pilihan ini khusus PC yang seluruh data Khanzanya telah dikonfirmasi pengguna sebagai data uji. Tidak membuat database E-MAS kedua, akun resep buatan, atau daftar pasien dummy. Data tetap berada di lokasi yang tercantum pada konfigurasi lama.

## Memasang

1. Tutup penuh E-MAS, termasuk tray. Jalankan installer EXE 0.32.1; tidak perlu CMD/PowerShell dan tidak perlu menghapus data.
2. Pada pilihan tugas tambahan, centang **UJI LOKAL: pakai database ini (bukan pelayanan)** pada kelompok **Polling aktif, kredensial Windows Machine**. Dengan memilihnya Anda mengonfirmasi PC dan seluruh data Khanza lokal hanya untuk uji. Pilihan ini tidak aktif secara default.
3. Setelah pemasangan, buka E-MAS seperti biasa dan pilih Mode Farmasi. Judul harus **E-MAS Farmasi — UJI LOKAL**. Banner harus menunjukkan tanggal mulai uji.
4. Pastikan Koneksi Khanza menunjukkan koneksi berhasil dan pemeriksaan otomatis aktif. Masukkan resep uji melalui Khanza, lalu lakukan validasi seperti alur biasa.

## Perubahan yang disetujui melalui pilihan installer

- `environment=test`, `khanza_adapter=mysql_local_test`, persetujuan uji lokal dan polling internal aktif.
- Koneksi wajib loopback (127.0.0.1/localhost/::1), memakai view Khanza yang sudah dikonfigurasi. Tidak mengubah skema/view, resep, stok, atau billing Khanza.
- Sumber kata sandi dipilih eksplisit dari environment Windows Machine. Kata sandi tidak disalin ke file atau mengganti environment proses/global. Jika tidak tersedia, koneksi gagal tanpa mencoba kredensial lain secara diam-diam.
- Pemantauan mencakup resep sejak tanggal pengaktifan uji. Pengulangan instalasi tidak memundurkan/mengganti tanggal tersebut secara otomatis. Tidak mengadopsi kegagalan lama di luar cakupan uji; riwayat lama tetap terlihat.
- Konfigurasi asli dicadangkan dengan nama `config.toml.before-local-test-<id>.bak` sebelum perubahan. Jalur/nama database, pengaturan audio, akun, dan data lama tidak dipindahkan. Kegagalan konfigurasi menahan peluncuran otomatis; periksa `local-test-setup.json` di folder data.

## Arti hasil uji

DDI tetap DRAFT, aturan tidak dipublikasikan, dan pemetaan tidak diberi persetujuan klinis otomatis. Data referensi tersebut boleh dipakai pada pemeriksaan TEST; hasil ditandai **UJI LOKAL**. Prefix internal untuk memisahkan hasil uji tidak mengubah nomor resep di Khanza.

Popup dan suara hanya untuk mayor/kontraindikasi setelah status validasi, melewati pembacaan stabil. Resep yang tidak berubah tidak memicu alarm berulang. Hasil nonberat tetap tercatat. Bila view belum menyediakan bukti komposisi akhir, hasil tetap menyebut data belum lengkap; keberadaan alert uji tidak membuktikan kesesuaian komposisi final.

Ini bukan mode pelayanan. Sebelum penggunaan pelayanan, lakukan peninjauan/publikasi klinis, verifikasi pemetaan dan kontrak view, serta pengaturan lingkungan yang sesuai. Jangan menganggap menghapus banner atau mengganti label sebagai validasi klinis.

Pengujian instalasi asli serta suara/popup pada desktop pengguna masih perlu dikonfirmasi pengguna; keberhasilan build, tes otomatis, atau pembacaan read-only bukan bukti bahwa suara telah terdengar.

Jika perlu kembali ke executable 0.32.0, simpan dahulu hasil uji dan pulihkan salinan konfigurasi sebelum pengaktifan uji. Versi 0.32.0 belum mengenal pengaturan `mysql_local_test`; jangan sekadar mengganti executable sambil memakai konfigurasi baru. Perubahan startup Windows per pengguna juga tetap memerlukan pemeriksaan setelah pemasangan, terutama bila UAC memakai akun administrator berbeda.

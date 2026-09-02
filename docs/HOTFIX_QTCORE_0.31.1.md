# Hotfix QtCore e-MSS 0.31.1 — 27 Agustus 2026

## Yang perlu dilakukan

1. Tutup e-MSS dan semua jendela error.
2. Jalankan installer **e-MSS-Farmasi-RS-Setup-0.31.1-x64.exe** dan setujui permintaan administrator Windows. Gunakan folder instalasi yang sama seperti versi lama.
3. Tidak perlu uninstall, reset, atau menghapus database. Installer mempertahankan konfigurasi ProgramData dan tidak mengganti database.
4. Buka e-MSS dari shortcut biasa. Login memakai akun lama; jangan membuat akun baru jika akun/data lama sudah ada.
5. Jika masih ada error atau data tampak kosong, hentikan penggunaan dan kirim screenshot error. Jangan membuat database baru atau mengganti DLL Windows.

Jika paket Repair QtCore sudah dijalankan, installer 0.31.1 tetap dapat dipasang. Jangan menginstal ulang installer 0.31.0 karena akan mengembalikan DLL yang bermasalah.

## Penyebab dan perubahan

Seluruh 343 file aplikasi terpasang cocok dengan build 0.31.0; bukan kegagalan penyalinan saat instalasi pengguna. PyInstaller mengambil icuuc.dll dari Poppler ICU78 pada PATH build. Qt6Core memerlukan ekspor ICU tanpa akhiran versi, sedangkan DLL asing menyediakan ekspor berakhiran _78. Windows System32 ICU menyediakan ekspor yang diperlukan.

Spec 0.31.1 mengecualikan icuuc.dll dan payload icudt DLL dari bundel. Saat upgrade, installer mengarantina hanya icuuc.dll dengan SHA-256 2882afacabd9d901762ab196c7a319b03051af39291e47fef51fcb69c26ab5b8 menjadi icuuc.dll.quarantined-0.31.0. Hash berbeda atau benturan cadangan menghentikan instalasi tanpa menimpa file tersebut. Tidak ada perubahan skema dari 0027_durable_monitor, seed, aturan DDI, polling, atau konfigurasi operasional.

## Verifikasi

- EXE frozen 0.31.0 pada data uji: gagal dengan Unhandled exception in script.
- Salinan EXE yang sama setelah karantina DLL: jendela login terlihat, keluar normal.
- Instalasi aktual 0.31.1 pada Program Files: seluruh 341 file cocok dengan build, DLL salah dikarantina, dan login terlihat dengan database uji terpisah. Agen tidak menjalankan pemasangan administrator.
- EXE frozen 0.31.1 baru: health READY, gui-smoke READY, platform Windows, dan login GUI asli terlihat.
- Uji negatif: memasukkan kembali DLL salah ke salinan 0.31.1 menghasilkan laporan ImportError/exit 1; tes GUI baru mendeteksi kegagalan yang dilewatkan health CLI.
- Lima kasus kode upgrade installer dan lima kasus kode repair lulus pada folder uji: DLL dikenal, tidak ada, tidak dikenal, benturan cadangan, dan sudah diperbaiki. Harness memakai kode Pascal yang sama; hanya target/fasilitas pemasangan diganti ke workspace tanpa hak administrator. Ini bukan uji pemasangan penuh pada Program Files.
- 303 tes lulus; 4 warning; 376.79 detik. Coverage gabungan statement/cabang 88.624281% (baseline 88.153657%; aturan/exclusion coverage tidak diubah).

## Batasan

Installer/EXE belum ditandatangani digital (NotSigned); kualifikasi lokal tidak mensyaratkan Authenticode. Jangan mematikan proteksi Windows. Persetujuan admin atau kebijakan instalasi RS tetap diperlukan. Belum diuji pada komputer bersih lain. Tidak ada klaim siap produksi atau persetujuan klinis.

Perbaikan pada instalasi operasional belum dijalankan oleh agen. Percobaan modifikasi langsung berhenti pada helper sebelum eksekusi; paket repair/installer memerlukan tindakan pengguna dengan persetujuan administrator. Pengujian memakai database sementara terisolasi, tanpa koneksi Khanza dan tanpa mengubah data ProgramData.

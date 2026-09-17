# Phase 3.6 — Production Installer & Release Packaging: Checklist UAT

## Fresh install

1. Jalankan `E-MAS-Farmasi-Setup-1.0.4-x64.exe` sebagai Administrator pada PC uji Windows x64.
2. Pastikan aplikasi terpasang di Program Files dan data dibuat di `%ProgramData%\eMSSFarmasi`.
3. Jalankan E-MAS dari Start Menu. Buat administrator pertama, masuk Mode Farmasi, lalu pilih RALAN atau RANAP sekali.
4. Buka **Persiapan Instalasi** dan pastikan Compatibility Wizard dapat dijalankan.
5. Restart aplikasi, lalu pastikan commissioning profile tetap sama dan tidak diminta memilih ulang.
6. Verifikasi Status Operasional, JAB/bridge, pembacaan resep, popup, audio, dan overlay pada lingkungan Khanza uji.

## Upgrade

1. Pada instalasi lama, catat profile, database, mapping, unmapped registry, active KB/provenance, dan audit.
2. Buat backup dari menu Pencadangan & Pemulihan sebelum menjalankan installer baru.
3. Jalankan installer baru di atas instalasi lama, lalu buka aplikasi sekali untuk menjalankan migrasi.
4. Pastikan `%ProgramData%\eMSSFarmasi` tidak dihapus, profile RALAN/RANAP tidak berubah, dan KB Published/historinya tetap sama.
5. Pastikan dashboard, status operasional, dan health check tetap berfungsi; tidak ada bridge kedua atau sumber Desktop+MySQL bersamaan.

## Failure and uninstall

1. Bila upgrade dihentikan/gagal, jangan hapus folder ProgramData; gunakan backup tervalidasi untuk pemulihan bila diperlukan.
2. Uninstall aplikasi. Pastikan hanya binaries/shortcut dihapus dan data klinis/config/backup di ProgramData tetap ada.

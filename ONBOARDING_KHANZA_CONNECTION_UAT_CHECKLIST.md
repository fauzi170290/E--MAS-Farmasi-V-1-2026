# UAT Onboarding, Commissioning, dan Koneksi Khanza

Gunakan PC fresh test atau database E-MAS baru. Jangan memakai database pelayanan
untuk skenario fresh install.

## Discovery final Desktop/JAB v1.0.13

Catat dari **Koneksi Khanza → Detail Teknis**: PID target, bukti identitas,
JAB attach, state bridge, state pembacaan resep, dan error terakhir bila ada.

1. Dengan Khanza sudah terbuka dan login, buka E-MAS. Pastikan target ditemukan,
   bukti identitas adalah `KHANZA_JAR` atau `JAB_UI_SIGNATURE`, JAB attach
   berhasil, dan state adalah `KHANZA_CONNECTED`.
2. Tutup form resep sambil membiarkan Khanza terbuka. Pastikan state pembacaan
   resep menjadi `PRESCRIPTION_VIEW_NOT_FOUND`, bukan `KHANZA_NOT_FOUND`.
3. Buka form resep yang valid. Pastikan state menjadi `PRESCRIPTION_READY` dan
   snapshot resep terbaca.
4. Tutup Khanza. Pastikan status kembali menunggu Khanza; sumber tetap
   Desktop/JAB dan tidak menjadi DISABLED.
5. Buka Khanza kembali. Pastikan koneksi pulih otomatis tanpa restart E-MAS,
   dan hanya satu proses `KhanzaBridge.exe` berjalan.
6. Bila ada aplikasi Java lain, pastikan aplikasi tersebut tidak menjadi target
   Khanza. Kandidat yang belum dapat dibuktikan harus tampil sebagai
   `KHANZA_UNVERIFIED`, bukan Khanza terhubung.

## Fresh install

1. Instal dan buka E-MAS Farmasi.
2. Buat Admin Utama.
3. Pastikan **Persiapan Awal E-MAS** terbuka otomatis sebelum halaman utama.
4. Pilih **Farmasi Rawat Jalan** atau **Farmasi Rawat Inap** sesuai PC.
5. Pastikan **Desktop / JAB — Direkomendasikan** sudah dipilih secara default.
6. Selesaikan onboarding dan pastikan halaman utama menampilkan:
   - Area Pelayanan sesuai pilihan;
   - Metode Pembacaan Resep: Desktop / JAB;
   - Status Integrasi: AKTIF.

## Khanza dibuka setelah E-MAS

1. Jalankan E-MAS ketika Khanza belum dibuka.
2. Pastikan status **Menunggu SIMRS Khanza dibuka**, bukan GAGAL atau
   NOT_CONFIGURED.
3. Buka dan login ke Khanza tanpa menutup E-MAS.
4. Tunggu pemeriksaan otomatis dan pastikan status berubah menjadi
   **Khanza terhubung** tanpa tombol Connect atau restart.
5. Buka satu detail resep dan pastikan resep terbaca.

## Reconnect

1. Tutup Khanza setelah status terhubung.
2. Pastikan metode Desktop/JAB dan integrasi tetap aktif; status kembali
   **Menunggu SIMRS Khanza dibuka**.
3. Buka Khanza kembali dan pastikan tersambung otomatis.
4. Pada Detail Teknis, pastikan hanya satu KhanzaBridge yang aktif.

## Khanza dibuka sebelum E-MAS

1. Tutup E-MAS, lalu buka dan login ke Khanza.
2. Jalankan E-MAS.
3. Pastikan E-MAS tersambung otomatis dan membaca resep tanpa tindakan manual.

## Persistensi dan isolation

1. Restart E-MAS dan pastikan onboarding tidak tampil lagi.
2. Pastikan area RALAN/RANAP dan Desktop/JAB tetap sama.
3. Buka Persiapan Instalasi dan pastikan Khanza yang belum terbuka berstatus
   MENUNGGU, bukan “MySQL fallback aktif”.
4. Bila menguji MySQL pada instalasi terpisah, pilih MySQL secara eksplisit dan
   pastikan Desktop/JAB tidak menjadi producer bersamaan.

## Regresi klinis

1. Uji satu resep DDI yang sudah dikenal.
2. Pastikan hasil DDI, popup, audio, fingerprint/dedup, dan overlay tetap sama
   dengan baseline UAT yang sudah disetujui.

Catat hasil tiap bagian sebagai PASS/FAIL beserta waktu dan nama workstation.

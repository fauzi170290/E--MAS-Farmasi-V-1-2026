# UAT PC Client — Dual KhanzaBridge v1.0.16

Gunakan installer `E-MAS-Farmasi-Setup-1.0.16-x64.exe` sebagai **upgrade**.
Data `%ProgramData%\eMSSFarmasi` tidak perlu dihapus.

1. Tutup E-MAS lalu jalankan installer sebagai Administrator. Bila diminta,
   izinkan installer menutup E-MAS. Setelah selesai, buka E-MAS kembali.
2. Dengan SIMRS Khanza sudah login, buka **Status Operasional & Pemulihan** lalu
   **Detail Teknis**. Pastikan `Target Khanza ditemukan: YA`, PID tampil,
   bukti `khanza.jar`, **Arsitektur Java Khanza: X64**, **Arsitektur Bridge:
   X64**, **Kecocokan arsitektur: COCOK**, JAB attach PASS, dan bridge
   CONNECTED. Gunakan **Salin Diagnostik Khanza** bila hasil perlu dikirim.
3. Tutup SIMRS Khanza. Status harus menjadi **Menunggu SIMRS Khanza dibuka**;
   metode Desktop/JAB tetap aktif, bukan DISABLED.
4. Buka dan login Khanza lagi tanpa merestart E-MAS. Pastikan status kembali
   terhubung dan hanya satu bridge persisten berjalan. Untuk Java x64 prosesnya
   `KhanzaBridge-x64.exe`; untuk Java x86 prosesnya `KhanzaBridge-x86.exe`.
5. Buka resep nyata atau dummy. Pastikan snapshot resep terbaca dan alur DDI
   (hasil/popup/audio/overlay sesuai konfigurasi workstation) tetap berjalan.

Jika target Khanza telah ditemukan tetapi resep belum terbaca, catat sebagai
masalah pembacaan resep beserta baris `DESKTOP_SNAPSHOT` dari log; jangan
laporkan sebagai `KHANZA_NOT_FOUND`.

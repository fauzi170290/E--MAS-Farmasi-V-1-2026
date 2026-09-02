# Status kebutuhan 27 Agustus 2026 — 0.31.0

Status “teknis” berarti implementasi dan bukti pada data sintetis terisolasi. Bukan UAT RS, persetujuan klinis, atau izin deployment. Backlog asli dipreservasi; dokumen ini adalah pembaruan terpisah.

| Kebutuhan | Status | Bukti / pekerjaan tersisa |
|---|---|---|
| Audit source aktif, baseline, installer lama | Selesai | Source 0.30.0/head0026; 256 pass; coverage gabungan dengan branch 88,153657%; hash installer lama cocok. Backup source dan manifest sebelum perubahan disimpan lokal. |
| Master/mapping runtime kosong, 5.432 pair DRAFT | Terverifikasi read-only | Koneksi aktual bukan kesiapan skrining; tidak ada publikasi/aktivasi otomatis. |
| Tiga kasus pengguna | Terlihat di view | Jumlah item reguler 4/5/2, racikan 0/0/4. Belum dipaksakan skrining klinis di runtime RS. |
| Password Machine/proses berbeda | Diagnostik tersedia | Nilai tidak dicetak/disalin/diubah; restart proses dari environment yang benar oleh IT. |
| Otomatis sejak jendela utama, tanpa klik Integrasi | Teknis selesai | Worker terjadwal dari startup setelah enable + consent; hasil dikirim per resep. Default operasional tidak diubah. |
| Tetap bekerja di tray | Teknis terbukti pada Windows lokal | Close-to-tray pada data sintetis, bukan sekadar mock hide. Tidak ada service; keluar penuh berhenti. |
| Otomatis tanpa klik / keputusan polling | Disetujui pengguna untuk UAT lokal | Pada 27 Agustus 2026 pengguna menyetujui polling internal 3 detik setelah penjelasan. Bukan push. Config terpisah disiapkan; adapter disabled sampai target clone dikonfirmasi. Izin deployment/klinis tetap terpisah. |
| Histori tidak menahan resep terkini | Teknis selesai dengan batas | Lane RECENT/TARGETED dan HISTORY/RECONCILE, checkpoint+inbox atomik, slot kerja terpisah. Uji 22.000 histori. Penemuan total sumber masih bertahap. |
| Retry sah, restart/reconnect | Teknis selesai | Inbox/backoff, adopsi kegagalan lama, alasan retry diaudit, outbox NEW bertahan; tidak reset cursor/histori. |
| Revisi tanpa timestamp, backdate, validasi/batal | Teknis selesai untuk keadaan yang teramati | Fingerprint item+status+validation token, event berurutan, dua observasi stabil. Tidak menjamin menangkap transisi yang terjadi lalu hilang di antara pembacaan. |
| Transaksi belum lengkap/parsial | Kontrol tersedia; kontrak RS terbuka | Snapshot satu transaksi repeatable-read, stabilitas, batas item fail-closed. Komposisi lengkap harus dinyatakan oleh view final yang teruji; kesamaan dua snapshot sendiri tidak membuktikan seluruh transaksi bisnis selesai. |
| Komposisi FINAL saat validasi | Adapter/fail-closed tersedia; DBA terblokir | Source lokal menunjukkan tabel pemberian/racikan terpisah. Kandidat SQL belum diterapkan/diuji MariaDB. Varian aktif dan relasi final harus dikonfirmasi; tuple no_rawat/tanggal/jam bisa ambigu. |
| Sinkronisasi master dan mapping | Teknis selesai | Tambah master PENDING_REVIEW, preservasi manual, workbook dapat dipreview. Persetujuan mapping/KB aktual tetap wajib. |
| Popup per hasil major/kontra | Teknis selesai | Kategori severity positif SERIOUS/CONTRAINDICATED, bukan semua CRITICAL. Minor/moderate dan warning keselamatan tetap ditangani. |
| Konfirmasi lengkap tanpa interaksi setelah validasi | Teknis selesai | Wajib FINAL verified, COMPLETE, seluruh pair dinilai, mapping lengkap, tanpa issue/warning. Pesan tepat, bukan jaminan aman klinis. |
| Antrean, prioritas, dedup popup/audio | Teknis selesai dengan batas | Satu suara/popup per giliran; prioritas kategori, outbox persisten, callback display menandai SHOWN. Crash tepat di antara visual dan penyimpanan SHOWN masih berpotensi pengulangan (at-least-once), bukan jaminan exactly-once. |
| Latensi seluruh popup <=10 detik | Belum tercapai pada burst | Enam sampel sintetis: hasil ~3 detik, popup kedua menunggu durasi popup pertama. Laporan angka p95/maksimum disertakan; bukan hard realtime. |
| Audio asli pilihan pengguna | Playback lokal diuji | Hash/PCM asli dipreservasi. Qt Playing terlihat; tidak sama dengan mendengar dan menilai persepsi. |
| Bundling audio Mixkit | Terblokir izin | Lisensi melarang redistribusi standalone/tool/source. Tidak dibundel sebelum izin redistribusi aplikasi jelas; tidak diganti suara lain. |
| Volume, pilih/test suara, fallback visual | Teknis selesai | File lokal, PCM WAV/MP3, batas ukuran/durasi, visual bila hilang/rusak/device tidak ada. Demo tidak membuat hasil klinis. |
| Silent/advisory/production fail-closed | Dipertahankan | Pemeriksaan gate juga pada pengiriman antrean. Tidak ada approval fiktif atau penggantian mode runtime. |
| Single head dan preservasi ledger | Teknis selesai | 0027 aditif; observasi immutable; downgrade mempertahankan tabel monitor, migrasi ulang tersedia. |
| Regression/coverage/build/lifecycle/signature | Lihat laporan final | Angka dan status harus berasal dari eksekusi terbaru, bukan rencana. Gate87 tidak dilemahkan; baseline aktual dibandingkan dengan presisi penuh. |
| Installer terpasang/clean-host RS/UAT independen | Belum dilakukan | Installer disiapkan tanpa deployment otomatis. Signature/waiver, approval klinis, target, backup dan window deployment tetap eksternal. |
| Interlock sebelum validasi/cetak | Di luar kewenangan saat ini | Integrasi read-only hanya setelah commit. Perubahan Khanza terpisah diperlukan. |

## Catatan audit dan keamanan

Tidak ada akses tulis klinis Khanza, perubahan sql_mode global, restore dump, trigger/binlog/service baru, atau pemberian hak admin. Data pasien tidak digunakan dalam screenshot/fixture/bukti yang dibagikan. Snapshot sumber pada runtime disimpan lokal untuk audit dan tetap merupakan data sensitif yang harus dikelola dengan kebijakan akses/retensi RS.

SQLite menyimpan waktu UTC; status timestamp sumber mengikuti konvensi adapter lama dan jam server. Pengukuran latensi memakai monotonic perf_counter, bukan selisih jam Windows dengan server. Sinkronisasi timezone/clock RS perlu masuk UAT.

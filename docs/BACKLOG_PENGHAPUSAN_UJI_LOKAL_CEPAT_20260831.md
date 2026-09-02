# Backlog — Penghapusan Uji Lokal Cepat

Status: SELESAI DI SOURCE setelah rilis 0.34.2; belum dibuat installer baru.

## Keputusan produk

Mulai pengembangan berikutnya, E-MAS Farmasi tidak lagi menyediakan atau menawarkan **UJI LOKAL CEPAT**. Jalur uji harus mengikuti integrasi pelayanan SIMRS Khanza yang sebenarnya, tetap read-only terhadap Khanza, dan tidak mengubah data klinis Khanza.

## Ruang lingkup

- Hapus pilihan `UJI LOKAL CEPAT` dari installer dan seluruh teks/aksi yang mengaktifkan pemeriksaan satu detik untuk tujuan pengujian.
- Jangan menghapus database internal E-MAS, backup, ekspor, atau konfigurasi instalasi yang sudah ada saat pembaruan maupun uninstall.
- Tetap pertahankan pemisahan RALAN/RANAP, koneksi Khanza read-only, dan guardrail bahwa hasil tidak boleh dianggap aman saat data/koneksi belum lengkap.
- Uji pada alur SIMRS Khanza pelayanan yang sesungguhnya dengan data dan persetujuan lingkungan yang sesuai; jangan menganggap data sintetis sebagai bukti UAT rumah sakit.

## Kriteria penerimaan

1. Installer tidak menampilkan task, label, atau perintah `UJI LOKAL CEPAT` / `configure-local-test`.
2. Instalasi atau pembaruan tidak menghapus data internal yang ada.
3. Tidak ada kredensial, perubahan schema, INSERT/UPDATE/DELETE, trigger, atau penulisan lain ke Khanza.
4. Alert dan popup tetap memakai mekanisme pelayanan normal; interval tidak dipaksakan satu detik oleh installer.
5. Kualifikasi ulang mencakup instalasi/pembaruan pada lingkungan uji SIMRS Khanza yang disetujui dan bukti aktual dipisahkan dari tes sintetis.

## Ketergantungan dan risiko

Batch ini menyentuh installer, konfigurasi, CLI, dokumentasi, serta tes integrasi. Klasifikasi awal: **MEDIUM**, effort **Medium**. Pisahkan dari perubahan UI rutin dan jangan memperbarui dua PDF sebelum pemilik sistem menyatakan isi panduan final.

## Implementasi

- Task installer, perintah CLI, adapter, polling, dan tampilan khusus `UJI LOKAL CEPAT` telah dihapus.
- Konfigurasi lama `mysql_local_test` hanya dibaca untuk kompatibilitas kemudian dinonaktifkan di memori; file konfigurasi, database, backup, dan ekspor tidak ditulis atau dihapus. Konfigurasi tidak pernah dialihkan diam-diam ke endpoint Khanza produksi.
- Jalur Khanza normal tetap menggunakan adapter `mysql` read-only dan guardrail RALAN/RANAP tetap berlaku.
- Verifikasi source: 79 tes integrasi lulus; parser CLI tidak lagi menyediakan `configure-local-test`; pencarian installer/source tidak menemukan task atau teks UJI LOKAL CEPAT. Kualifikasi installer dan pengujian pada lingkungan SIMRS Khanza yang disetujui tetap menjadi bagian batch rilis berikutnya.

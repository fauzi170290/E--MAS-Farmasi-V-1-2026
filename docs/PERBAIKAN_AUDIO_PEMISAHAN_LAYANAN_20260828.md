# Perbaikan berikutnya: suara hasil lengkap dan pemisahan rajal/ranap

Tanggal: 28 Agustus 2026. Baseline aplikasi: 0.32.1.
Status: KEBUTUHAN DICATAT; pembeda sumber sudah ditelusuri; BELUM DIIMPLEMENTASIKAN.

Dokumen ini mencatat permintaan terbaru pengguna. Tidak ada perubahan aplikasi
terpasang, pengaturan aktif, data resep, view Khanza, atau installer pada kegiatan
ini. Bukan bukti UAT atau persetujuan untuk penggunaan pelayanan.

## 1. Suara pemeriksaan lengkap tanpa popup alert

Permintaan pengguna: jika skrining lengkap dan tidak ditemukan interaksi, suara
"Pemeriksaan lengkap" tetap berbunyi, walaupun tidak ada popup alert interaksi.
Ini memperbarui ketentuan lama yang membatasi seluruh notifikasi hanya mayor/kontra
dan catatan lama yang menyebut suara tanpa interaksi sebagai kebutuhan opsional.

Kriteria penerimaan:

- Setelah validasi Khanza terdeteksi, tunggu snapshot stabil dan skrining berhasil.
- Suara konfirmasi hanya boleh diputar jika komposisi final terverifikasi, hasil
  COMPLETE, ada kandungan yang dapat dinilai, seluruh obat terpetakan, seluruh
  pasangan relevan selesai dinilai, tidak ada interaksi, dan tidak ada masalah
  kelengkapan atau kegagalan. Tidak adanya pasangan karena hanya satu kandungan
  harus dibedakan dari resep kosong/tidak terbaca.
- Adanya interaksi moderat/minor juga menolak suara "tanpa interaksi". Bukan sekadar
  tidak adanya mayor/kontraindikasi. Jangan mengganti INCOMPLETE menjadi COMPLETE
  hanya untuk memicu suara.
- Gunakan kanal audio `screening-clear` terpisah dari popup klinis. Suara konfirmasi
  tidak harus membuat popup/alert baru. Hasil tetap tampil dan tersimpan di riwayat.
- Teks hasil menjelaskan batas pemeriksaan: "Pemeriksaan lengkap; tidak ditemukan
  interaksi dalam basis data yang digunakan", bukan jaminan aman secara keseluruhan.
- Tetap hormati pengaturan mute, volume, izin operasional, dan penanda UJI LOKAL.
  Basis DRAFT/pending pada mode uji tidak boleh dipublikasikan otomatis.
- Deduplikasi satu konfirmasi per peristiwa validasi/revisi yang memenuhi syarat.
  Polling ulang, muat ulang, restart, atau klik riwayat tidak boleh mengulang suara.
- Prioritaskan suara mayor/kontra di atas suara konfirmasi. Kegagalan audio dicatat,
  tidak mengubah hasil atau menghapus popup risiko.
- Semua suara, termasuk konfirmasi, tunduk pada batas layanan instalasi pada bagian 3.

Temuan kode: `src/emss/alerts/notification.py` mempunyai pemeriksaan ketat untuk
hasil clear, tetapi cabang `validated_high_only` saat ini mengembalikan notify=False
lebih dahulu untuk hasil selain mayor/kontra. Pada perbaikan, jangan sekadar melepas
batas tersebut: pisahkan keputusan popup dan audio agar tidak mengaktifkan popup
moderat/konfirmasi yang tidak diminta.

## 2. Arti dan perbaikan status belum lengkap

Pada diagnosis dua resep 28 Agustus, validasi terbaca dan skrining selesai. Masalah
yang tercatat sama: "Komposisi akhir sumber belum terverifikasi; hasil bukan
konfirmasi tanpa interaksi." Tidak ditemukan obat belum terpetakan maupun pasangan
belum dinilai pada dua hasil tersebut. Salah satunya memiliki interaksi moderat;
yang lain tidak ditemukan interaksi pada pasangan yang dinilai.

View header aktif belum menyediakan `item_basis`, `composition_complete`, maupun
`validation_token`. Adapter memakai default UNVERIFIED/false untuk informasi
komposisi yang tidak tersedia. Monitor memerlukan `composition_complete=true` dan
`item_basis=FINAL` untuk menyatakan sumber resep tervalidasi lengkap.

Artinya bukan otomatis petugas belum memvalidasi atau lupa mengisi resep. E-MAS
belum dapat memastikan daftar obat yang diperiksa sama dengan obat final setelah
perubahan/validasi farmasi. Template integrasi dasar membaca rincian peresepan
(`resep_dokter` dan rincian racikan), yang belum membuktikan semua perubahan pada
hasil pelayanan ikut terbaca.

Langkah perbaikan:

1. Telusuri alur penyimpanan validasi rajal dan ranap, termasuk obat diganti,
   jumlah/aturan diubah, racikan, pembatalan, dan transaksi gagal.
2. Buktikan relasi setiap nomor resep ke item final tanpa tercampur resep lain.
   Kandidat `detail_pemberian_obat` menggunakan relasi no_rawat/tanggal/jam;
   tuple yang sama untuk beberapa resep, kode bersama racikan/nonracikan, atau
   data parsial tidak boleh dianggap pasti. Kandidat SQL di templates masih DRAFT.
3. Setelah relasi dibuktikan, tetapkan kontrak view header dan detail yang konsisten
   dalam satu transaksi baca. Jangan mengisi `composition_complete=1` secara tetap.
4. Uji dua jalur layanan dan hasil sebelum/sesudah perubahan; kasus ambigu tetap
   INCOMPLETE. Perubahan SQL dilakukan terpisah oleh pihak berwenang dengan target
   dan backup yang jelas; aplikasi tetap hanya SELECT.
5. Perjelas label antarmuka: "Skrining selesai — komposisi obat final belum
   terverifikasi", beserta alasan detail, agar tidak disangka validasi Khanza gagal.

## 3. Pemisahan wajib sesuai instalasi

Permintaan pengguna: E-MAS di Farmasi Rajal tidak boleh menampilkan atau membunyikan
alert dari resep Ranap, dan sebaliknya. Ini batas pemantauan/notifikasi instalasi,
bukan sekadar filter sementara pada tabel.

### Pembeda yang sudah ditemukan

| Sumber | Arti | Bukti lokal |
| --- | --- | --- |
| `resep_obat.status = 'ralan'` | Asal resep rawat jalan | Skema lokal enum dan query daftar resep Rajal |
| `resep_obat.status = 'ranap'` | Asal resep rawat inap | Skema lokal enum dan query daftar resep Ranap |
| `status_resep` pada view E-MAS | DIRESEPKAN / DIPROSES_FARMASI / DISERAHKAN | Berbeda dari asal layanan |
| `unit_depo` pada view sekarang | Label poli dengan nilai pengganti | Tidak cukup untuk penentu rajal/ranap |

Skema dump lokal: `D:/PROJECT KHANZA/sik/sik.sql`, baris 19841–19857,
khususnya 19849: status enum ralan/ranap, dapat NULL.
Kode lokal: `D:/PROJECT KHANZA/SIMRS-Khanza/src/inventory/DlgDaftarPermintaanResep.java`,
baris 2857 untuk ralan, 3393 untuk ranap. Kode yang sama juga memakai
`set_depo_ralan` (sekitar 2875) dan `set_depo_ranap` (sekitar 3412) untuk filter depo.
Pemeriksaan hanya membaca skema/kode, tidak menyalin data pasien dari dump.

Pola ini juga ditemukan di [kode resmi Khanza](https://github.com/mas-elkhanza/SIMRS-Khanza/blob/master/src/inventory/DlgDaftarPermintaanResep.java),
diakses 28 Agustus 2026. Skema/kode lokal adalah acuan untuk implementasi lokal;
versi resmi terkini tidak otomatis sama dengan instalasi pengguna.

Batas bukti: akun integrasi saat diagnosis hanya bisa membaca view, bukan tabel
dasar (MySQL 1142), dan view belum mengekspos asal layanan. Karena itu belum
dipastikan mana dari dua nomor resep uji terbaru yang ralan atau ranap. Nama UNIT
IGD/POLI ANAK tidak dipakai sebagai dugaan penentu. Jangan menggunakan kredensial
admin sebagai jalan pintas untuk mengatasi pembatasan akun aplikasi.

### Rencana implementasi

1. Teruskan `ro.status` dari header ke kolom baru yang eksplisit, misalnya
   `asal_layanan`, normalisasi hanya RALAN/RANAP; lainnya UNKNOWN. Tetap boleh
   memakai satu `vw_emss_prescription_header`. Jangan menimpa `status_resep`.
2. Simpan asal layanan di snapshot/peristiwa/revisi/antrean hasil. Jadikan perubahan
   asal bagian dari deteksi revisi. Jangan menebak dari nama pasien, nama poli,
   folder instalasi, IP, ataupun status pasien saat ini setelah pindah perawatan.
3. Pada konfigurasi awal instalasi, WAJIB pilih Farmasi Rawat Jalan atau Farmasi
   Rawat Inap. Tampilkan pilihan aktif terus di aplikasi, simpan per instalasi,
   batasi perubahan kepada administrator, dan audit perubahannya. Tidak ada
   default "Semua layanan" untuk workstation pelayanan. Upgrade mempertahankan
   pilihan yang sah; instalasi lama tanpa pilihan harus meminta konfigurasi dulu.
4. Batasi pembacaan/pemrosesan otomatis sejak query/discovery, serta periksa ulang
   batas layanan sebelum menampilkan antrean pelayanan dan mengirim popup/audio.
   Terapkan pada semua jalur: resep baru, validasi, retry, revisi, riwayat yang
   diperiksa ulang, reconnect, tray, serta antrean notifikasi yang sudah tersimpan.
5. Jangan hanya menyaring tampilan UI. Sediakan pemeriksaan akhir tepat sebelum
   popup/audio supaya hasil worker lama atau perubahan konfigurasi tidak
   meneruskan notifikasi dari layanan lain.
6. UNKNOWN/missing field atau instalasi belum dikonfigurasi: jangan menyebar alert
   ke semua workstation. Tampilkan peringatan konfigurasi/integrasi yang jelas,
   simpan alasan dan pekerjaan tertunda untuk ditangani, jangan menandainya SAFE
   atau selesai tanpa evaluasi. Rilis pelayanan diblokir bila kontrak sumber gagal.
7. Perubahan pilihan instalasi harus menghentikan pengiriman notifikasi lama,
   mengaudit notifikasi yang dibatalkan karena beda layanan, lalu melakukan
   rekonsiliasi cursor/inbox tanpa kehilangan resep yang kini menjadi tanggung
   jawabnya. Histori tidak dihapus dan tidak boleh bocor ke antrean layanan lain.
8. Rajal/ranap adalah minimum wajib. Bila ada beberapa depo dalam satu jenis
   layanan, telusuri kode depo tujuan/penanggung jawab secara terpisah. Mapping
   `set_depo_ralan`/`set_depo_ranap` adalah kandidat, bukan bukti identitas petugas
   validator. Perpindahan bangsal, ranap_gabung, IGD, resep pulang, dan beberapa
   workstation satu depo perlu kontrak/routing yang diuji sebelum diperluas.

### Uji penerimaan wajib sebelum rilis pemisahan

| Kasus | Instalasi Rajal | Instalasi Ranap |
| --- | --- | --- |
| Resep RALAN tervalidasi dengan mayor/kontra | Popup + suara sesuai aturan | Tidak ada popup/suara |
| Resep RANAP tervalidasi dengan mayor/kontra | Tidak ada popup/suara | Popup + suara sesuai aturan |
| RALAN lengkap tanpa interaksi | Suara konfirmasi, tanpa popup klinis | Tidak ada suara |
| RANAP lengkap tanpa interaksi | Tidak ada suara | Suara konfirmasi, tanpa popup klinis |
| Moderat/minor atau INCOMPLETE | Tidak ada suara konfirmasi clear | Tidak ada suara konfirmasi clear |
| Asal UNKNOWN atau pilihan instalasi belum ada | Peringatan konfigurasi; tidak merutekan klinis | Peringatan konfigurasi; tidak merutekan klinis |
| Polling ulang/restart tanpa revisi baru | Tidak mengulang notifikasi | Tidak mengulang notifikasi |

Uji tambahan: dua workstation aktif bersamaan, pergantian pilihan saat worker
berjalan, notifikasi tersimpan sebelum upgrade, perpindahan layanan, database
putus/sambung, dan volume besar satu layanan tidak menghambat layanan lainnya.
Mayor/kontra yang ditemukan pada data belum lengkap tetap mengikuti kebijakan
peringatan risiko yang berlaku di layanan yang benar; jangan mematikannya hanya
karena tidak memenuhi syarat suara clear.

## 4. Urutan pekerjaan dan batas verifikasi

Prioritas: pastikan kontrak asal layanan dan isolasi instalasi, buktikan komposisi
final, lalu aktifkan suara clear yang ketat. Uji lintas instalasi dan audio aktual
sebelum menyatakan lulus. Seluruh hasil tetap diberi penanda uji saat basis belum
memenuhi syarat pelayanan. Pada tahap pencatatan ini belum ada build, instalasi,
perubahan view, pengujian speaker, atau uji pemisahan dua PC.

Bukti diagnosis terkait: `outputs/DIAGNOSTIK_DUA_RESEP_20260828.json` pada workspace.
Dokumen ini melengkapi backlog 27 Agustus; ketentuan terbaru pengguna di sini
berlaku bila berbeda dengan ketentuan notifikasi lama.

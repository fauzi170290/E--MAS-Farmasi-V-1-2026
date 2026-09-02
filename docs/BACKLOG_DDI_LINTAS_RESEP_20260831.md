# Backlog E-MAS Farmasi — DDI lintas resep pasien yang sama

Tanggal pencatatan: 31 Agustus 2026.
Baseline: 0.34.1.
Status: Engine Batch 7 diimplementasikan pada kode sumber; regresi akhir gabungan Batch 6–7 lulus 411 tes. Integrasi penuh dan installer tetap Batch 8–9. Lihat IMPLEMENTASI_BATCH_6_7_20260831.md.
ID: DDI-LINTAS-RESEP-001.
Kebutuhan terkait: [menu tambah obat dan pasangan DDI manual](BACKLOG_MASTER_OBAT_PAIR_DDI_20260831.md), dicatat terpisah agar perubahan UI/CRUD master tidak digabung otomatis dengan mesin DDI lintas resep.
Otorisasi saat pencatatan awal hanya untuk backlog. Permintaan lanjutan pengguna “kerjakan batch 6-7” mengotorisasi implementasi kode sumber yang dilaporkan terpisah; tidak dilakukan perubahan schema atau penerapan ke database/installer operasional.

## Kebutuhan wajib pengguna

Setiap resep baru FINAL/tervalidasi pada pasien yang sama wajib memicu skrining DDI terhadap resep sebelumnya yang relevan, selain skrining di dalam resep dan deteksi duplikasi kandungan. Dokter/poli sama atau berbeda tidak boleh menjadi alasan melewatkan pemeriksaan.

| Waktu contoh | Resep | Pemeriksaan yang wajib dipicu |
|---|---|---|
| 09.00 | Nomor berakhiran 001 | DDI di dalam 001 dan terhadap resep terdahulu yang relevan bila tersedia. |
| 09.45 | Nomor berakhiran 002, pasien sama | DDI di dalam 002, duplikasi, serta pasangan obat lintas 002–001. |
| Sesudahnya | Nomor berakhiran 003, pasien sama | DDI di dalam 003, duplikasi, serta pasangan lintas 003–001 dan 003–002. Hasil 001–002 tetap tersedia dalam konteks gabungan tanpa notifikasi ulang yang tidak perlu. |

Nomor akhiran 001/002/003 hanya contoh. Pencocokan memakai identitas pasien yang stabil dari sumber, nomor resep lengkap, waktu/peristiwa sumber, dan revisi; bukan nama pasien saja atau urutan akhiran nomor resep. Tidak hanya membandingkan resep baru dengan satu resep paling akhir.

Skenario penerimaan utama menggunakan satu pasien sintetis dengan tiga resep, tiga dokter, dan variasi poli sama/berbeda. Buat rule uji sintetis yang hanya berinteraksi antar-resep sehingga keberhasilan tidak dapat dipenuhi oleh skrining DDI di dalam resep saja.

## Konteks terapi dan batas keselamatan

- Contoh 09.00 → 09.45 wajib tercakup. Resep baru tetap memicu evaluasi; ketidakpastian penggunaan obat lama tidak boleh membuat pemeriksaan dilewati diam-diam.
- Daftar resep historis adalah kandidat konteks pemeriksaan, bukan bukti semua obat masih diminum. Bila penggunaan belum diketahui, tampilkan potensi interaksi berbasis riwayat beserta sumber dan kebutuhan rekonsiliasi.
- Batas waktu/episode kandidat, data penghentian obat, dan cara konfirmasi terapi aktif harus ditetapkan sebelum implementasi inti. Jendela 24 jam yang digunakan deteksi duplikasi saat ini bukan otomatis kebijakan terapi aktif DDI.
- Pakai revisi efektif terbaru. Tangani resep dibatalkan, obat diganti/dihentikan, koreksi waktu, dan event terlambat tanpa menggandakan obat dari revisi lama. Pertahankan hasil historis dan jejak alasan perubahan konteks.
- Hasil harus membedakan DDI dalam resep, DDI antar-resep, dan duplikasi. Setiap temuan antar-resep menyertakan kedua nomor resep, kandungan/obat, waktu/revisi, dokter/poli bila tersedia, kategori master, dan status kelengkapan.
- Tidak mengarang rule DDI. Mapping hilang, rule belum tersedia, atau konteks sumber tidak lengkap tetap dinyatakan UNMAPPED/NOT_ASSESSED/INCOMPLETE sesuai kontrak hasil; jangan menyebut gabungan aman hanya karena tidak ada alert.
- Pasien berbeda tidak boleh tercampur. Identitas pasien yang ambigu menjadi kendala yang terlihat.
- Pertahankan isolasi pemantauan dan notifikasi RALAN/RANAP. Ruang lingkup penggunaan riwayat lintas layanan harus ditetapkan terpisah; jangan otomatis menyalurkan alert ke workstation layanan lain.
- Tinjauan atas hasil lama tidak otomatis meninjau pasangan baru yang muncul akibat resep/revisi berikutnya. Tidak membuat intervensi klinis otomatis.

## Batch A — Tampilan rincian DDI antar-resep

Issues: label jenis temuan, kolom dua nomor resep dan waktu, pemisah obat, kategori/warna, keterangan asal dokter/poli, tampilan konteks belum pasti.
Klasifikasi: LIGHT.
Wave: 1 — SAFE UI CHANGES.
Risk: rendah selama hanya presentasi dengan data contoh/kontrak hasil; tanpa perubahan keputusan klinis.
Model: GPT-5.6 Luna.
Effort: Low.
Alasan: perubahan lokal pada tampilan dan redaksi, tidak membutuhkan reasoning sistem menyeluruh.
Dependency: bentuk data hasil disepakati lebih dahulu; jangan menyatakan fitur aktif sebelum Batch C tersedia.
Verifikasi: seluruh pasangan dapat dibaca, teks panjang tidak terpotong, kategori dan identitas kedua resep jelas.
Rollback: patch tampilan terpisah, tanpa perubahan data.

## Batch B — Pengikatan hasil ke antrean dan handler lokal

Issues: pemilihan pasangan/resep terkait, pengambilan rincian dari hasil tersimpan, state belum tersedia/belum lengkap, validasi ID, tautan antrean dari popup.
Klasifikasi: MEDIUM.
Wave: 2 — LOCAL FUNCTIONAL FIXES.
Risk: sedang; salah ID/state dapat membuka hasil resep yang keliru.
Model: GPT-5.6 Terra.
Effort: Medium; dapat diturunkan ke Low jika targeted inspection membuktikan perubahan kecil dengan kontrak stabil.
Alasan: penghubung UI dan layanan lokal, bukan penentu konteks terapi atau algoritme pasangan.
Dependency: kontrak hasil Batch C; persiapan dan pengujian bisa memakai fixture. Pengikatan ke alur operasional menunggu inti tersedia.
Verifikasi: ID tidak berubah saat refresh, state kosong tidak menjadi SAFE, dan akses/pemilihan resep tetap benar.
Rollback: patch handler terpisah, tanpa menghapus hasil historis.

## Batch C — Inti konteks pasien dan skrining DDI lintas resep

Issues: pemilihan resep relevan pasien yang sama, revisi/pembatalan, pembentukan pasangan lintas resep, hasil/provenance, konsistensi event bersamaan/terlambat, invalidasi hasil dan tinjauan, deduplikasi popup/audio, serta isolasi layanan dan performa.
Klasifikasi: HEAVY.
Wave: 3 — DATA / SYSTEM CHANGES.
Risk: tinggi; kesalahan konteks atau revisi dapat menghasilkan interaksi terlewat, temuan berulang, atau hasil untuk pasien/layanan yang salah.
Model: GPT-5.6 Sol.
Effort: Medium sebagai awal, bukan High otomatis.
Alasan: perubahan menyentuh mesin skrining dan layanan bersama yang berhubungan dengan keselamatan hasil; memerlukan reasoning sistem, namun UI dan handler tetap dipisahkan.
Dependency: kebijakan konteks terapi/kandidat dan kontrak identitas sumber harus jelas. Telaah targeted pada screening, durable monitor, antrean, model hasil, serta notification policy.
High effort gate: naikkan hanya pada bagian yang setelah inspection menunjukkan ambiguity yang belum teratasi, race condition nyata, risiko kehilangan/kerusakan data, perubahan shared core dengan dependency tak terpisahkan, regression risk tinggi, atau percobaan Medium gagal. Tulis alasan konkretnya; jangan menaikkan A/B.
Verifikasi: contoh 001–002–003; pasien berbeda; dokter/poli berbeda; duplikasi tanpa DDI; DDI antar-resep tanpa duplikasi; mapping/rule hilang; revisi/batal; event terlambat/bersamaan; restart/retry; tinjauan hasil baru; RALAN/RANAP; latensi dan jumlah query.
Rollback: rencanakan bersama desain penyimpanan sebelum implementasi; jangan menghapus audit atau hasil lama.

## Urutan dan batas pelaksanaan

1. Tetapkan kontrak hasil dan kebutuhan konteks melalui inspection terarah, tanpa perubahan sistem.
2. Kerjakan bagian UI yang benar-benar independen pada Wave 1; jangan menambah scaffolding yang tidak diperlukan hanya untuk memaksakan urutan.
3. Kerjakan handler lokal pada Wave 2 setelah kontrak stabil. Jika pengikatan memerlukan inti, tunda bagian pengikatan tersebut sampai Batch C.
4. Implementasikan inti dan integrasi yang tidak dapat dipisahkan pada Wave 3, dalam patch terbatas dan pengujian tersendiri. Ketergantungan langsung boleh mengubah urutan pengikatan; bukan alasan mencampur seluruh UI dengan core.
5. FINAL tetap diproses pada siklus pertama. Jangan membaca ulang seluruh resep selesai setiap detik atau menambah query berat pada jalur popup. Utamakan konteks tersimpan/akses terarah; ukur dampak sebelum memilih desain cache/index.
6. Dua resep berdekatan atau revisi relevan harus memperbarui konteks yang terdampak. Deduplikasi berdasarkan konteks/revisi/pasangan, bukan hanya nomor resep, agar interaksi baru tidak tertekan oleh alert lama.
7. Perubahan schema E-MAS atau view/tabel Khanza tidak otomatis disetujui oleh backlog ini. Jika diperlukan, buktikan kebutuhan dan minta persetujuan tersendiri; jangan melakukan migration spekulatif.
8. Versi 0.34.1 tetap tidak memiliki DDI antar-resep. Jangan mengubah catatan rilis atau laporan tes lama seolah fitur ini sudah tersedia. Versi target belum ditetapkan.

## Dasar rekomendasi model

Pembagian batch/risiko di atas adalah penilaian engineering untuk proyek ini, mengikuti aturan pengguna: pisahkan dahulu, lalu pilih model dan effort per batch. Nama model tersedia dalam konteks aplikasi saat pencatatan; ini rekomendasi, bukan penggantian model otomatis.

Dokumentasi resmi OpenAI menjelaskan posisi Sol/Terra/Luna serta penggunaan Medium sebagai awal yang seimbang, dengan kenaikan effort berdasarkan manfaat kualitas yang terukur. Rujukan: [OpenAI Model guidance](https://developers.openai.com/api/docs/guides/latest-model). Tidak ada klaim bahwa pilihan ini menjamin durasi atau biaya tertentu.

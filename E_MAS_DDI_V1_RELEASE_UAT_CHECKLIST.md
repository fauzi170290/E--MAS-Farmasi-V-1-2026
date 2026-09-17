# E-MAS DDI v1 Release UAT Checklist

Gunakan satu workstation Rajal dan satu workstation Ranap bila tersedia. Catat resep sintetis atau nomor resep tanpa menyalin identitas pasien ke laporan.

## Rawat Jalan

- [ ] Zero DDI: SAFE audio sekali, tanpa popup DDI dan tanpa severity overlay.
- [ ] Single moderate DDI: popup, audio dan warna overlay benar.
- [ ] Major DDI: popup, audio dan warna overlay benar.
- [ ] Multi-DDI: satu popup aggregated, severity tertinggi dahulu, semua pasangan terlihat, detail dapat dibuka.
- [ ] Unmapped-only: tidak ada SAFE audio; feedback incomplete/unmapped dan registry tercatat.
- [ ] DDI + unmapped: DDI audio sekali, tanpa audio kedua, pasangan known tetap terlihat.
- [ ] Regular, racikan, lalu kombinasi regular + racikan terbaca benar.

## Rawat Inap

- [ ] Ulangi seven skenario Rawat Jalan di atas.
- [ ] Pastikan resep Ranap tidak masuk antrean atau konteks Rajal, dan sebaliknya.

## Navigation and overlay

- [ ] Rajal A → B, A → B → C cepat, dan A → B → A.
- [ ] Ranap A → B → C dan Rajal A → Ranap B → Rajal C.
- [ ] Popup, audio dan overlay hanya untuk resep aktif; highlight lama clear-first.
- [ ] Row obat yang tepat diberi warna; row non-DDI tidak berwarna.
- [ ] Scroll, resize, minimize/restore bila digunakan.
- [ ] Uji pada scale 100%, 125%, dan 150% yang didukung; bila geometry meragukan, overlay harus hilang, bukan salah row.

## Mapping and recovery

- [ ] Unresolved drug → existing canonical dengan referensi.
- [ ] Unresolved drug → canonical baru dengan referensi, lalu kelola pair DDI melalui manager yang ada.
- [ ] Buka kembali resep setelah mapping: hasil baru dievaluasi, tidak ada flood alert historis.
- [ ] Restart E-MAS saat Khanza tetap terbuka.
- [ ] Restart Khanza/bridge saat E-MAS tetap berjalan.
- [ ] Setelah recovery, hanya satu bridge dan satu prescription source aktif.

## Performance and fallback

- [ ] Popup/audio tetap responsif ketika registry mencatat unmapped A lalu resep B dan C dibuka cepat.
- [ ] Jika lingkungan MySQL tersedia: pilih adapter MySQL, pastikan Desktop listener tidak aktif, lalu lakukan satu smoke DDI.

## Sign-off

- Operator farmasi: __________________  Tanggal: __________
- IT / integrasi: _____________________  Tanggal: __________
- Hasil: [ ] PASS  [ ] HOLD

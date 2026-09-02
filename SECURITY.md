# Keamanan

## Pelaporan

Temuan keamanan dilaporkan langsung kepada Product Owner dan IT rumah sakit.
Jangan memasukkan data pasien, password, connection string, atau secret API
ke tiket umum, screenshot, commit, maupun log.

## Kontrol sampai Sprint 22

- Tidak ada password administrator bawaan.
- Password disimpan dengan Argon2id dan salt unik.
- Akun pengguna bersifat individual.
- Konfigurasi aplikasi tidak menyimpan kredensial Khanza.
- Audit tidak dapat diedit melalui UI.
- Database lokal menggunakan foreign key, WAL, dan busy timeout.
- Integrasi Khanza memakai akun dan session read-only melalui empat view.
- Silent pilot menyimpan hasil validasi tanpa menampilkan alert operasional.
- Workbook validasi/UAT dibatasi untuk kasus sintetis/anonim dan menolak
  formula pada sheet impor.
- Gate pilot dan dual sign-off dicatat dalam database/audit serta tidak dapat
  mengubah mode aplikasi otomatis.
- Build rilis menolak runtime selain Python 3.13 64-bit dan toolchain yang tidak
  lengkap; hasil preflight dicatat sebagai JSON mesin-baca.
- Isi ONEDIR dan installer dicatat dengan SHA-256 per file. Symlink, private key,
  dan nama file secret umum menutup gate distribusi.
- Executable wajib mencapai health `READY` pada database sementara; drill
  backup, restore, rollback, dan upgrade ulang wajib lulus.
- Sesi go-live terikat checksum release dan installer; PASS tanpa file bukti
  ber-checksum ditolak.
- Attestation klinis, teknis, dan pengambil keputusan GO wajib independen.
- Ledger keputusan go-live append-only; expiry, perubahan versi/schema, atau
  kerusakan hash menahan GO secara fail-closed.
- `EMSS_REQUIRE_SIGNATURE=1` membuat Authenticode `Valid` sebagai gate wajib.
- Rollout terbatas hanya menerima acceptance GO yang belum kedaluwarsa dan
  cocok dengan versi/schema aktif; kondisi invalid selalu fail-closed.
- Scope workstation dan wave dibatasi; hanya satu wave dapat aktif.
- Ambang insiden dan insiden CRITICAL memicu auto-halt. Klinis dan IT dapat
  melakukan emergency halt, sedangkan resume memerlukan role teknis.
- Ringkasan insiden tidak disimpan mentah; ledger hanya menyimpan hash,
  severity, dan jumlah workstation terdampak.
- Ledger rollout append-only dan keputusan COMPLETE/ROLLBACK immutable.
- Surveillance hanya menerima rollout COMPLETED serta memverifikasi ledger
  go-live dan rollout sebelum capture, attestation, atau promotion.
- Snapshot hanya memuat angka agregat non-MOCK, health, dan status audit; tidak
  memuat nomor resep, identitas pasien, atau teks klinis.
- Ringkasan isu dan remediasi hanya disimpan sebagai SHA-256.
- Snapshot basi, data observasi kosong, backlog operasional, isu terbuka, expiry,
  atau kerusakan ledger menahan promotion secara fail-closed.
- Production release record hanya menerima surveillance `PROMOTED` dan
  mengikat versi, schema, environment, installer, serta checksum installer.
- Evidence Authenticode/waiver, clean-host, preservasi data, rollback/restore,
  dan change approval divalidasi terhadap kontrak JSON dan disimpan sebagai
  metadata/checksum immutable; evidence tidak boleh memuat identitas pasien.
- Waiver, record, dan deployment window memiliki expiry. Status di luar window,
  revocation, kerusakan ledger, atau perubahan binding menutup authorization.
- Pengambil keputusan produksi wajib berbeda dari pembuat record, recorder
  evidence, dan approver perubahan. Emergency rollback hanya mencatat order
  manual yang diaudit dan tidak mengeksekusi perubahan produksi.
- Evidence package ZIP menolak traversal, symlink, enkripsi, duplikasi,
  anggota tak dideklarasikan, ukuran berlebih, checksum/binding yang salah,
  serta key identitas pasien. Semua verification attempt tersimpan append-only.
- Verifikasi terbaru wajib `VALID` dan cocok dengan snapshot evidence aktif;
  verification invalid yang lebih baru menutup gate secara fail-closed.
- Deployment ceremony hanya dapat dimulai dalam window aktif dan memerlukan
  attestation teknis/klinis dari akun berbeda. Ceremony terminal immutable.
- Decision maker produksi juga wajib independen dari verifier package, pembuat
  ceremony, dan kedua attestor. Receipt menyatakan `NOT_PERFORMED_BY_EMSS`.
- Dossier UAT hanya menerima qualification `QUALIFIED` yang cocok dengan
  versi/schema aktif dan checksum installer exact.
- Readiness evidence UAT divalidasi format, binding, freshness, expiry, serta
  key identitas pasien; database hanya menyimpan metadata dan SHA-256.
- Kit UAT tidak berisi hasil PASS: seluruh scenario diekspor `NOT_RECORDED` dan
  execution berstatus `NOT_STARTED`.
- Result attempt UAT append-only; latest result per scenario menentukan gate.
  Result baru atau issue baru mencabut dual sign-off yang telah diberikan.
- Issue UAT menyimpan ringkasan/remediasi sebagai SHA-256. Scenario tidak
  lengkap, non-PASS, issue terbuka, window/expiry, atau ledger rusak menutup
  acceptance secara fail-closed.
- Attestor dossier, tester, signatory execution, dan decision maker dipisahkan.
  UAT acceptance dapat dicabut dan tidak pernah memberi production authorization.

## Batasan

Sprint 22 menyediakan workflow software menuju UAT operasional, tetapi belum
berarti UAT rumah sakit telah dilaksanakan atau Production Ready.
Artefak lokal belum ditandatangani Authenticode dan belum memiliki waiver nyata.
Pelaksanaan UAT nyata, validasi klinis, silent pilot, pengujian installer
Windows bersih, preservasi/rollback pada host representatif, alert-fatigue
review, acceptance aktual, change approval, deployment window, dan keputusan
produksi rumah sakit masih wajib. Fixture test sintetis tidak menggantikan
attestation operasional oleh akun individual.

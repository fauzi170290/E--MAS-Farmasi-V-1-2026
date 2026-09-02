-- DRAFT UNTUK CLONE UJI SAJA. BELUM DITERAPKAN KE sik / DATABASE PELAYANAN.
-- Jalankan hanya setelah DBA memastikan target, backup, varian source dan izin.
-- Tetap empat view/SELECT grants. e-MSS sendiri tidak menjalankan DDL ini.
-- Pasangkan dengan header/master dari khanza_integration_views_mariadb104.sql.
-- Kolom header tambahan wajib disediakan DBA:
-- validation_token = gabungan tgl_perawatan/jam dan tgl_penyerahan/jam_penyerahan.
-- item_basis = FINAL_CANDIDATE (bukan FINAL sebelum kontrak final disetujui).
-- composition_complete = 0 (fail-closed sampai relasi final dibuktikan).
-- Relasi no_rawat + tgl_perawatan + jam tidak membawa kunci no_resep di detail.
-- >1 resep pada tuple tersebut atau kode di beberapa racikan adalah AMBIGU.
-- Tidak ada fallback ke resep awal untuk resep tervalidasi dengan detail kosong.

CREATE OR REPLACE SQL SECURITY DEFINER VIEW vw_emss_prescription_item AS
SELECT rd.no_resep, CONCAT('R:',rd.kode_brng,':',LEFT(SHA2(COALESCE(rd.aturan_pakai,''),256),16)) AS source_item_key,
       rd.kode_brng, COALESCE(db.nama_brng,rd.kode_brng) AS nama_brng,
       SUM(rd.jml) AS jumlah, rd.aturan_pakai, CAST('' AS CHAR(1)) AS rute
FROM resep_dokter rd
JOIN resep_obat ro ON ro.no_resep=rd.no_resep
LEFT JOIN databarang db ON db.kode_brng=rd.kode_brng
WHERE CAST(ro.tgl_perawatan AS CHAR)='0000-00-00'
GROUP BY rd.no_resep,rd.kode_brng,db.nama_brng,rd.aturan_pakai
UNION ALL
SELECT ro.no_resep, CONCAT('F:',d.kode_brng) AS source_item_key,
       d.kode_brng, COALESCE(db.nama_brng,d.kode_brng), SUM(d.jml),
       CAST('' AS CHAR(1)), CAST('' AS CHAR(1))
FROM resep_obat ro
JOIN detail_pemberian_obat d ON d.no_rawat=ro.no_rawat AND d.tgl_perawatan=ro.tgl_perawatan AND d.jam=ro.jam
LEFT JOIN databarang db ON db.kode_brng=d.kode_brng
WHERE CAST(ro.tgl_perawatan AS CHAR)<>'0000-00-00'
  AND (SELECT COUNT(*) FROM resep_obat other WHERE other.no_rawat=ro.no_rawat
       AND other.tgl_perawatan=ro.tgl_perawatan AND other.jam=ro.jam)=1
  AND NOT EXISTS (SELECT 1 FROM detail_obat_racikan c WHERE c.no_rawat=d.no_rawat
       AND c.tgl_perawatan=d.tgl_perawatan AND c.jam=d.jam AND c.kode_brng=d.kode_brng)
GROUP BY ro.no_resep,d.kode_brng,db.nama_brng;

CREATE OR REPLACE SQL SECURITY DEFINER VIEW vw_emss_compound_item AS
SELECT rd.no_resep, CONCAT('C:',rd.no_racik,':',rd.kode_brng) AS source_item_key,
       rd.kode_brng, COALESCE(db.nama_brng,rd.kode_brng) AS nama_brng,
       rd.jml AS jumlah, COALESCE(r.aturan_pakai,'') AS aturan_pakai,
       CAST('' AS CHAR(1)) AS rute, rd.no_racik
FROM resep_dokter_racikan_detail rd
JOIN resep_obat ro ON ro.no_resep=rd.no_resep
LEFT JOIN resep_dokter_racikan r ON r.no_resep=rd.no_resep AND r.no_racik=rd.no_racik
LEFT JOIN databarang db ON db.kode_brng=rd.kode_brng
WHERE CAST(ro.tgl_perawatan AS CHAR)='0000-00-00'
UNION ALL
SELECT ro.no_resep, CONCAT('FC:',c.no_racik,':',c.kode_brng), c.kode_brng,
       COALESCE(db.nama_brng,c.kode_brng), SUM(d.jml), COALESCE(r.aturan_pakai,''),
       CAST('' AS CHAR(1)), c.no_racik
FROM resep_obat ro
JOIN detail_obat_racikan c ON c.no_rawat=ro.no_rawat AND c.tgl_perawatan=ro.tgl_perawatan AND c.jam=ro.jam
JOIN detail_pemberian_obat d ON d.no_rawat=c.no_rawat AND d.tgl_perawatan=c.tgl_perawatan
     AND d.jam=c.jam AND d.kode_brng=c.kode_brng
LEFT JOIN obat_racikan r ON r.no_rawat=c.no_rawat AND r.tgl_perawatan=c.tgl_perawatan
     AND r.jam=c.jam AND r.no_racik=c.no_racik
LEFT JOIN databarang db ON db.kode_brng=c.kode_brng
WHERE CAST(ro.tgl_perawatan AS CHAR)<>'0000-00-00'
  AND (SELECT COUNT(*) FROM resep_obat other WHERE other.no_rawat=ro.no_rawat
       AND other.tgl_perawatan=ro.tgl_perawatan AND other.jam=ro.jam)=1
  AND (SELECT COUNT(*) FROM detail_obat_racikan other WHERE other.no_rawat=c.no_rawat
       AND other.tgl_perawatan=c.tgl_perawatan AND other.jam=c.jam AND other.kode_brng=c.kode_brng)=1
GROUP BY ro.no_resep,c.no_racik,c.kode_brng,db.nama_brng,r.aturan_pakai;

-- Dilarang menyatakan composition_complete=1 hanya karena kedua view berisi baris.
-- Periksa obat reguler yang berbagi kode dengan racikan, batch/depo, transaksi
-- gagal/rollback, pembatalan, penggantian obat dan ketidakunikan tuple sebelum
-- reviewer/IT menyetujui kontrak. Skrip ini hanya kandidat ekstraksi final.

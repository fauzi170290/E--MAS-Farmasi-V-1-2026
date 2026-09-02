-- e-MSS Farmasi RS - view integrasi Khanza (MariaDB 10.4)
-- Disusun dari struktur sik.sql yang diberikan pemilik produk.
--
-- KESELAMATAN:
-- 1. Jalankan hanya pada database UJI/CLONE setelah ditinjau DBA.
-- 2. Script ini hanya membuat/mengganti empat VIEW; tidak mengubah data Khanza.
-- 3. Aplikasi e-MSS hanya diberi SELECT pada empat view ini.
-- 4. Nama database tidak ditulis di sini. Pilih database clone yang benar dahulu.
-- 5. FINAL berarti komposisi resep dokter telah masuk tahap validasi/proses farmasi
--    menurut resep_obat; bukan bukti obat telah diberikan kepada pasien.

CREATE OR REPLACE SQL SECURITY DEFINER VIEW vw_emss_prescription_header AS
SELECT
    ro.no_resep AS no_resep,
    ro.no_rawat AS no_rawat,
    ro.status AS asal_layanan,
    rp.no_rkm_medis AS no_rm,
    ps.nm_pasien AS nama_pasien,
    COALESCE(NULLIF(pl.nm_poli, ''), NULLIF(rp.kd_poli, ''), ro.status) AS unit_depo,
    COALESCE(NULLIF(dr.nm_dokter, ''), ro.kd_dokter) AS dokter,
    CASE
        WHEN NULLIF(CAST(ro.tgl_penyerahan AS CHAR), '0000-00-00') IS NOT NULL
            THEN 'DISERAHKAN'
        WHEN NULLIF(CAST(ro.tgl_perawatan AS CHAR), '0000-00-00') IS NOT NULL
            THEN 'DIPROSES_FARMASI'
        ELSE 'DIRESEPKAN'
    END AS status_resep,
    CASE
        WHEN NULLIF(CAST(ro.tgl_penyerahan AS CHAR), '0000-00-00') IS NOT NULL
          OR NULLIF(CAST(ro.tgl_perawatan AS CHAR), '0000-00-00') IS NOT NULL
        THEN SHA2(CONCAT_WS('|', CONVERT(ro.no_resep USING utf8mb4), CAST(ro.tgl_perawatan AS CHAR),
            CAST(ro.jam AS CHAR), CAST(ro.tgl_penyerahan AS CHAR),
            CAST(ro.jam_penyerahan AS CHAR)), 256)
        ELSE ''
    END AS validation_token,
    CASE
        WHEN NULLIF(CAST(ro.tgl_penyerahan AS CHAR), '0000-00-00') IS NOT NULL
          OR NULLIF(CAST(ro.tgl_perawatan AS CHAR), '0000-00-00') IS NOT NULL
        THEN 'FINAL'
        ELSE 'PRESCRIBED'
    END AS item_basis,
    CASE
        WHEN NULLIF(CAST(ro.tgl_penyerahan AS CHAR), '0000-00-00') IS NOT NULL
          OR NULLIF(CAST(ro.tgl_perawatan AS CHAR), '0000-00-00') IS NOT NULL
        THEN 1 ELSE 0
    END AS composition_complete,
    CASE
        WHEN NULLIF(CAST(ro.tgl_penyerahan AS CHAR), '0000-00-00') IS NOT NULL
            THEN STR_TO_DATE(
                CONCAT(CAST(ro.tgl_penyerahan AS CHAR), ' ', CAST(ro.jam_penyerahan AS CHAR)),
                '%Y-%m-%d %H:%i:%s'
            )
        WHEN NULLIF(CAST(ro.tgl_perawatan AS CHAR), '0000-00-00') IS NOT NULL
            THEN STR_TO_DATE(
                CONCAT(CAST(ro.tgl_perawatan AS CHAR), ' ', CAST(ro.jam AS CHAR)),
                '%Y-%m-%d %H:%i:%s'
            )
        ELSE STR_TO_DATE(
            CONCAT(CAST(ro.tgl_peresepan AS CHAR), ' ', CAST(ro.jam_peresepan AS CHAR)),
            '%Y-%m-%d %H:%i:%s'
        )
    END AS changed_at
FROM resep_obat AS ro
LEFT JOIN reg_periksa AS rp ON rp.no_rawat = ro.no_rawat
LEFT JOIN pasien AS ps ON ps.no_rkm_medis = rp.no_rkm_medis
LEFT JOIN dokter AS dr ON dr.kd_dokter = ro.kd_dokter
LEFT JOIN poliklinik AS pl ON pl.kd_poli = rp.kd_poli;

CREATE OR REPLACE SQL SECURITY DEFINER VIEW vw_emss_prescription_item AS
SELECT
    rd.no_resep AS no_resep,
    CONCAT(
        'R:', rd.kode_brng, ':',
        CONVERT(
            LEFT(SHA2(COALESCE(rd.aturan_pakai, ''), 256), 16)
            USING latin1
        )
    ) AS source_item_key,
    rd.kode_brng AS kode_brng,
    COALESCE(NULLIF(db.nama_brng, ''), rd.kode_brng) AS nama_brng,
    SUM(rd.jml) AS jumlah,
    rd.aturan_pakai AS aturan_pakai,
    CAST('' AS CHAR(1)) AS rute
FROM resep_dokter AS rd
LEFT JOIN databarang AS db ON db.kode_brng = rd.kode_brng
GROUP BY
    rd.no_resep,
    rd.kode_brng,
    COALESCE(NULLIF(db.nama_brng, ''), rd.kode_brng),
    rd.aturan_pakai;

CREATE OR REPLACE SQL SECURITY DEFINER VIEW vw_emss_compound_item AS
SELECT
    rdd.no_resep AS no_resep,
    CONCAT('C:', rdd.no_racik, ':', rdd.kode_brng) AS source_item_key,
    rdd.kode_brng AS kode_brng,
    COALESCE(NULLIF(db.nama_brng, ''), rdd.kode_brng) AS nama_brng,
    rdd.jml AS jumlah,
    COALESCE(rr.aturan_pakai, '') AS aturan_pakai,
    CAST('' AS CHAR(1)) AS rute,
    rdd.no_racik AS no_racik
FROM resep_dokter_racikan_detail AS rdd
LEFT JOIN resep_dokter_racikan AS rr
    ON rr.no_resep = rdd.no_resep
   AND rr.no_racik = rdd.no_racik
LEFT JOIN databarang AS db ON db.kode_brng = rdd.kode_brng;

CREATE OR REPLACE SQL SECURITY DEFINER VIEW vw_emss_drug_master AS
SELECT
    db.kode_brng AS kode_brng,
    db.nama_brng AS nama_brng,
    CASE WHEN db.status = '1' THEN 1 ELSE 0 END AS aktif
FROM databarang AS db;

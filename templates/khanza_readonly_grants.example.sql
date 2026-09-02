-- CONTOH SAJA. DBA wajib mengganti nama database, host workstation, dan password.
-- Jangan jalankan dengan placeholder dan jangan memakai host '%'.
-- Pembuatan view dilakukan DBA; akun e-MSS tidak menerima hak ke tabel dasar.

CREATE USER 'emss_readonly'@'IP_WORKSTATION' IDENTIFIED BY 'PASSWORD_KUAT_DARI_DBA';
GRANT SELECT ON NAMA_DATABASE_UJI.vw_emss_prescription_header
    TO 'emss_readonly'@'IP_WORKSTATION';
GRANT SELECT ON NAMA_DATABASE_UJI.vw_emss_prescription_item
    TO 'emss_readonly'@'IP_WORKSTATION';
GRANT SELECT ON NAMA_DATABASE_UJI.vw_emss_compound_item
    TO 'emss_readonly'@'IP_WORKSTATION';
GRANT SELECT ON NAMA_DATABASE_UJI.vw_emss_drug_master
    TO 'emss_readonly'@'IP_WORKSTATION';


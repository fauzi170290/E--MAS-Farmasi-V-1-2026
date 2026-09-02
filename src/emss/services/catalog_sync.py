from dataclasses import dataclass
from pathlib import Path
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from emss.audit.service import AuditEvent
from emss.database.catalog_models import DrugMaster, DrugComponentMapping
from emss.importexport.drug_import import DrugImportService, DRUG_HEADERS, COMPONENT_HEADERS, normalize_name
from emss.importexport.xlsx_writer import XlsxSheet, write_xlsx


@dataclass(frozen=True)
class CatalogSyncResult:
    read: int
    inserted: int
    preserved: int


class CatalogSyncService:
    def __init__(self, database, audit, adapter):
        self.database, self.audit, self.adapter = database, audit, adapter

    def sync(self, actor):
        if self.adapter is None:
            raise ValueError('Konfigurasi adapter Khanza terlebih dahulu.')
        with self.database.session() as session:
            DrugImportService._require_manager(session, actor)
        self.adapter.test_connection()
        cursor, source = '', {}
        while True:
            page = self.adapter.get_active_drug_master(cursor, 500)
            if not page:
                break
            for r in page:
                if not r.khanza_code or r.khanza_code <= cursor or r.khanza_code in source:
                    raise ValueError('Paginasi master tidak valid; sinkronisasi dibatalkan.')
                source[r.khanza_code] = r
            cursor = page[-1].khanza_code
            if len(source) > 100000:
                raise ValueError('Master melebihi batas 100.000; hubungi IT.')
        inserted = 0
        with self.database.session() as session:
            DrugImportService._require_manager(session, actor)
            for code, r in source.items():
                existing = session.scalar(select(DrugMaster).where(DrugMaster.khanza_code == code))
                if existing is None:
                    session.add(DrugMaster(khanza_code=code, display_name=r.display_name,
                        normalized_name=normalize_name(r.display_name), source_version='KHANZA-VIEW',
                        source_mapping_status='UNMAPPED', review_status='PENDING_REVIEW',
                        mapping_method='KHANZA_READ_ONLY', component_count=0, is_active=r.active))
                    inserted += 1
            self.audit.append(session, AuditEvent(category='MASTER_DATA', action='KHANZA_MASTER_SYNC',
                outcome='SUCCESS', actor_user_id=actor, details={'read': len(source), 'inserted': inserted,
                'preserved': len(source) - inserted, 'mapping_activated': 0}))
            session.commit()
        return CatalogSyncResult(len(source), inserted, len(source) - inserted)

    def export_mapping_workbook(self, path: Path, actor):
        headers = sorted(DRUG_HEADERS)
        component_headers = sorted(COMPONENT_HEADERS)
        master, components = [headers], [component_headers]
        with self.database.session() as session:
            DrugImportService._require_manager(session, actor)
            drugs = session.scalars(select(DrugMaster).options(selectinload(DrugMaster.components)
                .selectinload(DrugComponentMapping.ingredient)).order_by(DrugMaster.khanza_code)).all()
            for d in drugs:
                mappings = sorted(d.components, key=lambda m: m.component_order)
                data = dict(database_version='MAPPING-REVIEW', khanza_code=d.khanza_code,
                    khanza_name_display=d.display_name, khanza_name_normalized_source=d.normalized_name,
                    standard_active_ingredients=';'.join(m.ingredient.standard_name for m in mappings),
                    component_count=d.component_count, mapping_status=d.source_mapping_status,
                    mapping_method=d.mapping_method, mapping_note=d.mapping_note or '', rx_row_count=0,
                    episode_count=0, name_variants=d.display_name)
                master.append([data.get(h, '') for h in headers])
                for m in mappings:
                    data = dict(database_version='MAPPING-REVIEW', khanza_code=d.khanza_code,
                        khanza_name_display=d.display_name, component_order=m.component_order,
                        standard_active_ingredient=m.ingredient.standard_name,
                        mapping_status=d.source_mapping_status, mapping_method=d.mapping_method)
                    components.append([data.get(h, '') for h in component_headers])
        return write_xlsx(path, [XlsxSheet('DRUG_MASTER_KHANZA', master, [24] * len(headers)),
            XlsxSheet('DRUG_COMPONENT_MAP', components, [26] * len(component_headers)),
            XlsxSheet('PETUNJUK', [ ['Petunjuk'],
                ['Isi zat aktif di DRUG_MASTER_KHANZA dan satu baris per komponen di DRUG_COMPONENT_MAP.'],
                ['Gunakan urutan komponen 1,2,...; jumlah komponen dan daftar zat harus sama.'],
                ['Mapping MAPPED hanya bila seluruh komponen dikenali; jangan menebak zat dari nama merek.'],
                ['Preview lalu commit PENDING_REVIEW; reviewer berwenang menyetujui melalui aplikasi.'],
                ['Tidak ada rule DDI atau persetujuan klinis yang diaktifkan oleh export ini.']], [110])])

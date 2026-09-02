from pathlib import Path
import pytest
from sqlalchemy import select

from emss.services.catalog_sync import CatalogSyncService
from emss.database.catalog_models import DrugMaster
from emss.integrations.khanza import MockKhanzaAdapter, DrugMasterRow


def test_catalog_sync_preserves_mapping_and_exports_reviewable_workbook(app_container, tmp_path):
    actor = app_container.users.create_first_admin(username='admin.sync', display_name='Admin Sintetis', password='Frasa uji sinkronisasi 2026!')
    adapter = MockKhanzaAdapter()
    adapter.get_active_drug_master = lambda cursor, limit: tuple(r for r in (
        DrugMasterRow('SYNTH-A', 'Obat Sintetis A'), DrugMasterRow('SYNTH-B', 'Obat Sintetis B')) if r.khanza_code > cursor)[:limit]
    service = CatalogSyncService(app_container.database, app_container.audit, adapter)
    result = service.sync(actor.id)
    assert result.inserted == 2 and result.preserved == 0
    with app_container.database.session() as session:
        first = session.scalar(select(DrugMaster).where(DrugMaster.khanza_code == 'SYNTH-A'))
        first.mapping_note = 'catatan manual harus dipreservasi'
        session.commit()
    assert service.sync(actor.id).preserved == 2
    with app_container.database.session() as session:
        first = session.scalar(select(DrugMaster).where(DrugMaster.khanza_code == 'SYNTH-A'))
        assert first.mapping_note == 'catatan manual harus dipreservasi'
        assert first.review_status == 'PENDING_REVIEW'
    target = service.export_mapping_workbook(tmp_path / 'mapping.xlsx', actor.id)
    preview = app_container.drug_import.preview(target, actor.id)
    assert preview.commit_allowed and preview.invalid_rows == 0
    assert app_container.catalog.summary().active_components == 0


def test_catalog_sync_permission_and_invalid_pagination(app_container):
    service = CatalogSyncService(app_container.database, app_container.audit, None)
    with pytest.raises(ValueError): service.sync('missing')
    actor = app_container.users.create_first_admin(username='admin.sync.bad', display_name='Uji', password='Frasa uji sinkronisasi 2026!')
    adapter = MockKhanzaAdapter()
    adapter.get_active_drug_master = lambda *a: (DrugMasterRow('A', 'A'),)
    service.adapter = adapter
    with pytest.raises(ValueError): service.sync(actor.id)
    assert app_container.catalog.summary().total_drugs == 0


def test_export_preserves_existing_multi_ingredient_mapping(app_container, tmp_path):
    from test_screening_engine import _admin, _seed
    actor = _admin(app_container)
    _seed(app_container, actor.id, combination=True)
    service = CatalogSyncService(app_container.database, app_container.audit, MockKhanzaAdapter())
    path = service.export_mapping_workbook(tmp_path / 'existing-mapping.xlsx', actor.id)
    preview = app_container.drug_import.preview(path, actor.id)
    assert preview.commit_allowed and preview.invalid_rows == 0
    assert app_container.catalog.summary().active_components == 3


def test_catalog_hides_legacy_short_code_when_zero_padded_khanza_code_exists(app_container):
    with app_container.database.session() as session:
        for code in ('3087', '000003087'):
            session.add(DrugMaster(khanza_code=code, display_name='OBAT UJI 20 MG',
                normalized_name='obat uji 20 mg', source_version='TEST',
                source_mapping_status='UNMAPPED', review_status='PENDING_REVIEW',
                mapping_method='TEST', component_count=0, is_active=True))
        session.commit()
    rows = app_container.catalog.list_drugs('OBAT UJI')
    assert [row.khanza_code for row in rows] == ['000003087']

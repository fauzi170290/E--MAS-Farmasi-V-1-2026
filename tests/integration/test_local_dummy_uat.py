from datetime import datetime, UTC
from types import SimpleNamespace
import pytest
from emss.config.settings import AppSettings, AppEnvironment, KhanzaAdapterMode, default_data_dir
from emss.integrations.khanza.local_dummy import LocalDummyKhanzaAdapter
from emss.integrations.khanza.domain import KhanzaDataError
from emss.services.local_dummy_mapping import match_native_code, reconcile_dummy_mapping


def dummy_settings(tmp_path, **overrides):
    values = dict(environment='test', data_dir=tmp_path / 'isolated', khanza_adapter='mysql_dummy',
        khanza_dummy_consent=True, khanza_dummy_prescriptions=('DUMMY-001', 'DUMMY-002'),
        pharmacy_care_setting='RALAN')
    values.update(overrides)
    return AppSettings(**values)


@pytest.mark.parametrize('override', [
    {'environment': 'production'}, {'environment': 'advisory_pilot'}, {'environment': 'silent_pilot'},
    {'khanza_dummy_consent': False}, {'khanza_host': '192.0.2.4'},
    {'khanza_dummy_prescriptions': ()}, {'khanza_dummy_prescriptions': ('x', 'x')},
    {'khanza_dummy_prescriptions': ("x' OR 1=1",)}, {'data_dir': default_data_dir()},
])
def test_dummy_adapter_rejects_unsafe_configuration(tmp_path, override):
    with pytest.raises(ValueError):
        dummy_settings(tmp_path, **override)


def test_dummy_adapter_queries_only_explicit_ids_and_never_identities(tmp_path):
    adapter = LocalDummyKhanzaAdapter(dummy_settings(tmp_path), engine=object())
    seen = []
    def rows(sql, params):
        seen.append((sql, params))
        return [{'no_resep': params['no_resep'], 'changed_at': datetime(2026, 8, 28, tzinfo=UTC),
            'status_resep': 'DIPROSES_FARMASI'}]
    adapter._rows = rows
    assert len(adapter.scan_prescriptions('', 10)) == 2
    assert len(adapter.get_new_prescriptions(None, 1)) == 1
    header = adapter.get_prescription_header('DUMMY-001')
    assert not header.composition_complete and header.item_basis == 'UNVERIFIED'
    assert header.patient_id == '' and header.no_rawat == ''
    for sql, params in seen:
        assert 'WHERE no_resep = :no_resep' in sql
        assert '*' not in sql and 'nama_pasien' not in sql and 'no_rawat' not in sql
        assert params['no_resep'] in {'DUMMY-001', 'DUMMY-002'}
    for operation in (adapter.get_prescription_header, adapter.get_prescription_items, adapter.get_compounded_items,
                      adapter.get_prescription_revision, adapter.get_snapshot):
        with pytest.raises(KhanzaDataError):
            operation('REAL-PATIENT')


def test_dummy_revalidates_mutated_settings(tmp_path):
    settings = dummy_settings(tmp_path)
    settings.environment = AppEnvironment.PRODUCTION
    with pytest.raises(ValueError):
        LocalDummyKhanzaAdapter(settings, engine=object())


def row(code, name='OBAT UJI 20 MG'):
    return SimpleNamespace(khanza_code=code, display_name=name)


def test_numeric_mapping_requires_unique_code_and_exact_name():
    source, native = row('3087'), row('000003087', ' obat uji 20 mg  ')
    assert match_native_code(native.khanza_code, native.display_name, [source], [native]) is source
    assert match_native_code(native.khanza_code, 'OBAT UJI 10 MG', [source], [native]) is None
    assert match_native_code(native.khanza_code, native.display_name, [source, row('03087')], [native]) is None
    assert match_native_code(native.khanza_code, native.display_name, [source], [native, row('03087')]) is None
    assert match_native_code('ABC', native.display_name, [source], [native]) is None
    assert match_native_code('000001074', 'ASPILET TAB', [row('6017', 'ASPILET TAB 100 MG')], [row('000001074')]) is None


def test_reconciliation_does_not_run_on_other_environments(app_container):
    with pytest.raises(ValueError):
        reconcile_dummy_mapping(app_container, [], 'not-authorized')


def test_reconciliation_copies_pending_components_once_without_approvals(app_container):
    from sqlalchemy import select, func
    from emss.database.catalog_models import DrugMaster, DrugComponentMapping, ActiveIngredient
    c = app_container
    actor = c.users.create_first_admin(username='test.mapping', display_name='Admin uji', password='Uji#Aman2026')
    c.settings.khanza_adapter = KhanzaAdapterMode.MYSQL_DUMMY
    with c.database.session() as session:
        ingredient = ActiveIngredient(standard_name='zat sintetis', normalized_name='zat sintetis')
        drug = DrugMaster(khanza_code='123', display_name='OBAT UJI 20 MG', normalized_name='obat uji 20 mg',
            source_version='SYNTHETIC', source_mapping_status='MAPPED', review_status='PENDING_REVIEW',
            mapping_method='USER_SOURCE', component_count=1)
        session.add_all([ingredient, drug])
        session.flush()
        session.add(DrugComponentMapping(drug_id=drug.id, ingredient_id=ingredient.id, component_order=1,
            source_mapping_status='MAPPED', mapping_method='USER_SOURCE', review_status='PENDING_REVIEW',
            is_active=False, source_version='SYNTHETIC'))
        session.commit()
    native = [row('000123'), row('000456', 'TIDAK DIKENAL')]
    assert [r['status'] for r in reconcile_dummy_mapping(c, native, actor.id)] == ['COPIED_FOR_DUMMY_UAT', 'UNMAPPED']
    assert reconcile_dummy_mapping(c, native, actor.id)[0]['status'] == 'EXISTING_PRESERVED'
    with c.database.session() as session:
        assert session.scalar(select(func.count()).select_from(DrugMaster)) == 2
        mappings = session.scalars(select(DrugComponentMapping)).all()
        assert len(mappings) == 2 and all(not m.is_active and m.review_status == 'PENDING_REVIEW' for m in mappings)
        assert session.scalar(select(DrugMaster).where(DrugMaster.khanza_code == '000456')) is None


def test_user_confirmed_ingredient_does_not_invent_strength_or_approval(app_container):
    import json
    from sqlalchemy import select
    from emss.database.catalog_models import ActiveIngredient, DrugMaster, DrugComponentMapping
    from emss.services.local_dummy_mapping import add_user_confirmed_dummy_mapping
    c = app_container
    actor = c.users.create_first_admin(username='test.confirm', display_name='Persiapan uji', password='Uji#Aman2026')
    args = dict(code='DUMMY-CODE', display_name='OBAT UJI', ingredient_name='zat sintetis',
                user_statement='Pernyataan sintetis untuk pengujian')
    with pytest.raises(ValueError):
        add_user_confirmed_dummy_mapping(c, actor.id, **args)
    c.settings.khanza_adapter = KhanzaAdapterMode.MYSQL_DUMMY
    c.settings.pharmacy_care_setting = 'RALAN'
    c.settings.khanza_dummy_consent = True
    c.settings.khanza_dummy_prescriptions = ('DUMMY-001',)
    with c.database.session() as session:
        session.add(ActiveIngredient(standard_name='zat sintetis', normalized_name='zat sintetis'))
        session.commit()
    assert add_user_confirmed_dummy_mapping(c, actor.id, **args)['status'] == 'APPLIED_FOR_DUMMY_UAT'
    assert add_user_confirmed_dummy_mapping(c, actor.id, **args)['status'] == 'ALREADY_APPLIED'
    with pytest.raises(ValueError, match='tidak ditimpa'):
        add_user_confirmed_dummy_mapping(c, actor.id, **{**args, 'strength_mg': 100})
    with c.database.session() as session:
        drug = session.scalar(select(DrugMaster).where(DrugMaster.khanza_code == 'DUMMY-CODE'))
        component = session.scalar(select(DrugComponentMapping).where(DrugComponentMapping.drug_id == drug.id))
        assert drug.display_name == 'OBAT UJI' and drug.review_status == 'PENDING_REVIEW'
        assert json.loads(drug.mapping_note)['strength_mg'] is None
        assert component.review_status == 'PENDING_REVIEW' and not component.is_active


@pytest.mark.parametrize('context,allowed', [
    ({'platform':'win32','window_station':'WinSta0','desktop':'Default'}, True),
    ({'platform':'win32','window_station':'WinSta0','desktop':'CodexSandboxDesktop-test'}, False),
    ({'platform':'win32','window_station':'Service-0','desktop':'Default'}, False),
    ({'platform':'win32'}, False),
    ({'platform':'win32','window_station':'WinSta0','desktop':'Default','qt_platform':'offscreen'}, False),
])
def test_dummy_gui_requires_visible_user_desktop(monkeypatch, context, allowed):
    from emss.desktop import interactive
    monkeypatch.setattr(interactive, 'current_desktop_context', lambda: context)
    if allowed:
        assert interactive.require_interactive_desktop() == context
    else:
        with pytest.raises(interactive.DesktopLaunchError):
            interactive.require_interactive_desktop()


def test_dummy_launcher_rejects_invisible_desktop_before_database_or_instance_lock(monkeypatch, tmp_path):
    import importlib.util
    from pathlib import Path
    from emss.desktop.interactive import DesktopLaunchError
    path = Path(__file__).resolve().parents[2] / 'scripts/local_dummy_uat.py'
    spec = importlib.util.spec_from_file_location('test_dummy_launcher', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    def reject():
        raise DesktopLaunchError('Isolated desktop')
    def never_prepare(_):
        pytest.fail('Must not prepare/open a runtime database on an invisible desktop')
    monkeypatch.setattr(module, 'require_interactive_desktop', reject)
    monkeypatch.setattr(module, 'prepare', never_prepare)
    assert module.main(['--workbook', 'unused.xlsx', '--data-dir', str(tmp_path / 'not-created'),
        '--recipe', 'DUMMY-001', '--allow-draft-dummy']) == 2
    assert not (tmp_path / 'not-created').exists()


def test_follow_dummy_patients_discovers_new_numbers_and_rejects_other_patients(monkeypatch, tmp_path):
    from test_mysql_khanza_contract import _contract_engine
    from sqlalchemy import text, bindparam, DateTime
    from datetime import timedelta
    engine, changed = _contract_engine()
    settings = dummy_settings(tmp_path, khanza_dummy_prescriptions=('RX-UJI-001',),
        khanza_dummy_follow_patients=True, khanza_dummy_show_patient_name=True)
    adapter = LocalDummyKhanzaAdapter(settings, engine=engine)
    with engine.begin() as conn:
        for key, patient, when in [('RX-UJI-003','RM-UJI',changed+timedelta(minutes=1)),
            ('RX-UJI-004','OTHER-PATIENT',changed+timedelta(minutes=2)),
            ('RX-OLD','RM-UJI',changed-timedelta(days=1))]:
            conn.execute(text('INSERT INTO vw_emss_prescription_header '
                '(no_resep,no_rm,nama_pasien,asal_layanan,status_resep,changed_at) '
                "VALUES (:key,:patient,:name,'ralan',:status,:when)")
                .bindparams(bindparam('when',type_=DateTime())),
                {'key':key,'patient':patient,'name':'Pasien Uji A','status':'DIPROSES_FARMASI','when':when})
    refs = adapter.scan_prescriptions('',500)
    assert [r.no_resep for r in refs] == ['RX-UJI-001','RX-UJI-003']
    assert [r.no_resep for r in adapter.scan_prescriptions('RX-UJI-001',1)] == ['RX-UJI-003']
    assert [r.no_resep for r in adapter.get_new_prescriptions(refs[0].cursor,1)] == ['RX-UJI-003']
    assert adapter.get_prescription_header('RX-UJI-003').patient_name == 'Pasien Uji A'
    for key in ('RX-UJI-002','RX-UJI-004','RX-OLD'):
        with pytest.raises(KhanzaDataError):
            adapter.get_snapshot(key)
    with engine.begin() as conn:
        conn.execute(text("UPDATE vw_emss_prescription_header SET no_rm='OTHER-PATIENT' WHERE no_resep='RX-UJI-001'"))
    assert [r.no_resep for r in adapter.scan_prescriptions('',500)] == ['RX-UJI-003']
    adapter.close()


def test_follow_dummy_fails_closed_without_seed_identity(tmp_path):
    from test_mysql_khanza_contract import _contract_engine
    from sqlalchemy import text
    engine, _ = _contract_engine()
    adapter = LocalDummyKhanzaAdapter(dummy_settings(tmp_path, khanza_dummy_prescriptions=('RX-UJI-001',),
        khanza_dummy_follow_patients=True), engine=engine)
    with engine.begin() as conn:
        conn.execute(text("UPDATE vw_emss_prescription_header SET no_rm='' WHERE no_resep='RX-UJI-001'"))
    with pytest.raises(KhanzaDataError, match='acuan tidak lengkap'):
        adapter.scan_prescriptions('',500)
    adapter.close()


@pytest.mark.parametrize('severity,validated,notify,category', [
    ('SERIOUS',False,False,''), ('SERIOUS',True,True,'major'),
    ('CONTRAINDICATED',False,False,''), ('CONTRAINDICATED',True,True,'contraindicated'),
    ('SIGNIFICANT',True,True,'significant-review'), ('NONE',True,False,''),
])
def test_dummy_notifications_only_after_validation_and_only_high(severity,validated,notify,category):
    from emss.alerts.notification import notification_decision
    screening = SimpleNamespace(risk_status='HIGH_RISK', completeness_status='INCOMPLETE')
    pair = SimpleNamespace(classification='INTERACTION_FOUND', severity_code=severity)
    decision, actual = notification_decision(screening,[pair],[],validated=validated,validated_high_only=True)
    assert (decision.notify,actual) == (notify,category)
    if notify:
        assert decision.title in {'MAYOR','KONTRAINDIKASI','INTERAKSI SIGNIFIKAN - WAJIB DITINJAU'}


def test_follow_monitor_detects_new_rx_then_validation_without_duplicates(app_container, monkeypatch):
    from test_mysql_khanza_contract import _contract_engine
    from test_screening_engine import _admin, _seed
    from sqlalchemy import text, bindparam, DateTime, select
    from datetime import timedelta
    from emss.services.khanza_polling import KhanzaPollingService
    from emss.database.queue_models import AlertEvent
    c = app_container
    actor = _admin(c)
    _seed(c,actor.id,version_status='DRAFT',approved_mapping=False,
        severity_code='SERIOUS',app_severity='HIGH_RISK',severity_rank=3)
    engine, changed = _contract_engine()
    c.settings.khanza_adapter = KhanzaAdapterMode.MYSQL_DUMMY
    c.settings.pharmacy_care_setting = 'RALAN'
    c.settings.khanza_dummy_consent = True
    c.settings.khanza_dummy_prescriptions = ('RX-UJI-001',)
    c.settings.khanza_dummy_follow_patients = True
    c.settings.khanza_dummy_show_patient_name = True
    c.settings.khanza_poll_interval_seconds = 3
    monkeypatch.setenv('EMSS_KHANZA_PASSWORD','synthetic-only')
    adapter = LocalDummyKhanzaAdapter(c.settings, engine=engine)
    clock = [changed.replace(tzinfo=UTC)]
    adapter.source_time = lambda: clock[0]
    polling = KhanzaPollingService(c.database,c.settings,adapter,c.screening,c.queue)
    polling.monitor.clock = lambda: clock[0]
    def cycle():
        result = polling.monitor.cycle(actor.id)
        clock[0] += timedelta(seconds=3)
        return result
    cycle()
    observed = cycle()
    if not observed.processed:  # Scoped reconcile and recent lanes may discover on adjacent cycles.
        observed = cycle()
    assert observed.processed == 1
    assert not c.queue.pending_screening_ids()  # Prescribed but not yet validated.
    with engine.begin() as conn:
        conn.execute(text("UPDATE vw_emss_prescription_header SET status_resep='DIPROSES_FARMASI' WHERE no_resep='RX-UJI-001'"))
    cycle()
    result = cycle()
    assert result.processed == 1
    alert = c.queue.enqueue_screening(result.screening_ids[0])
    assert alert.notify and alert.audio_category == 'major'
    c.queue.mark_alert_shown(alert.alert_id)
    assert cycle().processed == 0 and not c.queue.pending_screening_ids()
    with engine.begin() as conn:
        conn.execute(text('INSERT INTO vw_emss_prescription_header '
            '(no_resep,no_rm,nama_pasien,asal_layanan,status_resep,changed_at) '
            "VALUES (:key,:patient,:name,'ralan',:status,:when)")
            .bindparams(bindparam('when',type_=DateTime())),
            {'key':'RX-UJI-003','patient':'RM-UJI','name':'Pasien Uji A',
             'status':'DIPROSES_FARMASI','when':clock[0].replace(tzinfo=None)})
        conn.execute(text("INSERT INTO vw_emss_prescription_item (no_resep,source_item_key,kode_brng,nama_brng,jumlah) "
            "VALUES ('RX-UJI-003','ONLY-A','OBAT-A','Obat A',1)"))
    cycle()
    result = cycle()
    assert result.processed == 1  # New number picked up without restarting/retrying.
    alert = c.queue.enqueue_screening(result.screening_ids[0])
    assert not alert.notify and alert.audio_category == ''
    assert cycle().processed == 0
    with c.database.session() as session:
        assert sum(a.status == 'SHOWN' for a in session.scalars(select(AlertEvent))) == 1
    adapter.close()

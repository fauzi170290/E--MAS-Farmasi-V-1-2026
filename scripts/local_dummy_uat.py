"""Explicit local-only UAT launcher. Never edits installed config or either operational DB."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import secrets
import sys

SOURCE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE_ROOT / 'src'))

from sqlalchemy import select, func
from emss.app import build_application
from emss.audit.service import AuditEvent
from emss.config.settings import AppSettings, AppEnvironment, KhanzaAdapterMode
from emss.database.catalog_models import ImportBatch
from emss.database.models import AppUser
from emss.desktop.interactive import DesktopLaunchError, require_interactive_desktop
from emss.services.local_dummy_mapping import reconcile_dummy_mapping

SOURCE_SHA256 = '9f5283e7908fbfe679484344567b8b34e58b78ced80c8a3de9a38a805667420a'


def prepare(args):
    if not args.allow_draft_dummy:
        raise ValueError('Persetujuan penggunaan DRAFT pada resep dummy diperlukan')
    source = args.workbook.resolve(strict=True)
    if hashlib.sha256(source.read_bytes()).hexdigest() != SOURCE_SHA256:
        raise ValueError('Workbook berbeda dari sumber DDI yang sudah diperiksa; hentikan untuk review')
    data = args.data_dir.resolve()
    # This local launcher may write only inside this task workspace's work folder.
    work = SOURCE_ROOT.parent.resolve()
    if not data.is_relative_to(work) or data == work or data.is_relative_to(SOURCE_ROOT):
        raise ValueError('Direktori uji harus terpisah di dalam folder work task ini')
    marker = data / 'DUMMY_UAT_ONLY.json'
    scope = {'format': 'EMSS_LOCAL_DUMMY_UAT_V1', 'test_only': True,
        'recipes': sorted(args.recipe), 'source_sha256': SOURCE_SHA256,
        'authorization': 'Pengguna menyatakan 3 resep dummy dan mengizinkan DDI lokal, 28 Agustus 2026; bukan approval KFT.'}
    if data.exists() and any(data.iterdir()):
        if not marker.is_file() or json.loads(marker.read_text(encoding='utf-8')) != scope:
            raise ValueError('Direktori tidak memiliki penanda uji yang sesuai; tidak akan digunakan/ditimpa')
    import tomllib
    raw = tomllib.loads(args.installed_config.read_text(encoding='utf-8'))
    fields = {name: value for name, value in raw.items() if name.startswith('khanza_')}
    fields.update(khanza_adapter=KhanzaAdapterMode.MYSQL_DUMMY,
        khanza_dummy_prescriptions=tuple(args.recipe), khanza_dummy_consent=True,
        khanza_dummy_follow_patients=getattr(args, 'follow_seed_patients', False),
        khanza_dummy_show_patient_name=getattr(args, 'show_dummy_patient_names', False),
        khanza_polling_enabled=True, khanza_internal_polling_consent=True,
        khanza_poll_interval_seconds=3, khanza_stability_interval_seconds=2)
    settings = AppSettings(**fields, environment=AppEnvironment.TEST, data_dir=data,
        app_name='E-MAS Farmasi — UJI DUMMY LOKAL', allow_workstation_mode=True,
        workstation_label='UJI DUMMY', minimize_to_tray=False, backup_daily_enabled=False)
    # Read Machine credential into this UAT process only. No global environment changes.
    credential_source = 'PROCESS_ENVIRONMENT'
    if os.name == 'nt':
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                r'SYSTEM\CurrentControlSet\Control\Session Manager\Environment') as key:
                password = winreg.QueryValueEx(key, 'EMSS_KHANZA_PASSWORD')[0]
            if password:
                os.environ['EMSS_KHANZA_PASSWORD'] = password
                credential_source = 'WINDOWS_MACHINE_FOR_ISOLATED_UAT_PROCESS'
        except OSError:
            pass
    data.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps(scope, indent=2), encoding='utf-8')
    container = build_application(settings)
    try:
        container.khanza_adapter.test_connection()
        with container.database.session() as session:
            actor_id = session.scalar(select(AppUser.id).where(AppUser.normalized_username == 'uat.preparation'))
            if actor_id is None and session.scalar(select(func.count()).select_from(AppUser)):
                raise ValueError('Database berisi akun lain; bukan database UAT yang dibuat launcher ini')
        if actor_id is None:
            actor = container.users.create_first_admin(username='uat.preparation',
                display_name='Persiapan otomatis UAT (bukan reviewer klinis)', password='Uat#' + secrets.token_urlsafe(24))
            actor_id = actor.id
        container.bundled_ddi.apply_if_eligible(actor_id)
        container.bundled_mapping.apply_if_eligible(actor_id)
        with container.database.session() as session:
            existing = session.scalar(select(ImportBatch.id).where(ImportBatch.source_sha256 == SOURCE_SHA256,
                ImportBatch.status.in_(('COMMITTED', 'APPROVED'))))
        preview = None
        if existing is None:
            preview = container.drug_import.preview(source, actor_id)
            if not preview.commit_allowed:
                raise ValueError('Workbook gagal validasi; tidak diaktifkan')
            container.drug_import.commit(preview.batch_id, actor_id)
        native, cursor = [], ''
        while True:
            page = container.khanza_adapter.get_active_drug_master(cursor, 500)
            native.extend(page)
            if len(page) < 500:
                break
            if page[-1].khanza_code <= cursor or len(native) > 20000:
                raise ValueError('Pagination master tidak valid; persiapan dihentikan')
            cursor = page[-1].khanza_code
        mapping = reconcile_dummy_mapping(container, native, actor_id)
        report = {'test_only': True, 'operational_database_modified': False,
            'credential_source': credential_source, 'mapping': mapping,
            'import_preview_valid_rows': preview.valid_rows if preview else 'ALREADY_IMPORTED',
            'knowledge_status': 'DRAFT_UNCHANGED', 'rule_count': 5432,
            'poll_interval_seconds': 3, 'allowed_recipes': sorted(args.recipe),
            'follow_seed_patients': settings.khanza_dummy_follow_patients,
            'show_dummy_patient_names': settings.khanza_dummy_show_patient_name}
        with container.database.session() as session:
            container.audit.append(session, AuditEvent(category='INTEGRATION', action='LOCAL_DUMMY_UAT_AUTHORIZED',
                outcome='SUCCESS', actor_user_id=actor_id, details={**scope,
                    'follow_seed_patients': settings.khanza_dummy_follow_patients,
                    'show_dummy_patient_names': settings.khanza_dummy_show_patient_name,
                    'notification_policy': 'VALIDATED_MAJOR_CONTRAINDICATED_ONLY'}))
            session.commit()
        prefs = args.installed_config.parent / 'audio-preferences.json'
        local_prefs = data / 'audio-preferences.json'
        if prefs.is_file() and not local_prefs.exists():
            local_prefs.write_bytes(prefs.read_bytes())  # Paths only, never redistribute original audio files.
        (data / 'preparation-report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        return container
    except Exception:
        container.close()
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workbook', required=True, type=Path)
    parser.add_argument('--data-dir', required=True, type=Path)
    parser.add_argument('--installed-config', type=Path, default=Path('C:/ProgramData/eMSSFarmasi/config.toml'))
    parser.add_argument('--recipe', action='append', required=True)
    parser.add_argument('--allow-draft-dummy', action='store_true')
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--follow-seed-patients', action='store_true',
        help='Pantau resep baru sejak awal uji untuk pasien pada resep dummy acuan saja')
    parser.add_argument('--show-dummy-patient-names', action='store_true')
    args = parser.parse_args(argv)
    if not args.prepare_only:
        try:
            require_interactive_desktop()
        except DesktopLaunchError as exc:
            print(str(exc), flush=True)
            return 2
    container = prepare(args)
    try:
        if args.prepare_only:
            print('UAT_PREPARED: ' + str(container.settings.data_dir))
            return 0
        from emss.ui.application import run_gui
        return run_gui(container)
    finally:
        container.close()


if __name__ == '__main__':
    raise SystemExit(main())

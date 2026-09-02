"""Create pending native-code copies for UAT, with exact name + unique numeric-code evidence."""
import re
import json
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from emss.audit.service import AuditEvent
from emss.config.settings import AppEnvironment, KhanzaAdapterMode
from emss.database.catalog_models import DrugMaster, DrugComponentMapping, ActiveIngredient
from emss.importexport.drug_import import normalize_name


def numeric_code(value):
    return value.lstrip('0') or '0' if re.fullmatch('[0-9]+', value) else None


def match_native_code(code, name, source_rows, native_rows):
    key = numeric_code(code)
    if key is None:
        return None
    # Reject both source-side and target-side collisions, even if names agree.
    candidates = [row for row in source_rows if numeric_code(row.khanza_code) == key]
    targets = {row.khanza_code for row in native_rows if numeric_code(row.khanza_code) == key}
    if len(candidates) != 1 or len(targets) != 1:
        return None
    source = candidates[0]
    return source if normalize_name(source.display_name) == normalize_name(name) else None


def reconcile_dummy_mapping(container, native_rows, actor_user_id):
    settings = container.settings
    if settings.environment != AppEnvironment.TEST or settings.khanza_adapter != KhanzaAdapterMode.MYSQL_DUMMY:
        raise ValueError("Rekonsiliasi ini hanya untuk database uji dummy")
    report = []
    with container.database.session() as session:
        container.drug_import._require_manager(session, actor_user_id)
        rows = session.scalars(select(DrugMaster).options(selectinload(DrugMaster.components))).all()
        sources = [row for row in rows if row.mapping_method != 'UAT_NATIVE_CODE_FROM_SOURCE']
        existing = {row.khanza_code: row for row in rows}
        source_groups, native_groups = {}, {}
        for row in sources:
            source_groups.setdefault(numeric_code(row.khanza_code), []).append(row)
        for row in native_rows:
            native_groups.setdefault(numeric_code(row.khanza_code), []).append(row)
        for native in native_rows:
            key = numeric_code(native.khanza_code)
            match = match_native_code(native.khanza_code, native.display_name,
                source_groups.get(key, []), native_groups.get(key, []))
            item = {'native_code': native.khanza_code, 'display_name': native.display_name,
                    'source_code': match.khanza_code if match else None}
            report.append(item)
            if native.khanza_code in existing:
                item['status'] = 'EXISTING_PRESERVED'
                continue
            if match is None:
                item['status'] = 'UNMAPPED'
                continue
            if not match.is_active or match.source_mapping_status != 'MAPPED' or len(match.components) != match.component_count:
                item['status'] = 'SOURCE_INCOMPLETE'
                continue
            copy = DrugMaster(khanza_code=native.khanza_code, display_name=native.display_name.strip(),
                normalized_name=normalize_name(native.display_name), source_version=match.source_version,
                source_mapping_status=match.source_mapping_status, review_status='PENDING_REVIEW',
                mapping_method='UAT_NATIVE_CODE_FROM_SOURCE', component_count=match.component_count,
                mapping_note=f'UJI DUMMY: kode asal {match.khanza_code}; kode numerik unik dan nama sama. Bukan approval klinis.')
            session.add(copy)
            session.flush()
            for component in match.components:
                session.add(DrugComponentMapping(drug_id=copy.id, ingredient_id=component.ingredient_id,
                    component_order=component.component_order, source_mapping_status=component.source_mapping_status,
                    mapping_method='UAT_NATIVE_CODE_FROM_SOURCE', review_status='PENDING_REVIEW', is_active=False,
                    source_version=component.source_version))
            item['status'] = 'COPIED_FOR_DUMMY_UAT'
        container.audit.append(session, AuditEvent(category='INTEGRATION', action='DUMMY_MAPPING_RECONCILED',
            outcome='SUCCESS', actor_user_id=actor_user_id, details={'test_only': True, 'mappings': report}))
        session.commit()
    return report


def add_user_confirmed_dummy_mapping(container, actor_user_id, *, code, display_name,
                                     ingredient_name, user_statement, strength_mg=None):
    """Ingredient-only UAT mapping; an explicit user statement is not clinical approval."""
    settings = container.settings
    settings.validate_dummy_scope()
    if settings.environment != AppEnvironment.TEST or settings.khanza_adapter != KhanzaAdapterMode.MYSQL_DUMMY:
        raise ValueError('Konfirmasi ini hanya boleh diterapkan pada database uji dummy')
    if not code.strip() or not display_name.strip() or not user_statement.strip():
        raise ValueError('Kode, nama, dan pernyataan sumber harus diisi')
    details = {'test_only': True, 'code': code, 'display_name': display_name,
        'ingredient': normalize_name(ingredient_name), 'user_statement': user_statement,
        'strength_mg': strength_mg, 'strength_confirmed': strength_mg is not None,
        'clinical_approval': False}
    with container.database.session() as session:
        container.drug_import._require_manager(session, actor_user_id)
        ingredient = session.scalar(select(ActiveIngredient).where(
            ActiveIngredient.normalized_name == details['ingredient'], ActiveIngredient.is_active.is_(True)))
        if ingredient is None:
            raise ValueError('Zat aktif standar tidak ada dalam basis DDI')
        existing = session.scalar(select(DrugMaster).options(selectinload(DrugMaster.components)).where(
            DrugMaster.khanza_code == code))
        if existing is not None:
            if (existing.mapping_method == 'UAT_USER_CONFIRMED'
                and existing.mapping_note == json.dumps(details, sort_keys=True, ensure_ascii=False)
                and len(existing.components) == 1 and existing.components[0].ingredient_id == ingredient.id):
                return {'status': 'ALREADY_APPLIED', **details}
            raise ValueError('Kode sudah mempunyai master; tidak ditimpa otomatis')
        drug = DrugMaster(khanza_code=code, display_name=display_name, normalized_name=normalize_name(display_name),
            source_version='UAT-USER-CONFIRMATION', source_mapping_status='MAPPED', review_status='PENDING_REVIEW',
            mapping_method='UAT_USER_CONFIRMED', component_count=1,
            mapping_note=json.dumps(details, sort_keys=True, ensure_ascii=False))
        session.add(drug)
        session.flush()
        session.add(DrugComponentMapping(drug_id=drug.id, ingredient_id=ingredient.id, component_order=1,
            source_mapping_status='MAPPED', mapping_method='UAT_USER_CONFIRMED', review_status='PENDING_REVIEW',
            is_active=False, source_version='UAT-USER-CONFIRMATION'))
        container.audit.append(session, AuditEvent(category='INTEGRATION', action='DUMMY_USER_MAPPING_CONFIRMED',
            outcome='SUCCESS', actor_user_id=actor_user_id, entity_type='drug_master', entity_id=drug.id,
            details=details))
        session.commit()
    return {'status': 'APPLIED_FOR_DUMMY_UAT', **details}

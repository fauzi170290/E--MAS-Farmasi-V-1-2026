from __future__ import annotations
import gzip, hashlib, json
from dataclasses import dataclass
from pathlib import Path
from sqlalchemy import select
from emss.audit.service import AuditEvent, AuditService
from emss.database.catalog_models import ActiveIngredient, DrugAlias, DrugComponentMapping, DrugMaster, ImportBatch
from emss.database.engine import DatabaseManager
from emss.database.models import AppUser, Role, UserRole
from emss.importexport.drug_import import normalize_name
from emss.utils.resources import bundled_resource
from emss.utils.time import utc_now

BUNDLE_ID='MAPPING-KHANZA-20260831'
BUNDLE_FILE='mapping-khanza-20260831.json.gz'
MANIFEST_FILE='mapping-khanza-20260831.manifest.json'
EXPECTED_SOURCE_SHA256='68049818dfb4b4710f3176b00d809c50fb34a308f06423c66d5cee77af41f27a'
EXPECTED_BUNDLE_SHA256='dee704675ca4c9438d4c59944ef5fe33f58e51fe748af17a07aedd76dacff88e'
EXPECTED_SEMANTIC_SHA256='b67ea8087e9e0e79696ccec239309bef51555a88feecd5aa7df3376ab277b9b0'
EXPECTED_DRUG_COUNT=221
EXPECTED_CORRECTION_COUNT=193
EXPECTED_COMPONENT_COUNT=444

class BundledMappingError(ValueError): pass

@dataclass(frozen=True)
class BundledMappingResult:
    status:str; inserted:int; preserved:int; component_count:int

def _read_bundle(root:Path|None=None):
    folder=root or bundled_resource('seed')
    manifest=json.loads((folder/MANIFEST_FILE).read_text(encoding='utf-8'))
    packed=(folder/BUNDLE_FILE).read_bytes()
    if hashlib.sha256(packed).hexdigest()!=EXPECTED_BUNDLE_SHA256: raise BundledMappingError('Checksum bundle pemetaan tidak sesuai')
    raw=gzip.decompress(packed)
    if hashlib.sha256(raw).hexdigest()!=EXPECTED_SEMANTIC_SHA256: raise BundledMappingError('Checksum isi pemetaan tidak sesuai')
    payload=json.loads(raw)
    expected={'format':'EMAS_BUNDLED_MAPPING_V1','bundle_id':BUNDLE_ID,'source_sha256':EXPECTED_SOURCE_SHA256,
        'bundle_sha256':EXPECTED_BUNDLE_SHA256,'semantic_sha256':EXPECTED_SEMANTIC_SHA256,
        'drug_count':EXPECTED_DRUG_COUNT,'correction_count':EXPECTED_CORRECTION_COUNT,
        'component_count':EXPECTED_COMPONENT_COUNT,'patient_identity_included':False,'clinical_approval':False}
    for key,value in expected.items():
        actual=manifest.get(key) if key in manifest else payload.get(key)
        if actual!=value: raise BundledMappingError(f'Kontrak bundle pemetaan tidak sesuai: {key}')
    rows=payload.get('drugs',[])+payload.get('corrections',[])
    if len(payload.get('drugs',[]))!=EXPECTED_DRUG_COUNT or len(payload.get('corrections',[]))!=EXPECTED_CORRECTION_COUNT: raise BundledMappingError('Jumlah obat bundle pemetaan tidak sesuai')
    if sum(len(r.get('components',[])) for r in rows)!=EXPECTED_COMPONENT_COUNT: raise BundledMappingError('Jumlah kandungan bundle pemetaan tidak sesuai')
    if any(r.get('review_status')!='PENDING_REVIEW' or any(c.get('is_active') for c in r.get('components',[])) for r in rows): raise BundledMappingError('Bundle pemetaan harus menunggu tinjauan dan nonaktif')
    return manifest,payload,rows

class BundledMappingService:
    def __init__(self,database:DatabaseManager,audit:AuditService): self.database=database;self.audit=audit
    def apply_if_eligible(self,actor_user_id:str|None=None):
        manifest,payload,rows=_read_bundle()
        with self.database.session() as session:
            prior=session.scalar(select(ImportBatch).where(ImportBatch.import_type=='BUNDLED_MAPPING',ImportBatch.source_version==BUNDLE_ID))
            if prior:
                summary=json.loads(prior.summary_json)
                if prior.source_sha256!=EXPECTED_SOURCE_SHA256 or summary.get('bundle_sha256')!=EXPECTED_BUNDLE_SHA256: raise BundledMappingError('Catatan bundle pemetaan tidak sesuai')
                return BundledMappingResult('ALREADY_APPLIED',prior.inserted_rows,prior.unchanged_rows,EXPECTED_COMPONENT_COUNT)
            actor=self._actor(session,actor_user_id)
            if actor is None: return BundledMappingResult('DEFERRED_NO_ADMIN',0,0,EXPECTED_COMPONENT_COUNT)
            legacy=session.scalar(select(ImportBatch).where(
                ImportBatch.import_type=='BUNDLED_MAPPING',
                ImportBatch.source_version=='MAPPING-KHANZA-20260828'))
            if legacy and (legacy.source_sha256!='9f5283e7908fbfe679484344567b8b34e58b78ced80c8a3de9a38a805667420a'
                    or json.loads(legacy.summary_json).get('bundle_sha256')!='a364f4af37a14b6c9ce47c7fa44e60b44ca7f9eda987528a70a7f8f683044768'):
                raise BundledMappingError('Catatan bundle pemetaan sebelumnya tidak sesuai')
            ingredients={r.normalized_name:r for r in session.scalars(select(ActiveIngredient)).all()}
            existing={r for r in session.scalars(select(DrugMaster.khanza_code)).all()}
            inserted=preserved=component_count=0
            seen=set()
            for row in rows:
                code=row['code']
                if code in seen or code in existing or (legacy and row['source_version'] != BUNDLE_ID):
                    preserved+=1; continue
                seen.add(code)
                components=[]
                for data in row['components']:
                    normalized=normalize_name(data['ingredient'])
                    ingredient=ingredients.get(normalized)
                    if ingredient is None:
                        ingredient=ActiveIngredient(standard_name=data['ingredient'],normalized_name=normalized,is_active=True)
                        session.add(ingredient);session.flush()
                        ingredients[normalized]=ingredient
                    components.append((data,ingredient))
                drug=DrugMaster(khanza_code=code,display_name=row['name'],normalized_name=normalize_name(row['name']),
                    source_version=row['source_version'],source_mapping_status=row['source_mapping_status'],
                    review_status='PENDING_REVIEW',mapping_method=row['method'],mapping_note=row.get('note'),
                    component_count=row['component_count'],is_active=True)
                session.add(drug);session.flush()
                aliases=[]
                for alias in row.get('aliases',[]):
                    normalized=normalize_name(alias)
                    if normalized and normalized not in aliases:
                        aliases.append(normalized);session.add(DrugAlias(drug_id=drug.id,alias_name=alias,normalized_alias=normalized,source='BUNDLED_MAPPING',is_preferred=False))
                for data,ingredient in components:
                    session.add(DrugComponentMapping(drug_id=drug.id,ingredient_id=ingredient.id,component_order=data['order'],
                        source_mapping_status=data['source_mapping_status'],mapping_method=data['method'],review_status='PENDING_REVIEW',is_active=False,source_version=data['source_version']))
                    component_count+=1
                inserted+=1
            summary={'bundle_id':BUNDLE_ID,'bundle_sha256':EXPECTED_BUNDLE_SHA256,'semantic_sha256':EXPECTED_SEMANTIC_SHA256,
                'source_sha256':EXPECTED_SOURCE_SHA256,'drug_count':EXPECTED_DRUG_COUNT,'correction_count':EXPECTED_CORRECTION_COUNT,
                'inserted':inserted,'preserved':preserved,'clinical_approval':False,'patient_identity_included':False}
            session.add(ImportBatch(import_type='BUNDLED_MAPPING',source_filename=MANIFEST_FILE,source_sha256=EXPECTED_SOURCE_SHA256,
                source_version=BUNDLE_ID,status='COMMITTED',requested_by=actor.id,total_rows=len(rows),valid_rows=len(rows),invalid_rows=0,
                inserted_rows=inserted,updated_rows=0,unchanged_rows=preserved,summary_json=json.dumps(summary,sort_keys=True),completed_at=utc_now()))
            self.audit.append(session,AuditEvent(category='KNOWLEDGE_BASE',action='BUNDLED_MAPPING_APPLIED',outcome='SUCCESS',actor_user_id=actor.id,details=summary))
            session.commit()
            return BundledMappingResult('APPLIED',inserted,preserved,component_count)
    @staticmethod
    def _actor(session,actor_user_id):
        q=select(AppUser).join(UserRole,UserRole.user_id==AppUser.id).join(Role,Role.id==UserRole.role_id).where(AppUser.is_active.is_(True),Role.code.in_({'SUPER_ADMIN','IT_ADMIN','KNOWLEDGE_ADMIN'})).order_by(AppUser.created_at).limit(1)
        if actor_user_id: q=q.where(AppUser.id==actor_user_id)
        return session.scalar(q)

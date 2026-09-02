from __future__ import annotations

from dataclasses import dataclass

from emss.audit.service import AuditService
from emss.config.settings import AppEnvironment, AppSettings
from emss.database.engine import DatabaseManager
from emss.health.service import HealthService
from emss.importexport.drug_import import DrugImportService
from emss.importexport.ddi_import import DdiImportService
from emss.importexport.ddi_export import DdiExportService
from emss.logging.setup import configure_logging
from emss.security.passwords import PasswordService
from emss.services.authentication import AuthenticationService
from emss.services.backup import BackupService
from emss.services.catalog import DrugCatalogService
from emss.services.reference import ReferenceService
from emss.services.knowledge import KnowledgeBaseService
from emss.services.mock_screening import MockPrescriptionService
from emss.services.queue import ProcessingQueueService
from emss.services.interventions import PharmacistInterventionService
from emss.services.dashboard import DashboardService
from emss.services.screening import DdiScreeningService
from emss.services.medication_safety import MedicationSafetyService
from emss.services.users import UserService
from emss.services.workstation import WorkstationAccessService
from emss.services.clinical_validation import ClinicalValidationService
from emss.services.go_live import GoLiveService
from emss.services.limited_rollout import LimitedRolloutService
from emss.services.surveillance import SurveillanceService
from emss.services.production_release import ProductionReleaseService
from emss.services.production_evidence import ProductionEvidenceService
from emss.services.uat_release import UatReleaseService
from emss.services.bundled_ddi import BundledDdiSeedService
from emss.services.bundled_mapping import BundledMappingService
from emss.services.h3_activation import H3ActivationService
from emss.integrations.khanza import KhanzaPrescriptionAdapter
from emss.services.khanza_polling import (
    KhanzaPollingService,
    build_khanza_adapter,
)


@dataclass
class ApplicationContainer:
    settings: AppSettings
    database: DatabaseManager
    audit: AuditService
    passwords: PasswordService
    users: UserService
    authentication: AuthenticationService
    catalog: DrugCatalogService
    reference: ReferenceService
    drug_import: DrugImportService
    knowledge: KnowledgeBaseService
    ddi_import: DdiImportService
    ddi_export: DdiExportService
    screening: DdiScreeningService
    medication_safety: MedicationSafetyService
    mock_prescriptions: MockPrescriptionService
    queue: ProcessingQueueService
    interventions: PharmacistInterventionService
    dashboard: DashboardService
    khanza_adapter: KhanzaPrescriptionAdapter | None
    khanza_polling: KhanzaPollingService
    workstation_access: WorkstationAccessService
    health: HealthService
    backup: BackupService
    clinical_validation: ClinicalValidationService
    go_live: GoLiveService
    limited_rollout: LimitedRolloutService
    surveillance: SurveillanceService
    production_release: ProductionReleaseService
    production_evidence: ProductionEvidenceService
    uat_release: UatReleaseService
    bundled_ddi: BundledDdiSeedService
    bundled_mapping: BundledMappingService
    h3_activation: H3ActivationService

    def close(self) -> None:
        if self.khanza_adapter is not None:
            self.khanza_adapter.close()
        self.database.dispose()


def build_application(
    settings: AppSettings, *, run_migrations: bool = True
) -> ApplicationContainer:
    settings.ensure_directories()
    configure_logging(settings.log_dir, settings.log_level)

    database = DatabaseManager(settings)
    if run_migrations:
        database.migrate()
    audit = AuditService()
    backup = BackupService(settings, database, audit)
    passwords = PasswordService()
    users = UserService(database, passwords, audit)
    authentication = AuthenticationService(
        database, passwords, audit, settings
    )
    catalog = DrugCatalogService(database)
    drug_import = DrugImportService(database, audit)
    knowledge = KnowledgeBaseService(database, audit)
    ddi_import = DdiImportService(database, audit)
    ddi_export = DdiExportService(database, audit)
    medication_safety = MedicationSafetyService(database, audit)
    screening = DdiScreeningService(
        database, audit, settings, medication_safety
    )
    mock_prescriptions = MockPrescriptionService(database, screening)
    workstation_access = WorkstationAccessService(database, audit, settings)
    queue = ProcessingQueueService(database, audit, settings)
    interventions = PharmacistInterventionService(database, audit)
    dashboard = DashboardService(database, audit)
    khanza_adapter = build_khanza_adapter(settings)
    khanza_polling = KhanzaPollingService(
        database, settings, khanza_adapter, screening, queue
    )
    health = HealthService(settings, database, audit, khanza_polling)
    clinical_validation = ClinicalValidationService(
        database, audit, medication_safety
    )
    go_live = GoLiveService(database, audit)
    limited_rollout = LimitedRolloutService(database, audit, go_live)
    surveillance = SurveillanceService(database, audit, health, limited_rollout)
    production_release = ProductionReleaseService(database, audit, surveillance)
    production_evidence = ProductionEvidenceService(production_release)
    uat_release = UatReleaseService(database, audit)
    bundled_ddi = BundledDdiSeedService(database, audit)
    bundled_mapping = BundledMappingService(database, audit)
    h3_activation = H3ActivationService(database, audit)
    if run_migrations and settings.environment == AppEnvironment.PRODUCTION:
        bundled_ddi.apply_if_eligible()
        bundled_mapping.apply_if_eligible()
    return ApplicationContainer(
        settings=settings,
        database=database,
        audit=audit,
        passwords=passwords,
        users=users,
        authentication=authentication,
        catalog=catalog,
        reference=ReferenceService(database, audit),
        drug_import=drug_import,
        knowledge=knowledge,
        ddi_import=ddi_import,
        ddi_export=ddi_export,
        screening=screening,
        medication_safety=medication_safety,
        mock_prescriptions=mock_prescriptions,
        queue=queue,
        interventions=interventions,
        dashboard=dashboard,
        khanza_adapter=khanza_adapter,
        khanza_polling=khanza_polling,
        workstation_access=workstation_access,
        health=health,
        backup=backup,
        clinical_validation=clinical_validation,
        go_live=go_live,
        limited_rollout=limited_rollout,
        surveillance=surveillance,
        production_release=production_release,
        production_evidence=production_evidence,
        uat_release=uat_release,
        bundled_ddi=bundled_ddi,
        bundled_mapping=bundled_mapping,
        h3_activation=h3_activation,
    )

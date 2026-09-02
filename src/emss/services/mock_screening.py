from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select

from emss.database.catalog_models import DrugComponentMapping, DrugMaster
from emss.database.engine import DatabaseManager
from emss.database.knowledge_models import DdiRule, KnowledgeBaseVersion
from emss.services.screening import (
    DdiScreeningService,
    PrescriptionInput,
    PrescriptionItemInput,
    ScreeningResult,
    ScreeningUnavailableError,
)


@dataclass(frozen=True)
class MockScenario:
    code: str
    label: str
    description: str


MOCK_SCENARIOS = (
    MockScenario(
        "CRITICAL",
        "Interaksi CRITICAL",
        "Mengambil pasangan CONTRAINDICATED dari master DDI.",
    ),
    MockScenario(
        "HIGH_RISK",
        "Interaksi HIGH_RISK",
        "Mengambil pasangan SERIOUS dari master DDI.",
    ),
    MockScenario(
        "NOT_ASSESSED",
        "Pasangan belum dinilai",
        "Membuktikan bahwa belum dinilai tidak ditampilkan sebagai aman.",
    ),
    MockScenario(
        "UNMAPPED",
        "Obat belum dipetakan",
        "Menguji dimensi kelengkapan UNMAPPED.",
    ),
    MockScenario(
        "REVISION",
        "Resep berubah / revisi",
        "Mengubah jumlah obat dan membuat revisi baru tanpa menghapus riwayat.",
    ),
)


class MockPrescriptionService:
    def __init__(
        self, database: DatabaseManager, screening: DdiScreeningService
    ) -> None:
        self.database = database
        self.screening = screening

    def scenarios(self) -> tuple[MockScenario, ...]:
        return MOCK_SCENARIOS

    def simulate(self, code: str, actor_user_id: str) -> ScreeningResult:
        scenario = code.strip().upper()
        if scenario == "UNMAPPED":
            return self.screening.screen(
                PrescriptionInput(
                    no_resep="MOCK-UNMAPPED-DEMO",
                    patient_name="PASIEN SIMULASI",
                    service_unit="FARMASI MOCK",
                    items=(
                        PrescriptionItemInput(
                            source_item_key="1",
                            khanza_code="MOCK-TIDAK-TERPETAKAN",
                            display_name="Obat simulasi tanpa mapping",
                            quantity="1",
                        ),
                    ),
                ),
                actor_user_id,
                mock_mode=True,
            )

        version, rule, codes = self._resolve_rule(scenario)
        items = tuple(
            PrescriptionItemInput(
                source_item_key=str(index),
                khanza_code=drug_code,
                display_name=drug_name,
                quantity="1",
                directions="Simulasi",
                route="Oral",
            )
            for index, (drug_code, drug_name) in enumerate(codes, start=1)
        )
        if scenario == "REVISION":
            no_resep = "MOCK-REVISION-DEMO"
            self.screening.screen(
                PrescriptionInput(no_resep=no_resep, items=items),
                actor_user_id,
                mock_mode=True,
                version_id=version.id,
            )
            changed = list(items)
            changed[0] = PrescriptionItemInput(
                source_item_key=items[0].source_item_key,
                khanza_code=items[0].khanza_code,
                display_name=items[0].display_name,
                quantity="2",
                directions=items[0].directions,
                route=items[0].route,
            )
            return self.screening.screen(
                PrescriptionInput(no_resep=no_resep, items=tuple(changed)),
                actor_user_id,
                mock_mode=True,
                version_id=version.id,
            )
        return self.screening.screen(
            PrescriptionInput(
                no_resep=f"MOCK-{scenario}-DEMO",
                patient_name="PASIEN SIMULASI",
                service_unit="FARMASI MOCK",
                items=items,
            ),
            actor_user_id,
            mock_mode=True,
            version_id=version.id,
        )

    def _resolve_rule(
        self, scenario: str
    ) -> tuple[KnowledgeBaseVersion, DdiRule, tuple[tuple[str, str], ...]]:
        with self.database.session() as session:
            version = session.scalar(
                select(KnowledgeBaseVersion)
                .where(KnowledgeBaseVersion.status.in_(("DRAFT", "PUBLISHED")))
                .order_by(KnowledgeBaseVersion.created_at.desc())
                .limit(1)
            )
            if version is None:
                raise ScreeningUnavailableError(
                    "Belum ada knowledge base DRAFT/PUBLISHED untuk simulasi"
                )
            statement = select(DdiRule).where(
                DdiRule.knowledge_base_version_id == version.id
            )
            if scenario == "CRITICAL":
                statement = statement.where(
                    DdiRule.interaction_status == "INTERACTION_FOUND",
                    DdiRule.severity_code == "CONTRAINDICATED",
                )
            elif scenario == "HIGH_RISK":
                statement = statement.where(
                    DdiRule.interaction_status == "INTERACTION_FOUND",
                    DdiRule.severity_code == "SERIOUS",
                )
            elif scenario == "NOT_ASSESSED":
                statement = statement.where(
                    DdiRule.interaction_status.in_(
                        ("NOT_ASSESSABLE", "EXCLUDED")
                    )
                    | (
                        (DdiRule.interaction_status == "ASSESSED_NO_INTERACTION")
                        & (
                            DdiRule.source_validation_status
                            == "NO_INTERACTION_QUICK_CLOSURE"
                        )
                    )
                )
            elif scenario == "REVISION":
                statement = statement.where(
                    DdiRule.interaction_status == "INTERACTION_FOUND"
                )
            else:
                raise ScreeningUnavailableError(
                    f"Skenario MOCK tidak dikenal: {scenario}"
                )
            candidates = session.scalars(
                statement.order_by(DdiRule.severity_rank.desc()).limit(100)
            ).all()
            for rule in candidates:
                codes = self._drug_codes_for_rule(
                    session, rule.ingredient_low_id, rule.ingredient_high_id
                )
                if codes is not None:
                    return version, rule, codes
        raise ScreeningUnavailableError(
            "Rule skenario ada, tetapi pasangan obat Khanza belum dapat dipetakan"
        )

    @staticmethod
    def _drug_codes_for_rule(
        session, ingredient_low_id: str, ingredient_high_id: str
    ) -> tuple[tuple[str, str], tuple[str, str]] | None:
        rows = session.execute(
            select(
                DrugComponentMapping.ingredient_id,
                DrugMaster.khanza_code,
                DrugMaster.display_name,
            )
            .join(DrugMaster, DrugMaster.id == DrugComponentMapping.drug_id)
            .where(
                DrugComponentMapping.ingredient_id.in_(
                    (ingredient_low_id, ingredient_high_id)
                ),
                DrugMaster.is_active.is_(True),
            )
            .order_by(DrugMaster.khanza_code)
        ).all()
        by_ingredient: dict[str, tuple[str, str]] = {}
        for ingredient_id, khanza_code, display_name in rows:
            by_ingredient.setdefault(
                ingredient_id, (khanza_code, display_name)
            )
        low = by_ingredient.get(ingredient_low_id)
        high = by_ingredient.get(ingredient_high_id)
        if low is None or high is None or low[0] == high[0]:
            return None
        return low, high

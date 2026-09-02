from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from emss.database.catalog_models import (
    DrugComponentMapping,
    DrugMaster,
    ImportBatch,
)
from emss.database.engine import DatabaseManager


@dataclass(frozen=True)
class CatalogDrugItem:
    id: str
    khanza_code: str
    display_name: str
    source_mapping_status: str
    review_status: str
    component_count: int
    ingredients: tuple[str, ...]
    mapping_method: str
    source_version: str
    is_active: bool = True
    source_system: str = "KHANZA"
    kfa_product_code: str = ""
    kfa_product_type: str = ""
    ingredient_kfa_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class CatalogSummary:
    total_drugs: int
    source_mapped: int
    source_unmapped: int
    pending_review: int
    approved: int
    active_components: int


@dataclass(frozen=True)
class ImportBatchItem:
    id: str
    filename: str
    source_version: str | None
    status: str
    total_rows: int
    invalid_rows: int
    created_at: str


class DrugCatalogService:
    def __init__(self, database: DatabaseManager) -> None:
        self.database = database

    def list_drugs(
        self, search: str = "", limit: int = 500, *, include_inactive: bool = False
    ) -> list[CatalogDrugItem]:
        limit = max(1, min(limit, 2000))
        with self.database.session() as session:
            statement = (
                select(DrugMaster)
                .options(
                    selectinload(DrugMaster.components).selectinload(
                        DrugComponentMapping.ingredient
                    )
                )
                .where(True if include_inactive else DrugMaster.is_active.is_(True))
                .order_by(DrugMaster.display_name, DrugMaster.khanza_code)
                .limit(limit)
            )
            query = search.strip()
            if query:
                pattern = f"%{query}%"
                statement = statement.where(
                    or_(
                        DrugMaster.khanza_code.ilike(pattern),
                        DrugMaster.kfa_product_code.ilike(pattern),
                        DrugMaster.display_name.ilike(pattern),
                        DrugMaster.normalized_name.ilike(pattern),
                    )
                )
            rows = session.scalars(statement).all()
            # Some legacy imports stored the same Khanza item with a shortened
            # numeric code.  Do not delete either record or change screening
            # history here; the master view simply prefers the complete,
            # zero-padded Khanza code when the name and numeric code agree.
            rows = self._visible_rows(rows)[:limit]
            return [
                CatalogDrugItem(
                    id=row.id,
                    khanza_code=row.khanza_code,
                    display_name=row.display_name,
                    source_mapping_status=row.source_mapping_status,
                    review_status=row.review_status,
                    component_count=row.component_count,
                    ingredients=tuple(
                        mapping.ingredient.standard_name
                        for mapping in sorted(
                            row.components,
                            key=lambda item: item.component_order,
                        )
                    ),
                    mapping_method=row.mapping_method,
                    source_version=row.source_version,
                    is_active=row.is_active,
                    source_system=row.source_system,
                    kfa_product_code=row.kfa_product_code or "",
                    kfa_product_type=row.kfa_product_type or "",
                    ingredient_kfa_codes=tuple(
                        mapping.ingredient.kfa_bza_code or ""
                        for mapping in sorted(row.components, key=lambda item: item.component_order)
                    ),
                )
                for row in rows
            ]

    @staticmethod
    def _visible_rows(rows: list[DrugMaster]) -> list[DrugMaster]:
        selected: dict[tuple[str, str], DrugMaster] = {}
        for row in rows:
            code = row.khanza_code.strip()
            numeric = code.isdigit()
            identity = (
                row.normalized_name,
                (code.lstrip('0') or '0') if numeric else code,
            )
            previous = selected.get(identity)
            if previous is None:
                selected[identity] = row
                continue
            # A longer all-numeric code is the zero-padded/source format.  A
            # deterministic tie-breaker keeps the result stable.
            if (len(code), code) > (len(previous.khanza_code.strip()), previous.khanza_code.strip()):
                selected[identity] = row
        return sorted(selected.values(), key=lambda row: (row.display_name, row.khanza_code))

    def list_active_ingredients(self, search: str = "", limit: int = 1000) -> list[str]:
        """Return canonical active-ingredient names for pair selectors."""
        from emss.database.catalog_models import ActiveIngredient

        with self.database.session() as session:
            statement = select(ActiveIngredient.standard_name).where(
                ActiveIngredient.is_active.is_(True)
            )
            query = search.strip()
            if query:
                statement = statement.where(
                    ActiveIngredient.normalized_name.ilike(f"%{query.lower()}%")
                )
            rows = session.scalars(
                statement.order_by(ActiveIngredient.standard_name).limit(max(1, min(limit, 5000)))
            ).all()
            return [str(value) for value in rows]

    def summary(self) -> CatalogSummary:
        with self.database.session() as session:
            total = session.scalar(
                select(func.count()).select_from(DrugMaster)
            ) or 0
            source_mapped = session.scalar(
                select(func.count())
                .select_from(DrugMaster)
                .where(DrugMaster.source_mapping_status == "MAPPED")
            ) or 0
            source_unmapped = session.scalar(
                select(func.count())
                .select_from(DrugMaster)
                .where(DrugMaster.source_mapping_status != "MAPPED")
            ) or 0
            pending = session.scalar(
                select(func.count())
                .select_from(DrugMaster)
                .where(DrugMaster.review_status == "PENDING_REVIEW")
            ) or 0
            approved = session.scalar(
                select(func.count())
                .select_from(DrugMaster)
                .where(DrugMaster.review_status == "APPROVED")
            ) or 0
            active_components = session.scalar(
                select(func.count())
                .select_from(DrugComponentMapping)
                .where(DrugComponentMapping.is_active.is_(True))
            ) or 0
            return CatalogSummary(
                total_drugs=total,
                source_mapped=source_mapped,
                source_unmapped=source_unmapped,
                pending_review=pending,
                approved=approved,
                active_components=active_components,
            )

    def recent_batches(self, limit: int = 20) -> list[ImportBatchItem]:
        with self.database.session() as session:
            rows = session.scalars(
                select(ImportBatch)
                .where(ImportBatch.import_type == "DRUG_CATALOG")
                .order_by(ImportBatch.created_at.desc())
                .limit(max(1, min(limit, 100)))
            ).all()
            return [
                ImportBatchItem(
                    id=row.id,
                    filename=row.source_filename,
                    source_version=row.source_version,
                    status=row.status,
                    total_rows=row.total_rows,
                    invalid_rows=row.invalid_rows,
                    created_at=row.created_at.isoformat(timespec="seconds"),
                )
                for row in rows
            ]

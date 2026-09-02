"""Public service exports loaded lazily to avoid import-order side effects."""

from __future__ import annotations

from importlib import import_module
from typing import Any


_EXPORTS = {
    "AccountLockedError": ("authentication", "AccountLockedError"),
    "AuthenticatedUser": ("authentication", "AuthenticatedUser"),
    "AuthenticationError": ("authentication", "AuthenticationError"),
    "AuthenticationService": ("authentication", "AuthenticationService"),
    "DrugCatalogService": ("catalog", "DrugCatalogService"),
    "DuplicateUsernameError": ("users", "DuplicateUsernameError"),
    "InvalidCurrentPasswordError": ("users", "InvalidCurrentPasswordError"),
    "KnowledgeBaseService": ("knowledge", "KnowledgeBaseService"),
    "KnowledgeError": ("knowledge", "KnowledgeError"),
    "KnowledgePermissionError": ("knowledge", "KnowledgePermissionError"),
    "KnowledgeStateError": ("knowledge", "KnowledgeStateError"),
    "ManualDdiRule": ("knowledge", "ManualDdiRule"),
    "MockPrescriptionService": ("mock_screening", "MockPrescriptionService"),
    "MockScenario": ("mock_screening", "MockScenario"),
    "ProcessingQueueService": ("queue", "ProcessingQueueService"),
    "QueueError": ("queue", "QueueError"),
    "ClinicalValidationService": (
        "clinical_validation",
        "ClinicalValidationService",
    ),
    "GoLiveService": ("go_live", "GoLiveService"),
    "LimitedRolloutService": ("limited_rollout", "LimitedRolloutService"),
    "SurveillanceService": ("surveillance", "SurveillanceService"),
    "DdiScreeningService": ("screening", "DdiScreeningService"),
    "PrescriptionInput": ("screening", "PrescriptionInput"),
    "PrescriptionItemInput": ("screening", "PrescriptionItemInput"),
    "ScreeningError": ("screening", "ScreeningError"),
    "ScreeningResult": ("screening", "ScreeningResult"),
    "ScreeningUnavailableError": ("screening", "ScreeningUnavailableError"),
    "UserService": ("users", "UserService"),
    "UserValidationError": ("users", "UserValidationError"),
    "WorkstationAccessService": ("workstation", "WorkstationAccessService"),
    "WorkstationModeError": ("workstation", "WorkstationModeError"),
}

__all__ = list(_EXPORTS)


def __getattr__(name: str) -> Any:
    try:
        module_name, attribute = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(name) from exc
    value = getattr(import_module(f"emss.services.{module_name}"), attribute)
    globals()[name] = value
    return value

from __future__ import annotations

import pytest

from emss import importexport, services
from emss.importexport.drug_import import DrugImportService
from emss.services.users import UserService


def test_public_package_exports_remain_compatible_and_lazy():
    assert services.UserService is UserService
    assert importexport.DrugImportService is DrugImportService


def test_lazy_packages_reject_unknown_exports():
    with pytest.raises(AttributeError):
        getattr(services, "UnknownService")
    with pytest.raises(AttributeError):
        getattr(importexport, "UnknownImporter")

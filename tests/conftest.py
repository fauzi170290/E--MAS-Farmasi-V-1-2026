from __future__ import annotations

import pytest

from emss.app import ApplicationContainer, build_application
from emss.config.settings import AppEnvironment, AppSettings


@pytest.fixture
def settings(tmp_path):
    return AppSettings(
        environment=AppEnvironment.TEST,
        data_dir=tmp_path / "emss-data",
        log_level="ERROR",
        login_max_attempts=3,
        login_lock_minutes=5,
    )


@pytest.fixture
def app_container(settings) -> ApplicationContainer:
    container = build_application(settings)
    try:
        yield container
    finally:
        container.close()


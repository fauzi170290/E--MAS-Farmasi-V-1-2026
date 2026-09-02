from __future__ import annotations

import pytest

from emss.alerts import route_alert


@pytest.mark.parametrize(
    ("risk", "completeness", "level", "notify", "hold"),
    [
        ("SAFE", "COMPLETE", "NONE", False, False),
        ("INFO", "COMPLETE", "HISTORY", False, False),
        ("REVIEW", "COMPLETE", "TOAST", True, False),
        ("HIGH_RISK", "COMPLETE", "PERSISTENT", True, False),
        ("CRITICAL", "COMPLETE", "CRITICAL", True, True),
        ("SAFE", "NOT_ASSESSED", "TOAST", True, False),
        ("SAFE", "UNMAPPED", "PERSISTENT", True, False),
        ("SAFE", "ERROR", "ERROR", True, False),
        ("CRITICAL", "UNMAPPED", "CRITICAL", True, True),
    ],
)
def test_alert_router_combines_risk_and_completeness(
    risk, completeness, level, notify, hold
) -> None:
    result = route_alert(risk, completeness)

    assert result.level == level
    assert result.notify is notify
    assert result.hold_recommended is hold


def test_alert_router_rejects_unknown_status() -> None:
    with pytest.raises(ValueError):
        route_alert("UNKNOWN", "COMPLETE")
    with pytest.raises(ValueError):
        route_alert("SAFE", "UNKNOWN")

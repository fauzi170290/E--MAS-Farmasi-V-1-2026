from __future__ import annotations

from datetime import UTC, datetime
from threading import Thread

from emss.audit.service import AuditEvent


def test_audit_timestamp_is_monotonic_when_clock_values_are_equal(
    monkeypatch, app_container
) -> None:
    fixed = datetime(2026, 8, 3, 1, 2, 3, 456789, tzinfo=UTC)
    monkeypatch.setattr("emss.audit.service.utc_now", lambda: fixed)
    with app_container.database.session() as session:
        first = app_container.audit.append(
            session,
            AuditEvent("TEST", "FIRST", "SUCCESS"),
        )
        second = app_container.audit.append(
            session,
            AuditEvent("TEST", "SECOND", "SUCCESS"),
        )
        session.commit()

        assert second.occurred_at > first.occurred_at
        assert app_container.audit.verify_chain(session)


def test_concurrent_local_sessions_keep_one_audit_chain(app_container) -> None:
    errors = []

    def record(action: str) -> None:
        try:
            with app_container.database.session() as session:
                app_container.audit.append(session, AuditEvent("TEST", action, "SUCCESS"))
                session.commit()
        except Exception as exc:  # pragma: no cover - asserted below
            errors.append(exc)

    first, second = Thread(target=record, args=("FIRST",)), Thread(target=record, args=("SECOND",))
    first.start(); second.start()
    first.join(); second.join()
    assert not errors
    with app_container.database.session() as session:
        assert app_container.audit.verify_chain(session)

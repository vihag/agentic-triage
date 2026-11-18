"""audit_events rejects UPDATE and DELETE from the application role."""

from __future__ import annotations

import pytest
from psycopg.errors import InsufficientPrivilege
from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import ProgrammingError
from triage_db.repositories import save_audit_event


def _sample() -> dict:
    return {
        "event_id": "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
        "seq": 1,
        "occurred_at": "2026-11-18T03:10:00Z",
        "type": "auth.denied",
        "actor": {"type": "system", "id": "triage-db"},
        "case_id": None,
        "alert_id": None,
        "data": {"reason": "append-only probe"},
        "prev_hash": None,
        "hash": "a" * 64,
    }


def test_app_role_can_insert_and_select_but_not_mutate(conn: Connection, app_engine: Engine) -> None:
    save_audit_event(conn, _sample())
    conn.commit()

    with app_engine.connect() as app:
        with app.begin():
            row = app.execute(
                text("SELECT type FROM audit_events WHERE event_id = CAST(:event_id AS uuid)"),
                {"event_id": _sample()["event_id"]},
            ).one()
            assert row.type == "auth.denied"
        with app.begin():
            app.execute(
                text(
                    """
                    INSERT INTO audit_events (
                        event_id, occurred_at, type, actor, data, prev_hash, hash, document
                    ) VALUES (
                        CAST(:event_id AS uuid), now(), 'auth.denied',
                        CAST(:actor AS jsonb), CAST(:data AS jsonb), NULL, :hash, CAST(:document AS jsonb)
                    )
                    """
                ),
                {
                    "event_id": "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
                    "actor": '{"type":"system","id":"triage-db"}',
                    "data": '{"reason":"inserted by app"}',
                    "hash": "b" * 64,
                    "document": '{"event_id":"eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee","seq":2}',
                },
            )
        with pytest.raises(ProgrammingError) as updated:
            with app.begin():
                app.execute(text("UPDATE audit_events SET type = 'case.created'"))
        assert isinstance(updated.value.orig, InsufficientPrivilege)
        with pytest.raises(ProgrammingError) as deleted:
            with app.begin():
                app.execute(text("DELETE FROM audit_events"))
        assert isinstance(deleted.value.orig, InsufficientPrivilege)

    remaining = conn.execute(text("SELECT count(*) FROM audit_events")).scalar_one()
    assert remaining == 2
    conn.rollback()

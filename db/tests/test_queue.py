"""SKIP LOCKED claims, leases, bot scope, and the outbox."""

from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

from tests.factory import seed_queued_case
from tests.schema_check import _registry
from triage_db.jsonutil import parse_ts
from triage_db.queue import (
    CLAIM_SQL,
    OUTBOX_CLAIM_SQL,
    bot_claim,
    claim_next,
    claim_outbox,
    complete_outbox,
    reap_expired_leases,
    release_case,
)

ANALYST = {"type": "analyst", "id": "analyst-priya"}
PRIYA_BOT = {"type": "grok_bot", "id": "grokbot-priya", "on_behalf_of": "analyst-priya"}
OMAR_BOT = {"type": "grok_bot", "id": "grokbot-omar", "on_behalf_of": "analyst-omar"}


def _assert_case(document: dict) -> None:
    registry, schemas = _registry()
    validator = Draft202012Validator(schemas["case.schema.json"], registry=registry, format_checker=FormatChecker())
    errors = list(validator.iter_errors(document))
    assert not errors, errors[0].message


def test_claim_sql_locks_in_priority_order() -> None:
    compact = " ".join(CLAIM_SQL.split())
    assert "FOR UPDATE SKIP LOCKED" in compact
    assert "ORDER BY priority DESC, created_at ASC" in compact
    assert "status = 'queued'" in compact
    outbox = " ".join(OUTBOX_CLAIM_SQL.split())
    assert "FOR UPDATE SKIP LOCKED" in outbox
    assert "ORDER BY id ASC" in outbox


def test_claim_order_and_queue_filter(conn: Connection) -> None:
    third = seed_queued_case(conn, priority=50, created_at="2026-11-18T02:00:00Z", title="later-high")
    first = seed_queued_case(conn, priority=50, created_at="2026-11-18T01:30:00Z", title="earlier-high")
    second_wait = seed_queued_case(conn, priority=10, created_at="2026-11-18T01:00:00Z", title="low")
    seed_queued_case(conn, queue="soc-low", priority=100, created_at="2026-11-18T01:00:00Z", title="other-queue")

    claimed = claim_next(conn, queue="soc-high", claimed_by=ANALYST, max_items=1)
    assert [item["case_id"] for item in claimed] == [first["case_id"]]
    _assert_case(claimed[0])
    assert claimed[0]["status"] == "claimed"
    assert claimed[0]["version"] == 2
    assert claimed[0]["claimed_by"] == ANALYST
    lease = parse_ts(claimed[0]["lease_expires_at"])
    assert lease is not None and lease > datetime.now(timezone.utc)

    rest = claim_next(conn, queue="soc-high", claimed_by=ANALYST, max_items=5)
    assert [item["case_id"] for item in rest] == [third["case_id"], second_wait["case_id"]]
    assert claim_next(conn, queue="soc-high", claimed_by=ANALYST) == []

    conn.execute(text("SET LOCAL enable_seqscan = off"))
    indexed = "\n".join(
        conn.execute(
            text(
                """
                EXPLAIN SELECT case_id FROM cases
                WHERE queue = 'soc-low' AND status = 'queued'
                ORDER BY priority DESC, created_at ASC
                FOR UPDATE SKIP LOCKED
                LIMIT 1
                """
            )
        ).scalars()
    )
    assert "cases_queue_claim_idx" in indexed


def test_bot_claim_sees_only_its_analyst(conn: Connection) -> None:
    own = seed_queued_case(conn, assignee="analyst-priya", priority=10, title="priya")
    seed_queued_case(conn, assignee="analyst-omar", priority=100, title="omar")
    seed_queued_case(conn, assignee=None, priority=90, title="unassigned")

    claimed = bot_claim(conn, queue="soc-high", claimed_by=PRIYA_BOT, max_items=10)
    assert [item["case_id"] for item in claimed] == [own["case_id"]]
    assert claimed[0]["claimed_by"] == PRIYA_BOT

    omar = bot_claim(conn, queue="soc-high", claimed_by=OMAR_BOT, max_items=10)
    assert len(omar) == 1
    assert omar[0]["assignee"] == "analyst-omar"
    assert bot_claim(conn, queue="soc-high", claimed_by=PRIYA_BOT) == []


def test_bot_claim_rejects_a_principal_without_an_analyst() -> None:
    with pytest.raises(ValueError):
        bot_claim(None, queue="soc-high", claimed_by={"type": "grok_bot", "id": "grokbot-priya"})  # type: ignore[arg-type]


def test_release_returns_the_case_to_the_queue(conn: Connection) -> None:
    seeded = seed_queued_case(conn, priority=40)
    claimed = claim_next(conn, queue="soc-high", claimed_by=ANALYST)[0]
    released = release_case(conn, case_id=claimed["case_id"], released_by=ANALYST)
    _assert_case(released)
    assert released["status"] == "queued"
    assert released["claimed_by"] is None
    assert released["lease_expires_at"] is None
    assert released["version"] == 3
    again = claim_next(conn, queue="soc-high", claimed_by=ANALYST)
    assert again[0]["case_id"] == seeded["case_id"]


def test_expired_lease_returns_to_queued_and_emits_event(conn: Connection) -> None:
    seeded = seed_queued_case(conn)
    claim_next(conn, queue="soc-high", claimed_by=ANALYST)
    conn.execute(
        text(
            """
            UPDATE cases
            SET lease_expires_at = now() - interval '1 second'
            WHERE case_id = CAST(:case_id AS uuid)
            """
        ),
        {"case_id": seeded["case_id"]},
    )
    released = reap_expired_leases(conn)
    assert [item["case_id"] for item in released] == [seeded["case_id"]]
    assert released[0]["status"] == "queued"
    assert released[0]["claimed_by"] is None
    event = conn.execute(
        text(
            """
            SELECT type, actor->>'id' AS actor_id, case_id::text AS case_id
            FROM audit_events
            WHERE type = 'case.lease_expired'
            """
        )
    ).one()
    assert event.actor_id == "lease-reaper"
    assert event.case_id == seeded["case_id"]
    assert reap_expired_leases(conn) == []


def test_reap_rolls_back_with_the_case(engine: Engine, conn: Connection) -> None:
    seeded = seed_queued_case(conn)
    claim_next(conn, queue="soc-high", claimed_by=ANALYST)
    conn.execute(
        text(
            """
            UPDATE cases SET lease_expires_at = now() - interval '1 second'
            WHERE case_id = CAST(:case_id AS uuid)
            """
        ),
        {"case_id": seeded["case_id"]},
    )
    conn.commit()

    with engine.connect() as other:
        transaction = other.begin()
        released = reap_expired_leases(other)
        assert len(released) == 1
        transaction.rollback()

    status = conn.execute(
        text("SELECT status FROM cases WHERE case_id = CAST(:case_id AS uuid)"),
        {"case_id": seeded["case_id"]},
    ).scalar_one()
    events = conn.execute(text("SELECT count(*) FROM audit_events WHERE type = 'case.lease_expired'")).scalar_one()
    assert status == "claimed"
    assert events == 0


def test_fifty_claimers_do_not_double_claim(engine: Engine, conn: Connection) -> None:
    expected = {
        seed_queued_case(conn, priority=index % 20, created_at=f"2026-11-18T01:{index % 60:02d}:00Z")["case_id"]
        for index in range(50)
    }
    conn.commit()
    barrier = threading.Barrier(50)
    found: list[str] = []
    errors: list[BaseException] = []
    lock = threading.Lock()

    def claim_one() -> None:
        try:
            barrier.wait(timeout=30)
            with engine.connect() as connection:
                with connection.begin():
                    claimed = claim_next(
                        connection, queue="soc-high", claimed_by=ANALYST, max_items=1, lease_seconds=60
                    )
            ids = [item["case_id"] for item in claimed]
        except BaseException as exc:  # noqa: BLE001 - the assertion below reports the thread failure
            with lock:
                errors.append(exc)
            return
        with lock:
            found.extend(ids)

    threads = [threading.Thread(target=claim_one) for _ in range(50)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    assert errors == []
    assert len(found) == 50
    assert set(found) == expected
    assert len(set(found)) == 50


def test_outbox_claim_lease_and_concurrency(engine: Engine, conn: Connection) -> None:
    seed_queued_case(conn, title="outbox-a")
    seed_queued_case(conn, title="outbox-b")
    claimed = claim_outbox(conn, max_items=1, lease_seconds=30)
    assert len(claimed) == 1
    assert claimed[0].status == "processing"
    assert claimed[0].attempts == 1
    assert claimed[0].lease_expires_at > datetime.now(timezone.utc) - timedelta(seconds=1)
    second = claim_outbox(conn, max_items=10)
    assert len(second) == 1
    assert second[0].alert_id != claimed[0].alert_id
    assert claim_outbox(conn) == []

    conn.execute(
        text("UPDATE triage_outbox SET lease_expires_at = now() - interval '1 second' WHERE id = :id"),
        {"id": claimed[0].id},
    )
    reclaimed = claim_outbox(conn, max_items=1)
    assert reclaimed[0].id == claimed[0].id
    assert reclaimed[0].attempts == 2
    complete_outbox(conn, reclaimed[0].id)
    assert claim_outbox(conn) == []

    extra = [seed_queued_case(conn, title=f"burst-{index}")["alert_ids"][0] for index in range(20)]
    conn.commit()
    # complete_outbox consumed the reclaimed row; the other original row is still processing.
    pending_before = conn.execute(
        text("SELECT count(*) FROM triage_outbox WHERE status = 'pending'")
    ).scalar_one()
    assert pending_before == 20

    barrier = threading.Barrier(50)
    found: list[str] = []
    errors: list[BaseException] = []
    lock = threading.Lock()

    def claim_one() -> None:
        try:
            barrier.wait(timeout=30)
            with engine.connect() as connection:
                with connection.begin():
                    rows = claim_outbox(connection, max_items=1)
            ids = [row.alert_id for row in rows]
        except BaseException as exc:  # noqa: BLE001
            with lock:
                errors.append(exc)
            return
        with lock:
            found.extend(ids)

    threads = [threading.Thread(target=claim_one) for _ in range(50)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    assert errors == []
    assert len(found) == 20
    assert set(found) == set(extra)

"""The migration creates every ER table, pgvector, and the key indexes."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.engine import Connection

from triage_db.repositories import save_bot_credential, save_bot_run, save_incident, save_rule

ER_TABLES = {
    "siem_instances",
    "alerts",
    "triage_outbox",
    "triage_decisions",
    "cases",
    "evidence_packs",
    "evidence_items",
    "next_steps_packs",
    "actions",
    "analysts",
    "bot_credentials",
    "bot_runs",
    "audit_events",
    "incident_corpus",
    "rules",
}


def test_er_tables_exist(conn: Connection) -> None:
    rows = conn.execute(
        text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
    ).scalars()
    assert ER_TABLES <= set(rows)


def test_pgvector_extension_and_hnsw_index(conn: Connection) -> None:
    version = conn.execute(
        text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
    ).scalar_one()
    assert version
    indexdef = conn.execute(
        text("SELECT indexdef FROM pg_indexes WHERE indexname = 'incident_corpus_embedding_hnsw'")
    ).scalar_one()
    assert "hnsw" in indexdef
    assert "vector_cosine_ops" in indexdef
    embedding = [0.0] * 1536
    embedding[0] = 1.0
    save_incident(
        conn,
        ref_id="INC-2041",
        ref_type="past_incident",
        summary="Credential stuffing against VPN",
        verified_severity="high",
        verdict="true_positive",
        embedding=embedding,
    )
    distance = conn.execute(
        text(
            """
            SELECT embedding <=> CAST(:embedding AS vector)
            FROM incident_corpus WHERE ref_id = 'INC-2041'
            """
        ),
        {"embedding": "[" + ",".join(repr(value) for value in embedding) + "]"},
    ).scalar_one()
    assert distance == 0


def test_queue_and_partial_indexes(conn: Connection) -> None:
    indexes = {
        row.indexname: row.indexdef
        for row in conn.execute(
            text(
                """
                SELECT indexname, indexdef FROM pg_indexes
                WHERE schemaname = 'public'
                """
            )
        )
    }
    claim = indexes["cases_queue_claim_idx"]
    assert "priority DESC" in claim
    assert "created_at" in claim
    assert "queued" in claim
    assert "assignee" in indexes["cases_assignee_status_idx"]
    assert "UNIQUE" in indexes["alerts_sid_uk"].upper() or "unique" in indexes["alerts_sid_uk"]
    assert "dedup_key" in indexes["alerts_dedup_open_idx"]
    assert "case_open" in indexes["alerts_dedup_open_idx"]
    assert "triage_outbox_status_id_idx" in indexes
    approved = indexes["actions_approved_idx"]
    assert "approved" in approved


def test_reference_rows(conn: Connection) -> None:
    save_rule(conn, rule_id="AUTH-003", version="1.2.0", enabled=True, priority=10, config={"window": "10m"})
    save_bot_credential(conn, bot_id="grokbot-priya", on_behalf_of="analyst-priya", key_hash="hash")
    save_bot_run(
        conn,
        run_id="12121212-1212-4121-8121-121212121212",
        bot_id="grokbot-priya",
        routine_id="triage-routine",
        status="running",
        started_at=datetime(2026, 11, 18, 2, 40, tzinfo=timezone.utc),
    )
    assert conn.execute(text("SELECT count(*) FROM rules")).scalar_one() == 1
    assert conn.execute(text("SELECT on_shift FROM analysts WHERE analyst_id = 'analyst-priya'")).scalar_one() is False
    assert conn.execute(text("SELECT status FROM bot_runs")).scalar_one() == "running"


def test_audit_privileges_revoked_from_app_role(conn: Connection) -> None:
    assert conn.execute(text("SELECT has_table_privilege('triage_app', 'audit_events', 'INSERT')")).scalar_one()
    assert conn.execute(text("SELECT has_table_privilege('triage_app', 'audit_events', 'SELECT')")).scalar_one()
    assert not conn.execute(text("SELECT has_table_privilege('triage_app', 'audit_events', 'UPDATE')")).scalar_one()
    assert not conn.execute(text("SELECT has_table_privilege('triage_app', 'audit_events', 'DELETE')")).scalar_one()
    assert conn.execute(text("SELECT has_table_privilege('triage_app', 'cases', 'UPDATE')")).scalar_one()
    assert conn.execute(text("SELECT has_table_privilege('triage_app', 'cases', 'DELETE')")).scalar_one()

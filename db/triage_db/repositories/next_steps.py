"""Next steps pack persistence."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection

from triage_db.audit import SYSTEM_ACTOR, record_event
from triage_db.jsonutil import dump_json, load_json


def save_next_steps_pack(
    conn: Connection, document: dict[str, Any], *, actor: Mapping[str, Any] | None = None
) -> None:
    conn.execute(
        text(
            """
            INSERT INTO next_steps_packs (
                next_steps_pack_id, case_id, version, playbook_id, steps, draft_responses, document
            ) VALUES (
                CAST(:next_steps_pack_id AS uuid), CAST(:case_id AS uuid), :version, :playbook_id,
                CAST(:steps AS jsonb), CAST(:draft_responses AS jsonb), CAST(:document AS jsonb)
            )
            """
        ),
        {
            "next_steps_pack_id": document["next_steps_pack_id"],
            "case_id": document["case_id"],
            "version": document["version"],
            "playbook_id": document.get("playbook_id"),
            "steps": dump_json(document["steps"]),
            "draft_responses": dump_json(document.get("draft_responses") or []),
            "document": dump_json(document),
        },
    )
    record_event(
        conn,
        event_type="next_steps.updated",
        actor=dict(actor) if actor is not None else dict(SYSTEM_ACTOR),
        case_id=document["case_id"],
        data={"next_steps_pack_id": document["next_steps_pack_id"], "version": document["version"]},
    )


def replace_next_steps_pack(
    conn: Connection, document: dict[str, Any], *, actor: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    conn.execute(
        text(
            """
            UPDATE next_steps_packs SET
                version = :version,
                playbook_id = :playbook_id,
                steps = CAST(:steps AS jsonb),
                draft_responses = CAST(:draft_responses AS jsonb),
                document = CAST(:document AS jsonb)
            WHERE next_steps_pack_id = CAST(:next_steps_pack_id AS uuid)
            """
        ),
        {
            "next_steps_pack_id": document["next_steps_pack_id"],
            "version": document["version"],
            "playbook_id": document.get("playbook_id"),
            "steps": dump_json(document["steps"]),
            "draft_responses": dump_json(document.get("draft_responses") or []),
            "document": dump_json(document),
        },
    )
    record_event(
        conn,
        event_type="next_steps.updated",
        actor=dict(actor) if actor is not None else dict(SYSTEM_ACTOR),
        case_id=document["case_id"],
        data={"next_steps_pack_id": document["next_steps_pack_id"], "version": document["version"]},
    )
    return document


def get_next_steps_pack(conn: Connection, next_steps_pack_id: str) -> dict[str, Any]:
    document = conn.execute(
        text(
            """
            SELECT document FROM next_steps_packs
            WHERE next_steps_pack_id = CAST(:next_steps_pack_id AS uuid)
            """
        ),
        {"next_steps_pack_id": next_steps_pack_id},
    ).scalar_one()
    return load_json(document)

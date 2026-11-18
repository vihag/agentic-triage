"""Evidence pack plus one row per item, in document order."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection

from triage_db.jsonutil import dump_json, load_json, parse_ts


def save_evidence_pack(conn: Connection, document: dict[str, Any]) -> None:
    conn.execute(
        text(
            """
            INSERT INTO evidence_packs (
                evidence_pack_id, case_id, version, summary, timeline, generated_by, document
            ) VALUES (
                CAST(:evidence_pack_id AS uuid), CAST(:case_id AS uuid), :version, :summary,
                CAST(:timeline AS jsonb), CAST(:generated_by AS jsonb), CAST(:document AS jsonb)
            )
            """
        ),
        {
            "evidence_pack_id": document["evidence_pack_id"],
            "case_id": document["case_id"],
            "version": document["version"],
            "summary": document["summary"],
            "timeline": dump_json(document.get("timeline") or []),
            "generated_by": dump_json(document["generated_by"]),
            "document": dump_json(document),
        },
    )
    for position, item in enumerate(document["items"]):
        data = item.get("data")
        conn.execute(
            text(
                """
                INSERT INTO evidence_items (
                    evidence_id, evidence_pack_id, position, kind, title, source,
                    added_by, data, collected_at
                ) VALUES (
                    :evidence_id, CAST(:evidence_pack_id AS uuid), :position, :kind, :title,
                    :source, CAST(:added_by AS jsonb), CAST(:data AS jsonb), :collected_at
                )
                """
            ),
            {
                "evidence_id": item["evidence_id"],
                "evidence_pack_id": document["evidence_pack_id"],
                "position": position,
                "kind": item["kind"],
                "title": item["title"],
                "source": item["source"],
                "added_by": dump_json(item["added_by"]),
                "data": None if data is None else dump_json(data),
                "collected_at": parse_ts(item["collected_at"]),
            },
        )


def get_evidence_pack(conn: Connection, evidence_pack_id: str) -> dict[str, Any]:
    document = conn.execute(
        text(
            """
            SELECT document FROM evidence_packs
            WHERE evidence_pack_id = CAST(:evidence_pack_id AS uuid)
            """
        ),
        {"evidence_pack_id": evidence_pack_id},
    ).scalar_one()
    return load_json(document)

"""Write the starter corpus into ``incident_corpus`` with 1536-d embeddings."""

from __future__ import annotations

from sqlalchemy import text

from triage_agent.fuzzy.corpus import CORPUS, CorpusItem
from triage_agent.fuzzy.embedder import HashingEmbedder
from triage_agent.fuzzy.index import vector_literal

_UPSERT = """
INSERT INTO incident_corpus (
    ref_id, ref_type, summary, verified_severity, verdict, embedding
) VALUES (
    :ref_id, :ref_type, :summary, :verified_severity, :verdict, CAST(:embedding AS vector)
)
ON CONFLICT (ref_id) DO UPDATE SET
    ref_type = EXCLUDED.ref_type,
    summary = EXCLUDED.summary,
    verified_severity = EXCLUDED.verified_severity,
    verdict = EXCLUDED.verdict,
    embedding = EXCLUDED.embedding
"""


def iter_embeddings(
    embedder: HashingEmbedder | None = None,
) -> list[tuple[CorpusItem, list[float]]]:
    hasher = embedder or HashingEmbedder()
    return [(item, hasher.embed(item.summary)) for item in CORPUS]


def seed_corpus(conn: object, embedder: HashingEmbedder | None = None) -> int:
    """Embed every corpus row and upsert it. Returns the number of rows written."""
    rows = iter_embeddings(embedder)
    execute = conn.execute  # type: ignore[attr-defined]
    for item, embedding in rows:
        if len(embedding) != 1536:
            raise ValueError("incident embeddings are vector(1536)")
        execute(
            text(_UPSERT),
            {
                "ref_id": item.ref_id,
                "ref_type": item.ref_type,
                "summary": item.summary,
                "verified_severity": item.verified_severity,
                "verdict": item.verdict,
                "embedding": vector_literal(embedding),
            },
        )
    return len(rows)

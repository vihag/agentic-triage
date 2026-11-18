"""Nearest-neighbour lookup over the incident corpus."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from triage_agent.contract import SimilarItem
from triage_agent.fuzzy.corpus import CorpusItem
from triage_agent.fuzzy.errors import FuzzyTimeout

_QUERY = """
SELECT ref_id, ref_type, summary, verified_severity, verdict,
       (embedding <=> CAST(:embedding AS vector)) AS distance
FROM incident_corpus
ORDER BY embedding <=> CAST(:embedding AS vector)
LIMIT :k
"""


def vector_literal(values: Sequence[float]) -> str:
    return "[" + ",".join(repr(float(value)) for value in values) + "]"


def _clamp(similarity: float) -> float:
    if similarity < 0.0:
        return 0.0
    if similarity > 1.0:
        return 1.0
    return similarity


def to_similar(
    *,
    ref_id: str,
    ref_type: str,
    summary: str,
    similarity: float,
    verified_severity: str | None,
    verdict: str | None,
) -> SimilarItem:
    return SimilarItem(
        ref_type,  # type: ignore[arg-type]
        ref_id,
        _clamp(similarity),
        summary,
        verified_severity,  # type: ignore[arg-type]
        verdict or "unknown",
    )


class NeighbourIndex(Protocol):
    def nearest(
        self, vector: Sequence[float], k: int, *, timeout_s: float
    ) -> list[SimilarItem]: ...


class InMemoryIndex:
    """Cosine search over embeddings held in process. Used when Postgres is absent."""

    def __init__(self, rows: Sequence[tuple[CorpusItem, Sequence[float]]]) -> None:
        self.rows = list(rows)

    def nearest(self, vector: Sequence[float], k: int, *, timeout_s: float) -> list[SimilarItem]:
        if timeout_s <= 0:
            raise FuzzyTimeout("neighbour search timed out")
        scored: list[tuple[float, CorpusItem]] = []
        for item, embedding in self.rows:
            similarity = sum(
                left * right for left, right in zip(vector, embedding, strict=True)
            )
            scored.append((similarity, item))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [
            to_similar(
                ref_id=item.ref_id,
                ref_type=item.ref_type,
                summary=item.summary,
                similarity=similarity,
                verified_severity=item.verified_severity,
                verdict=item.verdict,
            )
            for similarity, item in scored[:k]
        ]


class PgvectorIndex:
    """kNN on ``incident_corpus.embedding`` using cosine distance."""

    def __init__(self, conn: object) -> None:
        self.conn = conn

    def nearest(self, vector: Sequence[float], k: int, *, timeout_s: float) -> list[SimilarItem]:
        if timeout_s <= 0:
            raise FuzzyTimeout("neighbour search timed out")
        milliseconds = max(1, int(timeout_s * 1000))
        execute = self.conn.execute  # type: ignore[attr-defined]
        try:
            execute(text(f"SET LOCAL statement_timeout = {milliseconds}"))
            rows = execute(
                text(_QUERY),
                {"embedding": vector_literal(vector), "k": k},
            ).mappings()
            found = [
                to_similar(
                    ref_id=row["ref_id"],
                    ref_type=row["ref_type"],
                    summary=row["summary"],
                    similarity=1.0 - float(row["distance"]),
                    verified_severity=row["verified_severity"],
                    verdict=row["verdict"],
                )
                for row in rows
            ]
        except DBAPIError as exc:
            if _cancelled(exc):
                raise FuzzyTimeout("neighbour search timed out") from exc
            raise
        finally:
            execute(text("SET LOCAL statement_timeout = 0"))
        return found


def _cancelled(exc: BaseException) -> bool:
    message = str(exc).lower()
    return (
        "statement timeout" in message
        or "querycanceled" in message
        or "canceling statement" in message
    )

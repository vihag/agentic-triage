"""pgvector kNN plus an LLM judge. Honour ``timeout_s`` or raise ``FuzzyTimeout``."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from triage_agent.contract import FuzzyMatchResult, LLMClient, SimilarItem
from triage_agent.fuzzy.embedder import HashingEmbedder
from triage_agent.fuzzy.errors import FuzzyTimeout
from triage_agent.fuzzy.index import NeighbourIndex
from triage_agent.fuzzy.judge import alert_text, judge

Clock = Callable[[], float]


def _monotonic() -> float:
    return time.monotonic()


def _result(payload: Mapping[str, Any]) -> FuzzyMatchResult:
    items = tuple(
        SimilarItem(
            item["ref_type"],
            item["ref_id"],
            item["similarity"],
            item["summary"],
            item.get("verified_severity"),
            item.get("verdict", "unknown"),
        )
        for item in payload["similar_items"]
    )
    labels = payload.get("suggested_labels") or ()
    return FuzzyMatchResult(
        payload["matcher_id"],
        payload["model"],
        items,
        payload["suggested_severity"],
        float(payload["confidence"]),
        payload["rationale"],
        tuple(labels),
    )


class PgvectorFuzzyMatcher:
    """Embeddings kNN over the seeded corpus, then a structured LLM judge.

    CI must not construct this with a live model client. Pass ``MockLLMClient``
    or, for tests that do not need retrieval, use ``MockFuzzyMatcher``.
    """

    matcher_id = "pgvector-knn+llm-judge"

    def __init__(
        self,
        index: NeighbourIndex,
        llm: LLMClient,
        embedder: HashingEmbedder | None = None,
        clock: Clock | None = None,
    ) -> None:
        self.index = index
        self.llm = llm
        self.embedder = embedder or HashingEmbedder()
        self._clock = clock or _monotonic

    def match(
        self, alert: Mapping[str, Any], k: int = 5, timeout_s: float = 5.0
    ) -> FuzzyMatchResult:
        if k < 1:
            raise ValueError("k must be at least 1")
        deadline = self._clock() + timeout_s

        def remaining() -> float:
            left = deadline - self._clock()
            if left <= 0:
                raise FuzzyTimeout("fuzzy matcher timed out")
            return left

        remaining()
        vector = self.embedder.embed(alert_text(alert))
        neighbours: Sequence[SimilarItem] = self.index.nearest(vector, k, timeout_s=remaining())
        model = f"embed:feature-hash-1536 / llm:{self.llm.model}"
        payload = judge(
            self.llm,
            alert,
            neighbours,
            matcher_id=self.matcher_id,
            model=model,
            timeout_s=remaining(),
        )
        return _result(payload)

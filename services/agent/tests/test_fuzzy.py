"""Fuzzy matcher without a live model or a network call."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from contracts.agent.interfaces import MockFuzzyMatcher, MockLLMClient

from triage_agent.contract import FuzzyMatchResult, combine_severity
from triage_agent.fuzzy.corpus import CORPUS
from triage_agent.fuzzy.embedder import EMBEDDING_DIM, HashingEmbedder
from triage_agent.fuzzy.errors import FuzzyTimeout
from triage_agent.fuzzy.fallback import GUARDRAIL, match_or_rules_only
from triage_agent.fuzzy.index import InMemoryIndex
from triage_agent.fuzzy.judge import alert_text
from triage_agent.fuzzy.matcher import PgvectorFuzzyMatcher
from triage_agent.fuzzy.schema import validate_fuzzy_match
from triage_agent.fuzzy.seed import iter_embeddings

FUZZY_SRC = Path(__file__).resolve().parents[1] / "src" / "triage_agent" / "fuzzy"
STUFFING = {
    "title": "Excessive failed logins followed by success credential stuffing VPN",
    "source": {"search_name": "Excessive Failed Logins Followed By Success"},
    "entities": {"users": ["jdoe"], "src_ips": ["203.0.113.45"]},
}
HIGH_JUDGMENT = {
    "suggested_severity": "high",
    "confidence": 0.82,
    "rationale": "Closest neighbour is a confirmed credential-stuffing incident.",
    "suggested_labels": ["candidate:account-takeover"],
}


class ScriptClock:
    def __init__(self, values: list[float]) -> None:
        self.values = values
        self.calls = 0

    def __call__(self) -> float:
        value = self.values[min(self.calls, len(self.values) - 1)]
        self.calls += 1
        return value


class SpyLLM:
    model = "mock-llm"

    def __init__(self, payload: dict | None = None, *, boom: BaseException | None = None) -> None:
        self.payload = payload if payload is not None else dict(HIGH_JUDGMENT)
        self.boom = boom
        self.calls = 0
        self.timeouts: list[float] = []
        self.schemas: list[dict] = []

    def complete_json(
        self, system: str, user: str, schema: dict, timeout_s: float = 10.0
    ) -> dict:
        self.calls += 1
        self.timeouts.append(timeout_s)
        self.schemas.append(schema)
        if self.boom is not None:
            raise self.boom
        return self.payload


def _matcher(llm: SpyLLM | MockLLMClient, clock: ScriptClock | None = None) -> PgvectorFuzzyMatcher:
    embedder = HashingEmbedder()
    index = InMemoryIndex(iter_embeddings(embedder))
    return PgvectorFuzzyMatcher(index, llm, embedder, clock=clock)


def test_corpus_covers_thirty_items_and_every_kind() -> None:
    assert len(CORPUS) >= 30
    assert {item.ref_type for item in CORPUS} == {
        "past_incident",
        "known_pattern",
        "benign_baseline",
    }
    assert len({item.ref_id for item in CORPUS}) == len(CORPUS)
    ids = {item.ref_id for item in CORPUS}
    assert {"INC-2041", "BASE-03", "BASE-12"} <= ids


def test_embedder_is_deterministic_and_unit_length() -> None:
    embedder = HashingEmbedder()
    first = embedder.embed("credential stuffing vpn")
    second = embedder.embed("credential stuffing vpn")
    assert first == second
    assert len(first) == EMBEDDING_DIM
    norm = sum(value * value for value in first) ** 0.5
    assert norm == pytest.approx(1.0)
    assert embedder.embed("")[0] == 1.0


def test_credential_stuffing_alert_ranks_the_example_incident() -> None:
    embedder = HashingEmbedder()
    index = InMemoryIndex(iter_embeddings(embedder))
    hits = index.nearest(embedder.embed(alert_text(STUFFING)), 3, timeout_s=1)
    assert hits[0].ref_id == "INC-2041"
    assert hits[0].ref_type == "past_incident"
    assert 0.0 <= hits[0].similarity <= 1.0


def test_judge_result_validates_against_fuzzy_match_schema() -> None:
    llm = SpyLLM()
    result = _matcher(llm).match(STUFFING, k=5, timeout_s=5)
    assert result.matcher_id == "pgvector-knn+llm-judge"
    assert result.model == "embed:feature-hash-1536 / llm:mock-llm"
    assert result.suggested_severity == "high"
    assert result.confidence == 0.82
    assert result.similar_items[0].ref_id == "INC-2041"
    assert list(result.suggested_labels) == ["candidate:account-takeover"]
    assert llm.schemas[0]["title"] == "FuzzyMatchResult"
    assert "suggested_severity" in llm.schemas[0]["required"]


def test_invalid_judge_json_is_rejected() -> None:
    llm = SpyLLM(
        {"suggested_severity": "urgent", "confidence": 0.4, "rationale": "not a severity"}
    )
    with pytest.raises(ValueError, match="FuzzyMatchResult"):
        _matcher(llm).match(STUFFING, timeout_s=5)
    with pytest.raises(ValueError, match="FuzzyMatchResult"):
        validate_fuzzy_match({"matcher_id": "x"})


def test_zero_timeout_skips_the_model_and_records_the_guardrail() -> None:
    llm = SpyLLM()
    matcher = _matcher(llm, clock=ScriptClock([0.0, 0.0]))
    outcome = match_or_rules_only(matcher, STUFFING, timeout_s=0)
    assert llm.calls == 0
    assert outcome.result is None
    assert outcome.guardrails == ("fuzzy_timeout_fallback",)
    assert GUARDRAIL == "fuzzy_timeout_fallback"
    assert combine_severity("medium", [], outcome.result) == "medium"


def test_provider_timeout_falls_back_to_rules_only() -> None:
    llm = SpyLLM(boom=TimeoutError("provider"))
    outcome = match_or_rules_only(_matcher(llm), STUFFING, timeout_s=5)
    assert llm.calls == 1
    assert outcome.result is None
    assert outcome.guardrails == ("fuzzy_timeout_fallback",)
    assert combine_severity("high", [], None) == "high"


def test_deadline_expires_before_the_judge() -> None:
    llm = SpyLLM()
    clock = ScriptClock([0.0, 0.0, 1.0, 10.0])
    with pytest.raises(FuzzyTimeout):
        _matcher(llm, clock=clock).match(STUFFING, timeout_s=5)
    assert llm.calls == 0


def test_in_memory_index_honours_its_own_timeout() -> None:
    index = InMemoryIndex(iter_embeddings())
    with pytest.raises(FuzzyTimeout):
        index.nearest([0.0] * EMBEDDING_DIM, 3, timeout_s=0)


def test_k_must_be_positive() -> None:
    with pytest.raises(ValueError, match="k"):
        _matcher(SpyLLM()).match(STUFFING, k=0)


def test_ci_uses_mock_fuzzy_matcher_and_never_a_live_model() -> None:
    fixture = FuzzyMatchResult(
        "mock-fuzzy",
        "mock",
        (),
        "high",
        0.82,
        "Recorded fixture. No model call.",
    )
    matcher = MockFuzzyMatcher({"Excessive Failed Logins Followed By Success": fixture})
    alert = {"source": {"search_name": "Excessive Failed Logins Followed By Success"}}
    assert matcher.match(alert) is fixture
    canned = MockLLMClient({"credential stuffing": HIGH_JUDGMENT})
    judged = canned.complete_json("system", "credential stuffing alert", {}, timeout_s=1)
    assert judged["suggested_severity"] == "high"
    forbidden = {"openai", "requests", "httpx", "urllib", "socket"}
    for path in FUZZY_SRC.glob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = {alias.name.split(".", 1)[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom):
                names = {(node.module or "").split(".", 1)[0]}
            else:
                continue
            assert names.isdisjoint(forbidden)

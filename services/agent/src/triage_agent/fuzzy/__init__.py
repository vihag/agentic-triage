"""Fuzzy matcher: local embeddings, pgvector kNN, mockable LLM judge."""

from triage_agent.fuzzy.corpus import CORPUS
from triage_agent.fuzzy.embedder import HashingEmbedder
from triage_agent.fuzzy.errors import FuzzyTimeout
from triage_agent.fuzzy.fallback import GUARDRAIL, FuzzyOutcome, match_or_rules_only
from triage_agent.fuzzy.index import InMemoryIndex, PgvectorIndex
from triage_agent.fuzzy.matcher import PgvectorFuzzyMatcher
from triage_agent.fuzzy.seed import seed_corpus

__all__ = [
    "CORPUS",
    "GUARDRAIL",
    "FuzzyOutcome",
    "FuzzyTimeout",
    "HashingEmbedder",
    "InMemoryIndex",
    "PgvectorFuzzyMatcher",
    "PgvectorIndex",
    "match_or_rules_only",
    "seed_corpus",
]

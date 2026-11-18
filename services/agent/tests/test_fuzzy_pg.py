"""Seed the corpus into pgvector and read it back with cosine kNN."""

from __future__ import annotations

import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from contracts.agent.interfaces import MockLLMClient
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from triage_agent.fuzzy.corpus import CORPUS
from triage_agent.fuzzy.embedder import HashingEmbedder
from triage_agent.fuzzy.index import PgvectorIndex
from triage_agent.fuzzy.matcher import PgvectorFuzzyMatcher
from triage_agent.fuzzy.seed import seed_corpus

REPO = Path(__file__).resolve().parents[3]
DB_DIR = REPO / "db"
ADMIN_URL = os.environ.get("TEST_ADMIN_URL", "postgresql+psycopg://ubuntu@/postgres")
TEST_DB = os.environ.get("TEST_FUZZY_DATABASE_NAME", "triage_fuzzy_test")
JUDGMENT = {
    "suggested_severity": "high",
    "confidence": 0.82,
    "rationale": "Closest neighbour is a confirmed credential-stuffing incident.",
    "suggested_labels": ["candidate:account-takeover"],
}


def _upgrade(url: str) -> None:
    os.environ["DATABASE_URL"] = url
    cfg = Config(str(DB_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(DB_DIR / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")


def test_seed_embeds_at_least_thirty_rows_and_knn_finds_inc_2041() -> None:
    admin = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    with admin.connect() as connection:
        connection.execute(text(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)"))
        connection.execute(text(f"CREATE DATABASE {TEST_DB}"))
    admin.dispose()
    url = f"postgresql+psycopg://ubuntu@/{TEST_DB}"
    _upgrade(url)
    engine = create_engine(url, poolclass=NullPool)
    embedder = HashingEmbedder()
    alert = {
        "title": "Excessive failed logins followed by success credential stuffing VPN",
        "source": {"search_name": "Excessive Failed Logins Followed By Success"},
    }
    llm = MockLLMClient({"credential stuffing": JUDGMENT})
    with engine.begin() as conn:
        assert seed_corpus(conn, embedder) >= 30
        assert seed_corpus(conn, embedder) == len(CORPUS)
        count, low, high = conn.execute(
            text(
                "SELECT count(*), min(vector_dims(embedding)), max(vector_dims(embedding)) "
                "FROM incident_corpus"
            )
        ).one()
        assert count == len(CORPUS)
        assert low == high == 1536
        matcher = PgvectorFuzzyMatcher(PgvectorIndex(conn), llm, embedder)
        result = matcher.match(alert, k=5, timeout_s=5)
    engine.dispose()
    assert result.similar_items[0].ref_id == "INC-2041"
    assert result.suggested_severity == "high"
    assert result.model.startswith("embed:feature-hash-1536 / llm:")
    assert llm.model == "mock-llm"

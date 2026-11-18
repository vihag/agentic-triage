"""Seed the corpus into pgvector and read it back with cosine kNN."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from contracts.agent.interfaces import MockLLMClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool

from triage_agent.fuzzy.corpus import CORPUS
from triage_agent.fuzzy.embedder import HashingEmbedder
from triage_agent.fuzzy.index import PgvectorIndex
from triage_agent.fuzzy.matcher import PgvectorFuzzyMatcher
from triage_agent.fuzzy.seed import seed_corpus

REPO = Path(__file__).resolve().parents[3]
DB_DIR = REPO / "db"
TEST_DB = os.environ.get("TEST_FUZZY_DATABASE_NAME", "triage_fuzzy_test")
_CANDIDATES = (
    os.environ.get("TEST_ADMIN_URL"),
    os.environ.get("TEST_DATABASE_URL"),
    "postgresql+psycopg://ubuntu@/postgres",
    "postgresql+psycopg://triage:local-dev-postgres-password@127.0.0.1:5432/triage",
)
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


def _admin_url() -> str:
    errors: list[str] = []
    for candidate in _CANDIDATES:
        if not candidate:
            continue
        engine = create_engine(candidate, isolation_level="AUTOCOMMIT", poolclass=NullPool)
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return candidate
        except Exception as exc:
            errors.append(f"{candidate}: {exc}")
        finally:
            engine.dispose()
    pytest.skip("Postgres is not reachable: " + "; ".join(errors))


def test_seed_embeds_at_least_thirty_rows_and_knn_finds_inc_2041() -> None:
    admin_url = _admin_url()
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    with admin.connect() as connection:
        connection.execute(text(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)"))
        connection.execute(text(f"CREATE DATABASE {TEST_DB}"))
    admin.dispose()
    url = make_url(admin_url).set(database=TEST_DB).render_as_string(hide_password=False)
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

"""Session Postgres for repository tests.

Uses TEST_DATABASE_URL when set. Otherwise creates a local database on the
Postgres 16 + pgvector instance (the T01 image, or the distro packages).
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.pool import NullPool

from triage_db.roles import APP_PASSWORD, APP_ROLE

DB_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ADMIN_URL = os.environ.get("TEST_ADMIN_URL", "postgresql+psycopg://ubuntu@/postgres")
TEST_DB = os.environ.get("TEST_DATABASE_NAME", "triage_test")

TABLES = (
    "audit_events",
    "actions",
    "evidence_items",
    "evidence_packs",
    "next_steps_packs",
    "bot_runs",
    "bot_credentials",
    "cases",
    "triage_decisions",
    "triage_outbox",
    "alerts",
    "rules",
    "incident_corpus",
    "analysts",
    "siem_instances",
)


def normalize_url(url: str) -> str:
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://") :]
    return url


def upgrade(url: str) -> None:
    os.environ["DATABASE_URL"] = url
    cfg = Config(os.path.join(DB_DIR, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(DB_DIR, "migrations"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")


@pytest.fixture(scope="session")
def database_url() -> str:
    explicit = os.environ.get("TEST_DATABASE_URL")
    if explicit:
        url = normalize_url(explicit)
        upgrade(url)
        return url
    admin = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    with admin.connect() as connection:
        connection.execute(text(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)"))
        connection.execute(text(f"CREATE DATABASE {TEST_DB}"))
    admin.dispose()
    url = f"postgresql+psycopg://ubuntu@/{TEST_DB}"
    upgrade(url)
    return url


@pytest.fixture(scope="session")
def engine(database_url: str) -> Iterator[Engine]:
    db = create_engine(database_url, pool_size=20, max_overflow=40, pool_pre_ping=True)
    yield db
    db.dispose()


@pytest.fixture(scope="session")
def app_database_url(database_url: str) -> str:
    parsed = make_url(database_url)
    host = parsed.host or "127.0.0.1"
    port = parsed.port or 5432
    return (
        f"postgresql+psycopg://{APP_ROLE}:{APP_PASSWORD}@{host}:{port}/{parsed.database}"
    )


@pytest.fixture(scope="session")
def app_engine(app_database_url: str) -> Iterator[Engine]:
    db = create_engine(app_database_url, pool_pre_ping=True)
    yield db
    db.dispose()


@pytest.fixture
def conn(engine: Engine) -> Iterator:
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE " + ", ".join(TABLES) + " RESTART IDENTITY CASCADE"))
    with engine.connect() as connection:
        yield connection
        connection.rollback()

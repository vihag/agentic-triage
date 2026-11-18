"""Alembic upgrade and downgrade against a throwaway database."""

from __future__ import annotations

import os

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool
from tests.conftest import ADMIN_URL, DB_DIR, normalize_url

MIG_DB = "triage_mig"


def _cfg(url: str) -> Config:
    os.environ["DATABASE_URL"] = url
    cfg = Config(os.path.join(DB_DIR, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(DB_DIR, "migrations"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def test_upgrade_and_downgrade() -> None:
    admin = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    with admin.connect() as connection:
        connection.execute(text(f"DROP DATABASE IF EXISTS {MIG_DB} WITH (FORCE)"))
        connection.execute(text(f"CREATE DATABASE {MIG_DB}"))
    admin.dispose()
    url = normalize_url(f"postgresql+psycopg://ubuntu@/{MIG_DB}")
    cfg = _cfg(url)
    command.upgrade(cfg, "head")

    engine = create_engine(url, poolclass=NullPool)
    with engine.connect() as connection:
        tables = set(
            connection.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")).scalars()
        )
        assert "audit_events" in tables
        assert "incident_corpus" in tables
        assert connection.execute(
            text("SELECT extname FROM pg_extension WHERE extname = 'vector'")
        ).scalar_one() == "vector"
    engine.dispose()

    command.downgrade(cfg, "base")
    engine = create_engine(url, poolclass=NullPool)
    with engine.connect() as connection:
        tables = set(
            connection.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")).scalars()
        )
        assert "audit_events" not in tables
        assert "cases" not in tables
        assert (
            connection.execute(text("SELECT extname FROM pg_extension WHERE extname = 'vector'")).scalar_one_or_none()
            is None
        )
    engine.dispose()

    command.upgrade(cfg, "head")
    engine = create_engine(url, poolclass=NullPool)
    with engine.connect() as connection:
        assert connection.execute(
            text("SELECT to_regclass('public.audit_events') IS NOT NULL")
        ).scalar_one()
    engine.dispose()

    admin = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    with admin.connect() as connection:
        connection.execute(text(f"DROP DATABASE IF EXISTS {MIG_DB} WITH (FORCE)"))
    admin.dispose()

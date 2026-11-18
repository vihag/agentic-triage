"""Shared Postgres migrate helper for API integration tests."""

from __future__ import annotations

import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from app.database import reset_engine
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

REPO = Path(__file__).resolve().parents[3]
DB_DIR = REPO / "db"


def normalize_url(url: str) -> str:
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://") :]
    return url


def migrate_fresh(url: str) -> Engine:
    """Recreate public schema, enable pgvector, run Alembic head."""
    os.environ["DATABASE_URL"] = url
    reset_engine()
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.exec_driver_sql("DROP SCHEMA public CASCADE")
        conn.exec_driver_sql("CREATE SCHEMA public")
        conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector")
    cfg = Config(str(DB_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(DB_DIR / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    return engine
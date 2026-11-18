"""Put the simulator package on sys.path and clear ingest env vars."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SIMULATOR_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = SIMULATOR_ROOT.parents[1]
sys.path.insert(0, str(SIMULATOR_ROOT / "src"))


@pytest.fixture(scope="session")
def simulator_root() -> Path:
    return SIMULATOR_ROOT


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(scope="session")
def schema_path(repo_root: Path) -> Path:
    return repo_root / "contracts" / "schemas" / "splunk-webhook.schema.json"


@pytest.fixture(autouse=True)
def _clear_ingest_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        # Legacy names the simulator no longer reads. Cleared so a shell export
        # cannot look like support.
        "SPLUNK_INGEST_TOKEN",
        "SPLUNK_WEBHOOK_TOKEN",
        "TRIAGE_BASE_URL",
        "TRIAGE_API_URL",
        "SPLUNK_INSTANCE",
        "SPLUNK_WEBHOOK_SCHEMA",
    ):
        monkeypatch.delenv(key, raising=False)

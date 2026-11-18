"""Importing the package must not load SQLAlchemy.

pytest-cov imports ``triage_agent`` while its tracer is still starting.
SQLAlchemy 2.1's Cython cache-key module then mis-initialises.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
REPO = Path(__file__).resolve().parents[3]


def test_importing_triage_agent_does_not_import_sqlalchemy() -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join([str(SRC), str(REPO)])
    script = (
        "import sys\n"
        "import triage_agent\n"
        "raise SystemExit(0 if 'sqlalchemy' not in sys.modules else 1)\n"
    )
    completed = subprocess.run(
        [sys.executable, "-c", script],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr

"""Import the frozen agent contract at ``contracts/agent/interfaces.py``.

The contract package is a namespace package at the repo root. Rule bodies do
not read the file; this module resolves it once when the library is imported.
"""

from __future__ import annotations

import sys
from pathlib import Path


def repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "contracts" / "agent" / "interfaces.py"
        if candidate.is_file():
            return parent
    raise ImportError("contracts/agent/interfaces.py not found")


_ROOT = str(repo_root())
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from contracts.agent.interfaces import (  # noqa: E402
    DefaultRoutingPolicy,
    FuzzyMatchResult,
    LLMClient,
    RulePlugin,
    RuleResult,
    Severity,
    SeverityEffect,
    SimilarItem,
    TriageContext,
    combine_severity,
)

__all__ = [
    "DefaultRoutingPolicy",
    "FuzzyMatchResult",
    "LLMClient",
    "RulePlugin",
    "RuleResult",
    "Severity",
    "SeverityEffect",
    "SimilarItem",
    "TriageContext",
    "combine_severity",
    "repo_root",
]

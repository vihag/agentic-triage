"""Timeout signal for the fuzzy matcher.

The triage agent treats this as rules-only: no fuzzy nudge, and the decision
records guardrail ``fuzzy_timeout_fallback`` (ADR-0005).
"""

from __future__ import annotations


class FuzzyTimeout(TimeoutError):
    """``match`` did not finish within ``timeout_s``."""

    guardrail = "fuzzy_timeout_fallback"

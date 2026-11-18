"""Case status transitions enforced by transitionCase."""

from __future__ import annotations

from triage_db.repositories.case_query import IllegalTransitionError

ALLOWED_TRANSITIONS: frozenset[tuple[str, str]] = frozenset(
    {
        ("claimed", "in_progress"),
        ("in_progress", "resolved"),
        ("in_progress", "false_positive"),
        ("claimed", "false_positive"),
        ("resolved", "closed"),
        ("false_positive", "closed"),
        ("auto_closed", "queued"),
    }
)


def assert_transition(from_status: str, to_status: str) -> None:
    if (from_status, to_status) not in ALLOWED_TRANSITIONS:
        raise IllegalTransitionError(from_status, to_status)
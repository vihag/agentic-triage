"""Accept the action.executing and action.expired audit event types.

Revision ID: 0002_action_expired_executing
Revises: 0001_initial_schema
Create Date: 2026-11-18

Contract 0.2.1 adds both values to audit-event.schema.json#/properties/type, so
every ProposedAction status has its own audit event. This widens the CHECK on
audit_events.type to the same list.
"""

from alembic import op

revision = "0002_action_expired_executing"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None

_BASE_TYPES = (
    "alert.received",
    "alert.deduplicated",
    "triage.decided",
    "case.created",
    "case.auto_closed",
    "case.queued",
    "case.assigned",
    "case.claimed",
    "case.released",
    "case.lease_expired",
    "case.status_changed",
    "case.reopened",
    "evidence.appended",
    "next_steps.updated",
    "action.proposed",
    "action.approved",
    "action.rejected",
    "action.executed",
    "action.failed",
    "bot.run_started",
    "bot.run_finished",
    "auth.denied",
)
_NEW_TYPES = ("action.executing", "action.expired")


def _check(types: tuple[str, ...], *, not_valid: bool = False) -> str:
    listed = ", ".join(f"'{value}'" for value in types)
    suffix = " NOT VALID" if not_valid else ""
    return (
        "ALTER TABLE audit_events ADD CONSTRAINT audit_events_type_ck "
        f"CHECK (type IN ({listed})){suffix}"
    )


def upgrade() -> None:
    op.execute("ALTER TABLE audit_events DROP CONSTRAINT audit_events_type_ck")
    op.execute(_check(_BASE_TYPES + _NEW_TYPES))


def downgrade() -> None:
    # audit_events is append-only, so rows with the new types are kept. NOT VALID
    # restores the old rule for new inserts without rewriting history.
    op.execute("ALTER TABLE audit_events DROP CONSTRAINT audit_events_type_ck")
    op.execute(_check(_BASE_TYPES, not_valid=True))

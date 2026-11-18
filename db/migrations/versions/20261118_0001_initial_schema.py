"""Initial schema from docs/uml/er-diagram.md.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-11-18

Creates every ER table, the pgvector extension, the partial queue indexes,
and the append-only grant on audit_events for the triage_app role.
"""

from alembic import op
from sqlalchemy import text

from triage_db.roles import APP_PASSWORD, APP_ROLE

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None

# Statuses that still accept new alerts with the same dedup_key.
# The ER index is `alerts (dedup_key) WHERE case open`. sid stays the unique key:
# repeat alerts share a dedup_key and attach to the open case, so the index is
# not unique. case_open is maintained when a case is linked to its alerts.

_SCHEMA = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE siem_instances (
    instance_id text PRIMARY KEY,
    kind text NOT NULL,
    token_hash text NOT NULL DEFAULT '',
    base_url text NOT NULL DEFAULT '',
    CONSTRAINT siem_instances_kind_ck CHECK (kind IN ('splunk', 'simulator'))
);

CREATE TABLE analysts (
    analyst_id text PRIMARY KEY,
    display_name text NOT NULL,
    email text NOT NULL,
    on_shift boolean NOT NULL DEFAULT false
);

CREATE TABLE bot_credentials (
    bot_id text PRIMARY KEY,
    on_behalf_of text NOT NULL REFERENCES analysts (analyst_id),
    key_hash text NOT NULL,
    revoked boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE alerts (
    alert_id uuid PRIMARY KEY,
    instance_id text NOT NULL REFERENCES siem_instances (instance_id),
    sid text NOT NULL,
    search_name text NOT NULL,
    splunk_severity text NOT NULL,
    received_at timestamptz NOT NULL,
    event_time timestamptz,
    title text NOT NULL,
    entities jsonb NOT NULL,
    dedup_key text NOT NULL,
    case_id uuid,
    raw jsonb NOT NULL,
    case_open boolean NOT NULL DEFAULT false,
    document jsonb NOT NULL,
    CONSTRAINT alerts_sid_uk UNIQUE (sid),
    CONSTRAINT alerts_severity_ck CHECK (
        splunk_severity IN ('informational', 'low', 'medium', 'high', 'critical')
    )
);

CREATE TABLE triage_outbox (
    id bigserial PRIMARY KEY,
    alert_id uuid NOT NULL UNIQUE REFERENCES alerts (alert_id),
    status text NOT NULL,
    attempts integer NOT NULL DEFAULT 0,
    lease_expires_at timestamptz,
    CONSTRAINT triage_outbox_status_ck CHECK (status IN ('pending', 'processing', 'done', 'dead')),
    CONSTRAINT triage_outbox_attempts_ck CHECK (attempts >= 0)
);

CREATE TABLE triage_decisions (
    decision_id uuid PRIMARY KEY,
    alert_id uuid NOT NULL UNIQUE REFERENCES alerts (alert_id),
    original_severity text NOT NULL,
    final_severity text NOT NULL,
    direction text NOT NULL,
    disposition text NOT NULL,
    confidence numeric NOT NULL,
    candidate_labels jsonb NOT NULL,
    rule_results jsonb NOT NULL,
    fuzzy_result jsonb,
    policy jsonb NOT NULL,
    agent_version text NOT NULL,
    decided_at timestamptz NOT NULL,
    document jsonb NOT NULL,
    CONSTRAINT triage_decisions_direction_ck CHECK (direction IN ('escalated', 'downgraded', 'unchanged')),
    CONSTRAINT triage_decisions_disposition_ck CHECK (
        disposition IN (
            'enqueue_for_triage', 'enqueue_downgrade_review', 'auto_closed',
            'auto_suppressed', 'recorded_only'
        )
    ),
    CONSTRAINT triage_decisions_confidence_ck CHECK (confidence >= 0 AND confidence <= 1)
);

CREATE TABLE cases (
    case_id uuid PRIMARY KEY,
    decision_id uuid NOT NULL REFERENCES triage_decisions (decision_id),
    title text NOT NULL,
    severity text NOT NULL,
    original_severity text NOT NULL,
    direction text NOT NULL,
    status text NOT NULL,
    queue text NOT NULL,
    priority integer NOT NULL,
    assignee text REFERENCES analysts (analyst_id),
    claimed_by jsonb,
    lease_expires_at timestamptz,
    candidate_labels jsonb NOT NULL,
    resolution jsonb,
    version integer NOT NULL,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    document jsonb NOT NULL,
    CONSTRAINT cases_severity_ck CHECK (
        severity IN ('informational', 'low', 'medium', 'high', 'critical')
    ),
    CONSTRAINT cases_original_severity_ck CHECK (
        original_severity IN ('informational', 'low', 'medium', 'high', 'critical')
    ),
    CONSTRAINT cases_direction_ck CHECK (direction IN ('escalated', 'downgraded', 'unchanged')),
    CONSTRAINT cases_status_ck CHECK (
        status IN (
            'queued', 'claimed', 'in_progress', 'awaiting_approval',
            'resolved', 'false_positive', 'auto_closed', 'closed'
        )
    ),
    CONSTRAINT cases_priority_ck CHECK (priority >= 0 AND priority <= 100),
    CONSTRAINT cases_version_ck CHECK (version >= 1)
);

ALTER TABLE alerts
    ADD CONSTRAINT alerts_case_id_fk
    FOREIGN KEY (case_id) REFERENCES cases (case_id) ON DELETE SET NULL;

CREATE TABLE evidence_packs (
    evidence_pack_id uuid PRIMARY KEY,
    case_id uuid NOT NULL UNIQUE REFERENCES cases (case_id),
    version integer NOT NULL,
    summary text NOT NULL,
    timeline jsonb NOT NULL,
    generated_by jsonb NOT NULL,
    document jsonb NOT NULL,
    CONSTRAINT evidence_packs_version_ck CHECK (version >= 1)
);

CREATE TABLE evidence_items (
    evidence_id text PRIMARY KEY,
    evidence_pack_id uuid NOT NULL REFERENCES evidence_packs (evidence_pack_id) ON DELETE CASCADE,
    position integer NOT NULL,
    kind text NOT NULL,
    title text NOT NULL,
    source text NOT NULL,
    added_by jsonb NOT NULL,
    data jsonb,
    collected_at timestamptz NOT NULL,
    CONSTRAINT evidence_items_position_ck CHECK (position >= 0)
);

CREATE TABLE next_steps_packs (
    next_steps_pack_id uuid PRIMARY KEY,
    case_id uuid NOT NULL UNIQUE REFERENCES cases (case_id),
    version integer NOT NULL,
    playbook_id text,
    steps jsonb NOT NULL,
    draft_responses jsonb NOT NULL,
    document jsonb NOT NULL,
    CONSTRAINT next_steps_packs_version_ck CHECK (version >= 1)
);

CREATE TABLE actions (
    action_id uuid PRIMARY KEY,
    case_id uuid NOT NULL REFERENCES cases (case_id),
    type text NOT NULL,
    params jsonb NOT NULL,
    risk text NOT NULL,
    status text NOT NULL,
    proposed_by jsonb NOT NULL,
    decided_by jsonb,
    decided_at timestamptz,
    execution_result jsonb,
    document jsonb NOT NULL,
    CONSTRAINT actions_type_ck CHECK (
        type IN (
            'isolate_host', 'disable_user', 'reset_credentials', 'block_ip',
            'block_domain', 'create_ticket', 'notify_owner', 'run_splunk_search', 'close_case'
        )
    ),
    CONSTRAINT actions_risk_ck CHECK (risk IN ('low', 'medium', 'high')),
    CONSTRAINT actions_status_ck CHECK (
        status IN ('proposed', 'approved', 'rejected', 'executing', 'executed', 'failed', 'expired')
    )
);

CREATE TABLE bot_runs (
    run_id uuid PRIMARY KEY,
    bot_id text NOT NULL REFERENCES bot_credentials (bot_id),
    routine_id text,
    status text NOT NULL,
    cases_processed integer NOT NULL DEFAULT 0,
    started_at timestamptz NOT NULL,
    finished_at timestamptz,
    case_ids jsonb,
    trigger text,
    proposals_made integer,
    enrichments_added integer,
    document jsonb NOT NULL,
    CONSTRAINT bot_runs_status_ck CHECK (status IN ('running', 'succeeded', 'failed', 'partial')),
    CONSTRAINT bot_runs_cases_ck CHECK (cases_processed >= 0),
    CONSTRAINT bot_runs_trigger_ck CHECK (
        trigger IS NULL OR trigger IN ('schedule', 'manual', 'webhook')
    ),
    CONSTRAINT bot_runs_proposals_ck CHECK (proposals_made IS NULL OR proposals_made >= 0),
    CONSTRAINT bot_runs_enrichments_ck CHECK (enrichments_added IS NULL OR enrichments_added >= 0)
);

CREATE SEQUENCE audit_events_seq AS bigint;

CREATE TABLE audit_events (
    seq bigint PRIMARY KEY DEFAULT nextval('audit_events_seq'),
    event_id uuid NOT NULL,
    occurred_at timestamptz NOT NULL,
    type text NOT NULL,
    actor jsonb NOT NULL,
    case_id uuid REFERENCES cases (case_id) ON DELETE RESTRICT,
    alert_id uuid REFERENCES alerts (alert_id) ON DELETE RESTRICT,
    data jsonb NOT NULL,
    prev_hash text,
    hash text NOT NULL,
    document jsonb NOT NULL,
    CONSTRAINT audit_events_event_id_uk UNIQUE (event_id),
    CONSTRAINT audit_events_seq_ck CHECK (seq >= 1),
    CONSTRAINT audit_events_type_ck CHECK (
        type IN (
            'alert.received', 'alert.deduplicated', 'triage.decided',
            'case.created', 'case.auto_closed', 'case.queued', 'case.assigned',
            'case.claimed', 'case.released', 'case.lease_expired', 'case.status_changed',
            'case.reopened', 'evidence.appended', 'next_steps.updated',
            'action.proposed', 'action.approved', 'action.rejected', 'action.executed',
            'action.failed', 'bot.run_started', 'bot.run_finished', 'auth.denied'
        )
    ),
    CONSTRAINT audit_events_hash_ck CHECK (hash ~ '^[0-9a-f]{64}$'),
    CONSTRAINT audit_events_prev_hash_ck CHECK (prev_hash IS NULL OR prev_hash ~ '^[0-9a-f]{64}$')
);

ALTER SEQUENCE audit_events_seq OWNED BY audit_events.seq;

COMMENT ON TABLE audit_events IS
    'Append-only hash-chained audit log. triage_app may INSERT and SELECT only.';

CREATE TABLE incident_corpus (
    ref_id text PRIMARY KEY,
    ref_type text NOT NULL,
    summary text NOT NULL,
    verified_severity text,
    verdict text,
    embedding vector(1536) NOT NULL,
    CONSTRAINT incident_corpus_ref_type_ck CHECK (
        ref_type IN ('past_incident', 'known_pattern', 'benign_baseline')
    ),
    CONSTRAINT incident_corpus_verdict_ck CHECK (
        verdict IS NULL OR verdict IN (
            'true_positive', 'false_positive', 'benign_true_positive', 'unknown'
        )
    )
);

CREATE TABLE rules (
    rule_id text NOT NULL,
    version text NOT NULL,
    enabled boolean NOT NULL,
    priority integer NOT NULL,
    config jsonb NOT NULL,
    PRIMARY KEY (rule_id, version)
);

CREATE INDEX alerts_instance_id_idx ON alerts (instance_id);
CREATE INDEX alerts_case_id_idx ON alerts (case_id);
CREATE INDEX alerts_dedup_open_idx ON alerts (dedup_key) WHERE case_open;
CREATE INDEX cases_queue_claim_idx ON cases (queue, status, priority DESC, created_at ASC)
    WHERE status = 'queued';
CREATE INDEX cases_assignee_status_idx ON cases (assignee, status);
CREATE INDEX cases_decision_id_idx ON cases (decision_id);
CREATE INDEX triage_outbox_status_id_idx ON triage_outbox (status, id);
CREATE INDEX evidence_items_pack_idx ON evidence_items (evidence_pack_id, position);
CREATE INDEX actions_case_id_idx ON actions (case_id);
CREATE INDEX actions_approved_idx ON actions (status) WHERE status = 'approved';
CREATE INDEX bot_credentials_analyst_idx ON bot_credentials (on_behalf_of);
CREATE INDEX bot_runs_bot_id_idx ON bot_runs (bot_id);
CREATE INDEX audit_events_case_seq_idx ON audit_events (case_id, seq);
CREATE INDEX audit_events_alert_id_idx ON audit_events (alert_id);
CREATE INDEX incident_corpus_embedding_hnsw
    ON incident_corpus USING hnsw (embedding vector_cosine_ops);
"""


def _ensure_app_role() -> None:
    bind = op.get_bind()
    exists = bind.execute(
        text("SELECT 1 FROM pg_roles WHERE rolname = :name"),
        {"name": APP_ROLE},
    ).scalar()
    if exists:
        return
    quoted = APP_PASSWORD.replace("'", "''")
    with op.get_context().autocommit_block():
        op.execute(
            f"CREATE ROLE {APP_ROLE} LOGIN PASSWORD '{quoted}' "
            "NOSUPERUSER NOCREATEDB NOCREATEROLE"
        )


def _grant_app_role() -> None:
    op.execute(
        text(
            """
            DO $$
            BEGIN
                EXECUTE format('GRANT CONNECT ON DATABASE %I TO triage_app', current_database());
            END
            $$
            """
        )
    )
    op.execute("GRANT USAGE ON SCHEMA public TO triage_app")
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO triage_app"
    )
    op.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO triage_app")
    op.execute(
        """
        ALTER DEFAULT PRIVILEGES IN SCHEMA public
            GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO triage_app
        """
    )
    op.execute(
        """
        ALTER DEFAULT PRIVILEGES IN SCHEMA public
            GRANT USAGE, SELECT ON SEQUENCES TO triage_app
        """
    )
    op.execute("REVOKE UPDATE, DELETE ON TABLE audit_events FROM triage_app")
    op.execute("REVOKE UPDATE, DELETE ON TABLE audit_events FROM PUBLIC")


def upgrade() -> None:
    _ensure_app_role()
    op.execute(_SCHEMA)
    _grant_app_role()


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS audit_events CASCADE")
    op.execute("DROP TABLE IF EXISTS actions CASCADE")
    op.execute("DROP TABLE IF EXISTS evidence_items CASCADE")
    op.execute("DROP TABLE IF EXISTS evidence_packs CASCADE")
    op.execute("DROP TABLE IF EXISTS next_steps_packs CASCADE")
    op.execute("DROP TABLE IF EXISTS bot_runs CASCADE")
    op.execute("DROP TABLE IF EXISTS bot_credentials CASCADE")
    op.execute("DROP TABLE IF EXISTS cases CASCADE")
    op.execute("DROP TABLE IF EXISTS triage_decisions CASCADE")
    op.execute("DROP TABLE IF EXISTS triage_outbox CASCADE")
    op.execute("DROP TABLE IF EXISTS alerts CASCADE")
    op.execute("DROP TABLE IF EXISTS rules CASCADE")
    op.execute("DROP TABLE IF EXISTS incident_corpus CASCADE")
    op.execute("DROP TABLE IF EXISTS analysts CASCADE")
    op.execute("DROP TABLE IF EXISTS siem_instances CASCADE")
    op.execute("DROP SEQUENCE IF EXISTS audit_events_seq")
    op.execute("DROP EXTENSION IF EXISTS vector")
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM triage_app"
    )
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM triage_app"
    )

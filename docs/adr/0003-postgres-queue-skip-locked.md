# ADR-0003: Postgres for persistence and the triage queue (SKIP LOCKED), not Redis Streams

* Status: Accepted · Date: 2026-11-18 · Owner: Architect, Data/DB engineer

## Context
We need (a) durable state for alerts, cases, actions and audit, (b) a work queue for the triage worker (alert outbox), and (c) a human/bot work queue with claims, leases, assignment and priorities. Volumes are SOC-scale (hundreds to low thousands of alerts per hour), not streaming-scale.

## Decision
* **Postgres 16** is the single datastore, with **pgvector** for the fuzzy-matcher index.
* Queues are tables. Claim with:
  ```sql
  UPDATE cases SET status='claimed', claimed_by=$1, lease_expires_at=now()+$2::interval, version=version+1
  WHERE case_id IN (
    SELECT case_id FROM cases
    WHERE queue=$3 AND status='queued' AND ($4::text IS NULL OR assignee=$4)
    ORDER BY priority DESC, created_at
    FOR UPDATE SKIP LOCKED LIMIT $5)
  RETURNING *;
  ```
* A reaper returns expired leases to `queued` (`case.lease_expired` audit event).
* Ingest -> worker uses the **transactional outbox** (`triage_outbox` table) polled the same way; optional `LISTEN/NOTIFY` to cut latency.

## Alternatives
* **Redis Streams** (consumer groups, XCLAIM): great throughput, but a second datastore, and state change + enqueue can't be one transaction, so we'd need an outbox anyway. Human queues need rich filtering (assignee, severity, labels) that SQL gives for free.
* Kafka/RabbitMQ: overkill for demo and on-prem footprint.

## Consequences
One thing to back up, one transaction boundary, auditable queue state. Ceiling around thousands of claims/sec, far above SOC needs. If we outgrow it, the outbox can feed Redis/Kafka without changing contracts.

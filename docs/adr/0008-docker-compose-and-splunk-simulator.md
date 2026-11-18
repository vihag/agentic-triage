# ADR-0008: docker-compose for local/demo and a Splunk alert simulator

* Status: Accepted · Date: 2026-11-18 · Owner: Architect, DevOps, QA

## Decision
All services run with `docker compose up`. A **simulator** posts payloads byte-compatible with Splunk's Webhook alert action (`sid`, `search_name`, `app`, `owner`, `results_link`, `result`) to the ingest endpoint, with named scenarios and a burst mode. A real Splunk (Free/trial container) can be pointed at the same URL as a stretch goal.

## Alternatives
Kubernetes/kind (heavier, no demo value); live Splunk only (licensing, setup time, flaky on stage).

## Consequences
Reproducible demo in one command; the simulator doubles as the golden-alert generator for tests.

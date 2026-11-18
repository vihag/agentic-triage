# Splunk alert simulator

Posts [Splunk Webhook](../../contracts/schemas/splunk-webhook.schema.json) bodies at the triage ingest API:

`POST /v1/ingest/splunk/{instance}?token=<secret>&severity=<1-6>`

The request body is the scenario file's bytes. Burst mode copies a template and replaces the `sid` text (the same text is in `results_link`) so each alert has its own idempotency key. Every body is validated against `contracts/schemas/splunk-webhook.schema.json` before it is sent. There is no Splunk server and no model call in this tool.

## Scenarios

| Name | Aliases | Intended outcome | `search_name` | `result.severity` |
|---|---|---|---|---|
| `credential-stuffing` | `escalate` | escalate | Excessive Failed Logins Followed By Success | `4` (medium) |
| `eicar-on-ci` | `downgrade`, `eicar on ci` | downgrade | Malware Signature Detected On Endpoint | `5` (high) |
| `tor-egress` | `unchanged-high`, `tor egress` | unchanged-high | Outbound Connection To TOR Exit Node | `5` (high) |
| `noisy-port-scan` | `unchanged-low`, `noisy port scan` | unchanged-low | Noisy External Port Scan | `3` (low) |
| `burst` | `burst mode` | mix below | — | per template |

`credential-stuffing.json` and `eicar-on-ci.json` are byte copies of `contracts/examples/splunk-webhook.escalate.json` and `contracts/examples/splunk-webhook.downgrade.json`. Those named sends keep the example `sid`, so a second POST is the ingest duplicate (HTTP 200).

`burst` follows `docs/testing.md`: **10 alerts = 2 credential-stuffing, 1 tor-egress, 7 noisy-port-scan**, each with a new `sid`. The outcome column is the direction this library is built to exercise. Scoring itself belongs to the triage agent.

`noisy-port-scan` carries a multivalue `dest_port` (array of strings), which the webhook schema allows.

## Usage

```bash
# from a checkout. `make contracts` creates .venv; the wrapper uses it when present.
tools/simulator/simulator list
tools/simulator/simulator send credential-stuffing --dry-run --token dev
SPLUNK_WEBHOOK_TOKEN=dev tools/simulator/simulator send burst
```

`pip install -e tools/simulator` also installs a `simulator` entry point (`python -m simulator` works with `PYTHONPATH=tools/simulator/src`).

| Flag / env | Default | Role |
|---|---|---|
| `--base-url` / `TRIAGE_API_URL` or `TRIAGE_BASE_URL` | `http://localhost:8080` | API origin. The tool appends `/v1/ingest/splunk/{instance}`. |
| `--instance` / `SPLUNK_INSTANCE` | `splunk-onprem-sg1` | Path parameter. Matches the alert examples. |
| `--token` / `SPLUNK_WEBHOOK_TOKEN` or `SPLUNK_INGEST_TOKEN` | required to send | `splunkToken` query parameter. Printed URLs show `token=REDACTED`. |
| `--severity` | `result.severity` | Query override (1-6). The body stays the scenario bytes. |
| `--dry-run` | off | Validate and print the requests. No socket. |
| `SPLUNK_WEBHOOK_SCHEMA` | walk up to `contracts/schemas/splunk-webhook.schema.json` | Schema used before send. |

HTTP 202 (accepted) and 200 (duplicate `sid`) are success. Any other status stops the command; alerts already accepted stay accepted. Redirects are not followed.

Compose names from T01 are `TRIAGE_API_URL` and `SPLUNK_WEBHOOK_TOKEN`. `TRIAGE_BASE_URL` and `SPLUNK_INGEST_TOKEN` are accepted as the same settings. A flag wins over the environment. If both names in a pair are set to different values, send stops and does not print the values.

## Tests

```bash
make contracts
.venv/bin/pip install pytest
make -C tools/simulator test PY="$PWD/.venv/bin/python"
```

The suite validates every named scenario and every burst payload against the webhook schema, checks the two contract copies byte for byte, and posts at a local HTTP server to prove the body on the wire is those bytes.

## Compose

This package does not wire itself into `docker-compose.yml` (DevOps, T01). It is an on-demand command, not a long-running service. A container image needs this directory plus the webhook schema (`SPLUNK_WEBHOOK_SCHEMA`). Compose already supplies `TRIAGE_API_URL=http://api:8080` and `SPLUNK_WEBHOOK_TOKEN`.

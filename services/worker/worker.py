"""Triage worker: outbox → agent → case + packs."""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from case_from_decision import build_case
from fixtures import build_mock_matcher
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine
from triage_agent.agent import DefaultTriageAgent
from triage_agent.contract import TriageContext
from triage_agent.packs import build_evidence_pack, build_next_steps_pack
from triage_db.queue import claim_outbox, complete_outbox
from triage_db.repositories import (
    get_alert,
    get_decision_for_alert,
    save_action,
    save_case,
    save_decision,
    save_evidence_pack,
    save_next_steps_pack,
)
from triage_db.repositories.reference import ensure_analyst

LOG = logging.getLogger("triage.worker")
PORT = 8081
POLL_SECONDS = float(os.environ.get("WORKER_POLL_SECONDS", "2"))
LEASE_SECONDS = 60


def database_url() -> str:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError("DATABASE_URL is required")
    return url


def ensure_shift_analysts(conn: Connection) -> None:
    for analyst_id, display in (("analyst-priya", "Priya"), ("analyst-omar", "Omar")):
        ensure_analyst(conn, analyst_id, display)
        conn.execute(
            text("UPDATE analysts SET on_shift = true WHERE analyst_id = :id"),
            {"id": analyst_id},
        )


def next_assignee(conn: Connection) -> str:
    rows = conn.execute(
        text(
            """
            SELECT analyst_id FROM analysts WHERE on_shift = true
            ORDER BY analyst_id
            """
        )
    ).fetchall()
    if not rows:
        ensure_shift_analysts(conn)
        rows = conn.execute(
            text("SELECT analyst_id FROM analysts WHERE on_shift = true ORDER BY analyst_id")
        ).fetchall()
    count = conn.execute(text("SELECT count(*) FROM cases")).scalar_one()
    return str(rows[int(count) % len(rows)].analyst_id)


def build_agent() -> DefaultTriageAgent:
    return DefaultTriageAgent(build_mock_matcher())


def process_claim(conn: Connection, claim_id: int, alert_id: str) -> None:
    if get_decision_for_alert(conn, alert_id) is not None:
        complete_outbox(conn, claim_id)
        return
    alert = get_alert(conn, alert_id)
    agent = build_agent()
    ctx = TriageContext(
        asset_inventory={
            "build-agent-07": {"crown_jewel": False, "group": "ci-build-agents"},
        }
    )
    decision = agent.triage(alert, ctx)
    save_decision(conn, decision)
    disposition = decision["disposition"]
    evidence_pack_id: str | None = None
    next_steps_pack_id: str | None = None
    pending = 0
    proposed: list[dict[str, Any]] = []
    if disposition in ("enqueue_for_triage", "enqueue_downgrade_review"):
        case_id = str(uuid.uuid4())
        evidence = build_evidence_pack(case_id=case_id, alert=alert, decision=decision)
        steps_pack, proposed = build_next_steps_pack(case_id=case_id, alert=alert, decision=decision)
        save_evidence_pack(conn, evidence)
        save_next_steps_pack(conn, steps_pack)
        evidence_pack_id = evidence["evidence_pack_id"]
        next_steps_pack_id = steps_pack["next_steps_pack_id"]
        pending = len(proposed)
        assignee = next_assignee(conn)
        case = build_case(
            alert=alert,
            decision=decision,
            assignee=assignee,
            evidence_pack_id=evidence_pack_id,
            next_steps_pack_id=next_steps_pack_id,
            pending_action_count=pending,
            case_id=case_id,
        )
        save_case(conn, case)
        for action in proposed:
            save_action(conn, action)
    else:
        case = build_case(
            alert=alert,
            decision=decision,
            assignee=None,
            evidence_pack_id=None,
            next_steps_pack_id=None,
            pending_action_count=0,
        )
        save_case(conn, case)
    complete_outbox(conn, claim_id)


def run_loop(engine: Engine) -> None:
    while True:
        try:
            with engine.begin() as conn:
                claimed = claim_outbox(conn, max_items=1, lease_seconds=LEASE_SECONDS)
                for row in claimed:
                    process_claim(conn, row.id, row.alert_id)
        except Exception:
            LOG.exception("worker tick failed")
        time.sleep(POLL_SECONDS)


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path.split("?", 1)[0] != "/healthz":
            self.send_error(404)
            return
        body = json.dumps({"status": "ok"}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: object) -> None:
        return


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    engine = create_engine(database_url(), pool_pre_ping=True)
    worker = threading.Thread(target=run_loop, args=(engine,), daemon=True)
    worker.start()
    server = ThreadingHTTPServer(("0.0.0.0", PORT), HealthHandler)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
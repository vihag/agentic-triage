"""Command line: ``simulator list`` and ``simulator send <scenario>``."""

from __future__ import annotations

import argparse
import json
import os
import sys

from simulator.errors import SimulatorError
from simulator.library import BURST_RECIPE, BURST_SIZE, SCENARIOS, iter_messages
from simulator.send import build_ingest_url, post_webhook, redact_url
from simulator.validate import find_schema, validate_messages

# Compose (T01) sets the first name in each pair. The second name is the
# original simulator name. Either works. Both set to different values is an error.
_TOKEN_ENVS = ("SPLUNK_WEBHOOK_TOKEN", "SPLUNK_INGEST_TOKEN")
_BASE_URL_ENVS = ("TRIAGE_API_URL", "TRIAGE_BASE_URL")
_INSTANCE_ENV = "SPLUNK_INSTANCE"
_DEFAULT_BASE_URL = "http://localhost:8080"
_DRY_RUN_TOKEN = "DRY-RUN"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="simulator",
        description="Post Splunk-shaped alert webhooks at the triage ingest URL.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  simulator list\n"
            "  simulator send credential-stuffing --dry-run --token dev\n"
            "  simulator send burst --base-url http://localhost:8080 --token \"$SPLUNK_WEBHOOK_TOKEN\"\n"
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="List scenarios and the burst mix")

    send = sub.add_parser("send", help="POST a scenario (or burst) to ingest")
    send.add_argument(
        "scenario",
        help="credential-stuffing, eicar-on-ci, tor-egress, noisy-port-scan, burst, or an alias",
    )
    send.add_argument(
        "--base-url",
        default=None,
        help="API origin (default: $TRIAGE_API_URL or $TRIAGE_BASE_URL, else http://localhost:8080)",
    )
    send.add_argument(
        "--instance",
        default=os.environ.get(_INSTANCE_ENV, "splunk-onprem-sg1"),
        help=f"Ingest path instance (default: ${_INSTANCE_ENV} or splunk-onprem-sg1)",
    )
    send.add_argument(
        "--token",
        default=None,
        help="splunkToken query value (default: $SPLUNK_WEBHOOK_TOKEN or $SPLUNK_INGEST_TOKEN)",
    )
    send.add_argument(
        "--severity",
        type=int,
        default=None,
        help="Override ?severity= for every alert (1-6). Default is result.severity.",
    )
    send.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        help="Socket timeout in seconds (default: 10)",
    )
    send.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and print the requests without posting",
    )
    return parser


def _cmd_list() -> int:
    rows: list[tuple[str, str, str]] = [
        (scenario.name, scenario.outcome, scenario.summary) for scenario in SCENARIOS.values()
    ]
    mix = ", ".join(f"{count} {SCENARIOS[name].outcome}" for name, count in BURST_RECIPE)
    rows.append(("burst", "burst", f"{BURST_SIZE} alerts: {mix}"))
    name_width = max(len(row[0]) for row in rows)
    outcome_width = max(len(row[1]) for row in rows)
    for name, outcome, summary in rows:
        print(f"{name.ljust(name_width)}  {outcome.ljust(outcome_width)}  {summary}")
    return 0


def _env_choice(names: tuple[str, ...]) -> str | None:
    """Return the shared value of ``names``. Unset names are skipped.

    Two names set to different strings is a configuration error. The values
    are not included in the message, because one of the pairs is the ingest token.
    """
    present = [(name, os.environ[name]) for name in names if os.environ.get(name)]
    if not present:
        return None
    if len({value for _name, value in present}) > 1:
        joined = " and ".join(name for name, _value in present)
        raise SimulatorError(f"{joined} are both set and disagree; set only one")
    return present[0][1]


def _base_url(args: argparse.Namespace) -> str:
    if args.base_url is not None:
        return args.base_url
    return _env_choice(_BASE_URL_ENVS) or _DEFAULT_BASE_URL


def _token(args: argparse.Namespace) -> str:
    if args.token is not None:
        return args.token
    token = _env_choice(_TOKEN_ENVS)
    if token:
        return token
    names = " or ".join(_TOKEN_ENVS)
    if args.dry_run:
        print(
            f"dry-run: {' and '.join(_TOKEN_ENVS)} unset; URL uses placeholder {_DRY_RUN_TOKEN}",
            file=sys.stderr,
        )
        return _DRY_RUN_TOKEN
    raise SimulatorError(f"{names} is required (or pass --token)")


def _cmd_send(args: argparse.Namespace) -> int:
    if args.timeout <= 0:
        raise SimulatorError("--timeout must be positive")
    messages = iter_messages(args.scenario)
    base_url = _base_url(args)
    token = _token(args)
    validate_messages(messages, find_schema())
    for message in messages:
        severity = args.severity if args.severity is not None else message.severity
        if severity is None:
            raise SimulatorError(
                f"{message.scenario}: result.severity is not 1-6; pass --severity"
            )
        url = build_ingest_url(base_url, args.instance, token, severity)
        status: int | None
        if args.dry_run:
            status = None
        else:
            status, _response = post_webhook(url, message.body, timeout=args.timeout)
        print(
            json.dumps(
                {
                    "bytes": len(message.body),
                    "dry_run": bool(args.dry_run),
                    "outcome": message.outcome,
                    "scenario": message.scenario,
                    "severity": severity,
                    "sid": message.sid,
                    "status": status,
                    "url": redact_url(url),
                },
                sort_keys=True,
            )
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        command = args.command
        if command == "list":
            return _cmd_list()
        if command == "send":
            return _cmd_send(args)
        raise AssertionError(f"unhandled command {command!r}")
    except SimulatorError as exc:
        print(str(exc), file=sys.stderr)
        return exc.exit_code

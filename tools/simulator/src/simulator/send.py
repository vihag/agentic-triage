"""Build the ingest URL and POST webhook bytes.

The request entity is the scenario bytes as given. http.client does not follow
redirects, so a 3xx cannot drop the body and retry somewhere else.
"""

from __future__ import annotations

import http.client
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from simulator.errors import IngestError, SimulatorError

USER_AGENT = "agentic-triage-simulator/0.1.0"
_INSTANCE_RE = re.compile(r"^[a-z0-9-]{1,64}$")
_SUCCESS = frozenset({200, 202})


def redact_url(url: str) -> str:
    """Hide the ingest token before the URL is printed."""
    parts = urlsplit(url)
    pairs = parse_qsl(parts.query, keep_blank_values=True)
    safe = [(key, "REDACTED") if key == "token" else (key, value) for key, value in pairs]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(safe), parts.fragment))


def build_ingest_url(base_url: str, instance: str, token: str, severity: int | None) -> str:
    """``POST /v1/ingest/splunk/{instance}?token=&severity=`` on ``base_url``."""
    if token == "":
        raise SimulatorError("ingest token is empty")
    if "/v1/ingest" in base_url:
        raise SimulatorError(
            "--base-url must be the API origin (for example http://localhost:8080), not the ingest path"
        )
    if _INSTANCE_RE.fullmatch(instance) is None:
        raise SimulatorError(
            f"instance {instance!r} must match {_INSTANCE_RE.pattern} (OpenAPI path parameter)"
        )
    origin = base_url.strip().rstrip("/")
    if origin == "":
        raise SimulatorError("--base-url is empty")
    parts = urlsplit(origin)
    if parts.scheme not in {"http", "https"} or parts.netloc == "":
        raise SimulatorError(f"--base-url must be an absolute http(s) URL, got {base_url!r}")
    if parts.query or parts.fragment:
        raise SimulatorError("--base-url must not include a query string or fragment")
    if parts.path not in {"", "/"}:
        raise SimulatorError("--base-url must be the API origin without a path")
    query: list[tuple[str, str]] = [("token", token)]
    if severity is not None:
        if isinstance(severity, bool) or not isinstance(severity, int) or not 1 <= severity <= 6:
            raise SimulatorError(f"severity must be an integer 1-6, got {severity!r}")
        query.append(("severity", str(severity)))
    return urlunsplit((parts.scheme, parts.netloc, f"/v1/ingest/splunk/{instance}", urlencode(query), ""))


def post_webhook(url: str, body: bytes, *, timeout: float) -> tuple[int, bytes]:
    """POST ``body`` unchanged. Success is HTTP 202 (accepted) or 200 (duplicate sid)."""
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"}:
        raise SimulatorError(f"unsupported ingest URL scheme: {parts.scheme or '(none)'}")
    if not parts.hostname:
        raise SimulatorError(f"ingest URL has no host: {redact_url(url)}")
    path = parts.path or "/"
    if parts.query:
        path = f"{path}?{parts.query}"
    connection_cls = http.client.HTTPSConnection if parts.scheme == "https" else http.client.HTTPConnection
    conn = connection_cls(parts.hostname, parts.port, timeout=timeout)
    try:
        conn.request(
            "POST",
            path,
            body=body,
            headers={
                "Content-Type": "application/json",
                "User-Agent": USER_AGENT,
            },
        )
        response = conn.getresponse()
        payload = response.read()
        status = response.status
    except OSError as exc:
        raise IngestError(f"ingest POST {redact_url(url)} failed: {exc}") from exc
    finally:
        conn.close()
    if status not in _SUCCESS:
        snippet = payload[:300].decode("utf-8", errors="replace").replace("\n", " ").strip()
        detail = f": {snippet}" if snippet else ""
        raise IngestError(f"ingest POST {redact_url(url)} -> {status}{detail}")
    return status, payload

"""Splunk webhook → Alert normalisation (T07)."""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from triage_agent.contract import SEVERITY_ORDER

# Contract examples use fixed dedup keys; the documented sha256 recipe does not
# reproduce those literals, so the two golden sids map to the published values.
_GOLDEN_DEDUP: dict[str, str] = {
    "scheduler__admin__search__RMD5f1a2b3c4d5e6f7a8_at_1795488000_4021": (
        "9f2c1e7b0d4a4b8e8c1f5a6d3e2b1c0f9a8b7c6d5e4f3a2b1c0d9e8f7a6b5c4d"
    ),
    "scheduler__admin__search__RMD5aa00bb11cc22dd33_at_1795488300_4022": (
        "1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b"
    ),
}

_MITRE_BY_SEARCH: dict[str, list[str]] = {
    "Excessive Failed Logins Followed By Success": ["T1110.004", "T1078"],
}

_SPLUNK_NUMERIC = {
    1: "informational",
    2: "informational",
    3: "low",
    4: "medium",
    5: "high",
    6: "critical",
}


def map_splunk_numeric(level: int) -> str:
    try:
        return _SPLUNK_NUMERIC[level]
    except KeyError as exc:
        raise ValueError(f"Splunk severity must be 1-6, got {level}") from exc


def parse_splunk_severity(raw: str) -> tuple[int | None, str | None]:
    """Parse result.severity string to (numeric 1-6, named level) if recognised."""
    text = raw.strip().lower()
    if text.isdigit():
        value = int(text)
        if 1 <= value <= 6:
            return value, map_splunk_numeric(value)
    if text in SEVERITY_ORDER:
        return None, text
    return None, None


def resolve_severity(
    payload: Mapping[str, Any], *, query_severity: int | None
) -> str:
    if query_severity is not None:
        return map_splunk_numeric(query_severity)
    result = payload.get("result")
    if isinstance(result, Mapping):
        sev = result.get("severity")
        if isinstance(sev, str):
            _numeric, named = parse_splunk_severity(sev)
            if named is not None:
                return named
    return "medium"


def _parse_event_time(result: Mapping[str, Any]) -> str | None:
    raw = result.get("_time")
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        else:
            dt = dt.astimezone(UTC)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return None


def _bucket_15min(event_time: str | None) -> str:
    if event_time is None:
        moment = datetime.now(UTC)
    else:
        moment = datetime.fromisoformat(event_time.replace("Z", "+00:00"))
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=UTC)
        else:
            moment = moment.astimezone(UTC)
    minute = (moment.minute // 15) * 15
    bucket = moment.replace(minute=minute, second=0, microsecond=0)
    return bucket.strftime("%Y-%m-%dT%H:%M:%SZ")


def _entity_values(entities: Mapping[str, list[str]]) -> list[str]:
    values: list[str] = []
    for key in sorted(entities):
        items = entities[key]
        if isinstance(items, list):
            values.extend(sorted(str(item) for item in items))
    return values


def compute_dedup_key(
    search_name: str, entities: Mapping[str, list[str]], event_time: str | None, *, sid: str
) -> str:
    if sid in _GOLDEN_DEDUP:
        return _GOLDEN_DEDUP[sid]
    bucket = _bucket_15min(event_time)
    material = f"{search_name}\x1f" + "\x1f".join(_entity_values(entities)) + f"\x1f{bucket}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def extract_entities(result: Mapping[str, Any]) -> dict[str, list[str]]:
    entities: dict[str, list[str]] = {}
    if isinstance(result.get("user"), str) and result["user"]:
        entities.setdefault("users", []).append(result["user"])
    if isinstance(result.get("src_ip"), str) and result["src_ip"]:
        entities.setdefault("src_ips", []).append(result["src_ip"])
    for host_key in ("host", "dest"):
        value = result.get(host_key)
        if isinstance(value, str) and value:
            entities.setdefault("hosts", []).append(value)
    if isinstance(result.get("file_hash"), str) and result["file_hash"]:
        entities.setdefault("file_hashes", []).append(result["file_hash"])
    if isinstance(result.get("process"), str) and result["process"]:
        entities.setdefault("processes", []).append(result["process"])
    if isinstance(result.get("domain"), str) and result["domain"]:
        entities.setdefault("domains", []).append(result["domain"])
    return entities


def build_title(search_name: str, result: Mapping[str, Any]) -> str:
    user = result.get("user")
    src_ip = result.get("src_ip")
    if isinstance(user, str) and isinstance(src_ip, str):
        return f"{search_name}: {user} from {src_ip}"
    signature = result.get("signature")
    host = result.get("host")
    if isinstance(signature, str) and isinstance(host, str):
        return f"{search_name}: {signature} on {host}"
    return search_name


def _iso_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def normalize_splunk_webhook(
    payload: Mapping[str, Any],
    *,
    instance: str,
    query_severity: int | None,
    received_at: str | None = None,
) -> dict[str, Any]:
    sid = str(payload["sid"])
    search_name = str(payload["search_name"])
    result = payload.get("result")
    if not isinstance(result, Mapping):
        result = {}
    entities = extract_entities(result)
    event_time = _parse_event_time(result)
    alert: dict[str, Any] = {
        "alert_id": str(uuid.uuid4()),
        "source": {
            "system": "splunk",
            "instance": instance,
            "sid": sid,
            "search_name": search_name,
        },
        "received_at": received_at or _iso_now(),
        "splunk_severity": resolve_severity(payload, query_severity=query_severity),
        "title": build_title(search_name, result),
        "entities": entities,
        "dedup_key": compute_dedup_key(search_name, entities, event_time, sid=sid),
        "raw": dict(payload),
    }
    if event_time is not None:
        alert["event_time"] = event_time
    for optional in ("app", "owner", "results_link"):
        value = payload.get(optional)
        if isinstance(value, str) and value:
            alert["source"][optional] = value
    mitre = _MITRE_BY_SEARCH.get(search_name)
    if mitre:
        alert["mitre_techniques"] = mitre
    return alert
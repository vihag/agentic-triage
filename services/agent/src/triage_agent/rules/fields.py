"""Pure accessors over an Alert mapping and a TriageContext. No I/O."""

from __future__ import annotations

import ipaddress
from collections.abc import Mapping, Sequence
from typing import Any

from triage_agent.contract import TriageContext


def strings(value: object) -> list[str]:
    """Normalise an entity field to non-empty strings. Non-strings are dropped."""
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, (bytes, bytearray)) or not isinstance(value, Sequence):
        return []
    found: list[str] = []
    for item in value:
        if isinstance(item, str):
            text = item.strip()
            if text:
                found.append(text)
    return found


def _mapping(value: object) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}


def search_name(alert: Mapping[str, Any]) -> str:
    name = _mapping(alert.get("source")).get("search_name")
    return name if isinstance(name, str) else ""


def title_text(alert: Mapping[str, Any]) -> str:
    title = alert.get("title")
    return title if isinstance(title, str) else ""


def description_text(alert: Mapping[str, Any]) -> str:
    description = alert.get("description")
    return description if isinstance(description, str) else ""


def raw_result(alert: Mapping[str, Any]) -> Mapping[str, Any]:
    return _mapping(_mapping(alert.get("raw")).get("result"))


def _entity_or_raw(
    alert: Mapping[str, Any], entity_key: str, raw_keys: tuple[str, ...]
) -> list[str]:
    values = strings(_mapping(alert.get("entities")).get(entity_key))
    if values:
        return values
    result = raw_result(alert)
    for key in raw_keys:
        values = strings(result.get(key))
        if values:
            return values
    return []


def users_of(alert: Mapping[str, Any]) -> list[str]:
    return _entity_or_raw(alert, "users", ("user", "users"))


def src_ips_of(alert: Mapping[str, Any]) -> list[str]:
    return _entity_or_raw(alert, "src_ips", ("src_ip", "src_ips"))


def dest_ips_of(alert: Mapping[str, Any]) -> list[str]:
    return _entity_or_raw(alert, "dest_ips", ("dest_ip", "dest_ips"))


def hosts_of(alert: Mapping[str, Any]) -> list[str]:
    return _entity_or_raw(alert, "hosts", ("host", "hosts"))


def domains_of(alert: Mapping[str, Any]) -> list[str]:
    return _entity_or_raw(alert, "domains", ("domain", "domains"))


def file_hashes_of(alert: Mapping[str, Any]) -> list[str]:
    hashes = _entity_or_raw(alert, "file_hashes", ("file_hash", "file_hashes", "hash"))
    return [item.lower() for item in hashes]


def signature_of(alert: Mapping[str, Any]) -> str:
    result = raw_result(alert)
    parts: list[str] = []
    for key in ("signature", "signature_id", "threat_name"):
        value = result.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(value.strip())
    return " ".join(parts)


def as_int(value: object) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if value.is_integer():
            return int(value)
        return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return int(text)
        except ValueError:
            return None
    return None


def failure_success_counts(alert: Mapping[str, Any]) -> tuple[int | None, int | None]:
    result = raw_result(alert)
    return as_int(result.get("failed_count")), as_int(result.get("success_count"))


def window_minutes(alert: Mapping[str, Any]) -> int | None:
    result = raw_result(alert)
    for key in ("window_minutes", "window_min"):
        if key in result:
            return as_int(result.get(key))
    return None


def allow_values(ctx: TriageContext, *names: str) -> list[str]:
    found: list[str] = []
    for name in names:
        found.extend(strings(ctx.allow_lists.get(name)))
    return found


def lookup_record(table: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    direct = table.get(key)
    if isinstance(direct, Mapping):
        return direct
    lowered = key.lower()
    for candidate, record in table.items():
        if str(candidate).lower() == lowered and isinstance(record, Mapping):
            return record
    return {}


def host_record(ctx: TriageContext, host: str) -> Mapping[str, Any]:
    return lookup_record(ctx.asset_inventory, host)


def identity_record(ctx: TriageContext, user: str) -> Mapping[str, Any]:
    return lookup_record(ctx.identity_directory, user)


def flag_is_true(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return False


def ip_in_list(ip: str, patterns: Sequence[str]) -> bool:
    candidate = ip.strip()
    try:
        address = ipaddress.ip_address(candidate)
    except ValueError:
        address = None
    for pattern in patterns:
        text = pattern.strip()
        if candidate.lower() == text.lower():
            return True
        if address is None or "/" not in text:
            continue
        try:
            network = ipaddress.ip_network(text, strict=False)
        except ValueError:
            continue
        if address in network:
            return True
    return False

"""Process settings. Defaults match .env.example so the compose stack boots."""

from __future__ import annotations

import json
import os
import secrets
from dataclasses import dataclass

DEFAULT_JWT_SECRET = "local-dev-jwt-secret"
DEFAULT_JWT_ISSUER = "agentic-triage-dev"
DEFAULT_JWT_AUDIENCE = "agentic-triage-api"
DEFAULT_SPLUNK_TOKEN = "local-dev-splunk-webhook-token"
DEFAULT_BOT_KEY = "local-dev-grok-bot-key"
DEFAULT_BOT_ID = "grok-bot-demo"
DEFAULT_ON_BEHALF_OF = "analyst-demo"


@dataclass(frozen=True)
class BotIdentity:
    bot_id: str
    on_behalf_of: str


class BotKeyRegistry:
    """Maps an X-GrokBot-Key value to {bot_id, on_behalf_of}.

    T16 replaces this with a revocable store. GROK_BOT_KEYS, when set, is the
    whole map. Otherwise one key is taken from GROK_BOT_API_KEY.
    """

    def __init__(self, keys: dict[str, BotIdentity]) -> None:
        if not keys:
            raise ValueError("at least one bot API key is required")
        for key, identity in keys.items():
            if not key or not identity.bot_id or not identity.on_behalf_of:
                raise ValueError("bot key, bot_id, and on_behalf_of must be non-empty")
        self._keys = dict(keys)

    def resolve(self, presented: str) -> BotIdentity | None:
        if presented == "":
            return None
        matched: BotIdentity | None = None
        presented_bytes = presented.encode()
        for key, identity in self._keys.items():
            if secrets.compare_digest(presented_bytes, key.encode()):
                matched = identity
        return matched


@dataclass(frozen=True)
class Settings:
    jwt_secret: str
    jwt_issuer: str
    jwt_audience: str
    splunk_webhook_token: str
    bot_keys: BotKeyRegistry


def build_settings(
    *,
    jwt_secret: str = DEFAULT_JWT_SECRET,
    jwt_issuer: str = DEFAULT_JWT_ISSUER,
    jwt_audience: str = DEFAULT_JWT_AUDIENCE,
    splunk_webhook_token: str = DEFAULT_SPLUNK_TOKEN,
    bot_keys: dict[str, tuple[str, str]] | None = None,
) -> Settings:
    if not jwt_secret or not jwt_issuer or not jwt_audience or not splunk_webhook_token:
        raise ValueError("jwt secret, issuer, audience, and splunk token must be non-empty")
    mapping = bot_keys if bot_keys is not None else {DEFAULT_BOT_KEY: (DEFAULT_BOT_ID, DEFAULT_ON_BEHALF_OF)}
    registry = BotKeyRegistry(
        {
            key: BotIdentity(bot_id=bot_id, on_behalf_of=analyst_id)
            for key, (bot_id, analyst_id) in mapping.items()
        }
    )
    return Settings(
        jwt_secret=jwt_secret,
        jwt_issuer=jwt_issuer,
        jwt_audience=jwt_audience,
        splunk_webhook_token=splunk_webhook_token,
        bot_keys=registry,
    )


def _env(name: str, default: str) -> str:
    value = os.environ.get(name, default)
    if value == "":
        raise RuntimeError(f"{name} must not be empty")
    return value


def _bot_keys_from_env() -> dict[str, tuple[str, str]]:
    raw = os.environ.get("GROK_BOT_KEYS")
    if not raw:
        return {
            _env("GROK_BOT_API_KEY", DEFAULT_BOT_KEY): (
                _env("GROK_BOT_ID", DEFAULT_BOT_ID),
                _env("GROK_BOT_ON_BEHALF_OF", DEFAULT_ON_BEHALF_OF),
            )
        }
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("GROK_BOT_KEYS must be a JSON object")
    keys: dict[str, tuple[str, str]] = {}
    for key, value in parsed.items():
        if not isinstance(key, str) or not isinstance(value, dict):
            raise ValueError("GROK_BOT_KEYS entries must be objects")
        bot_id = value.get("bot_id")
        on_behalf_of = value.get("on_behalf_of")
        if not isinstance(bot_id, str) or not isinstance(on_behalf_of, str):
            raise ValueError("GROK_BOT_KEYS values need string bot_id and on_behalf_of")
        keys[key] = (bot_id, on_behalf_of)
    return keys


def load_settings() -> Settings:
    return build_settings(
        jwt_secret=_env("JWT_SECRET", DEFAULT_JWT_SECRET),
        jwt_issuer=_env("JWT_ISSUER", DEFAULT_JWT_ISSUER),
        jwt_audience=_env("JWT_AUDIENCE", DEFAULT_JWT_AUDIENCE),
        splunk_webhook_token=_env("SPLUNK_WEBHOOK_TOKEN", DEFAULT_SPLUNK_TOKEN),
        bot_keys=_bot_keys_from_env(),
    )

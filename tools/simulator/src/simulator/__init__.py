"""Splunk alert simulator.

``simulator send <scenario>`` posts a webhook whose body is the scenario file
(or, for burst, that file with a new sid) to the triage ingest URL.
"""

from simulator.library import (
    BURST_RECIPE,
    BURST_SIZE,
    SCENARIOS,
    Scenario,
    WebhookMessage,
    iter_messages,
    known_names,
    resolve_scenario,
)

__version__ = "0.1.0"

__all__ = [
    "BURST_RECIPE",
    "BURST_SIZE",
    "SCENARIOS",
    "Scenario",
    "WebhookMessage",
    "__version__",
    "iter_messages",
    "known_names",
    "resolve_scenario",
]

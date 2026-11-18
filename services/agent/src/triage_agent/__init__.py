"""In-process triage agent library.

T09 owns rule discovery and the starter rules. T10 owns the fuzzy matcher.
T11 owns severity combination, routing, and TriageDecision. Pack builders
stay behind the same contract.
"""

from triage_agent.agent import DefaultTriageAgent
from triage_agent.contract import TriageContext
from triage_agent.engine import RuleEngine
from triage_agent.loader import discover_rules
from triage_agent.routing import RoutingConfig
from triage_agent.version import __version__

__all__ = [
    "DefaultTriageAgent",
    "RoutingConfig",
    "RuleEngine",
    "TriageContext",
    "__version__",
    "discover_rules",
]

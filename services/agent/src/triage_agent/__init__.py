"""In-process triage agent library.

T09 owns rule discovery and the starter rules. T10 owns the fuzzy matcher.
T11 owns severity combination, routing, and TriageDecision. Pack builders
stay behind the same contract.

Importing this package must not import SQLAlchemy. pytest-cov loads the
parent package while its tracer is still starting, and SQLAlchemy 2.1's
Cython cache-key module mis-initialises under that tracer. The agent and
routing modules import the fuzzy package, which imports SQLAlchemy, so they
are not re-exported here.
"""

from triage_agent.contract import TriageContext
from triage_agent.engine import RuleEngine
from triage_agent.loader import discover_rules
from triage_agent.version import __version__

__all__ = [
    "RuleEngine",
    "TriageContext",
    "__version__",
    "discover_rules",
]

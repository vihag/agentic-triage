"""In-process triage agent library.

T09 owns rule discovery and the starter rules. Later tickets add the fuzzy
matcher, severity routing, and pack builders behind the same contract.
"""

from triage_agent.contract import TriageContext
from triage_agent.engine import RuleEngine
from triage_agent.loader import discover_rules

__all__ = ["RuleEngine", "TriageContext", "discover_rules"]
__version__ = "0.1.0"

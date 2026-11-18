"""Package version. Recorded on every TriageDecision as ``agent_version``."""

__version__ = "0.1.0"


def agent_version() -> str:
    return f"triage-agent/{__version__}"

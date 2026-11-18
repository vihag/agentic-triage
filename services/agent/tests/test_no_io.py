"""Rules stay pure: the source may not import I/O, and evaluate may not open anything."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

from triage_agent.contract import TriageContext
from triage_agent.engine import RuleEngine

RULES = Path(__file__).resolve().parents[1] / "src" / "triage_agent" / "rules"
ALLOWED_ROOTS = {
    "__future__",
    "collections",
    "ipaddress",
    "re",
    "typing",
    "triage_agent",
}
FORBIDDEN_CALLS = {"open", "input", "print", "getattr", "eval", "exec", "__import__"}
FORBIDDEN_ATTRS = {
    "read_text",
    "read_bytes",
    "write_text",
    "write_bytes",
    "urlopen",
    "system",
    "popen",
    "connect",
}


def _violations(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0]
                if root not in ALLOWED_ROOTS:
                    found.append(f"{path.name}:{node.lineno} import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                found.append(f"{path.name}:{node.lineno} relative import")
            module = node.module or ""
            root = module.split(".", 1)[0]
            if root not in ALLOWED_ROOTS:
                found.append(f"{path.name}:{node.lineno} from {module}")
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in FORBIDDEN_CALLS:
                found.append(f"{path.name}:{node.lineno} call {func.id}")
            elif isinstance(func, ast.Attribute) and func.attr in FORBIDDEN_ATTRS:
                found.append(f"{path.name}:{node.lineno} call .{func.attr}")
    return found


def test_rule_sources_have_no_io_imports_or_calls() -> None:
    files = sorted(RULES.glob("*.py"))
    assert files
    violations = [item for path in files for item in _violations(path)]
    assert violations == []


def test_evaluate_does_not_open_files_or_sockets() -> None:
    engine = RuleEngine()
    seen: list[str] = []
    active = True

    def hook(event: str, args: tuple[object, ...]) -> None:
        if active and event in {"open", "socket.connect", "subprocess.Popen"}:
            seen.append(event)

    sys.addaudithook(hook)
    try:
        engine.run(
            {
                "title": "TOR egress after failed login success",
                "source": {"search_name": "Excessive Failed Logins Followed By Success"},
                "entities": {
                    "users": ["root"],
                    "src_ips": ["203.0.113.45"],
                    "dest_ips": ["185.220.101.1"],
                    "hosts": ["crown-db"],
                    "file_hashes": [
                        "275a021bbfb6489e54d471899f7db9d1663fc695ec2fe2a2c4538aabf651fd0f"
                    ],
                },
                "raw": {
                    "result": {
                        "failed_count": "4",
                        "success_count": "1",
                        "signature": "EICAR-Test-File",
                    }
                },
            },
            TriageContext(
                asset_inventory={"crown-db": {"crown_jewel": True, "group": "ci-build-agents"}},
                identity_directory={"root": {"privileged": True}},
                allow_lists={
                    "scanners": ["203.0.113.45"],
                    "tor_exit_nodes": ["185.220.101.1"],
                },
            ),
        )
    finally:
        active = False
    assert seen == []

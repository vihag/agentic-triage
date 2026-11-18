#!/usr/bin/env python3
"""Contract gate: run locally (`make contracts`) and in CI.

Checks
  1. Every JSON Schema in contracts/schemas is a valid Draft 2020-12 schema.
  2. Every example in contracts/examples validates against its schema.
     Naming: <schema>[.<DefName>].<variant>.json  -> contracts/schemas/<schema>.schema.json
             (a capitalised second segment targets  #/$defs/<DefName>)
  3. Every example in contracts/examples/invalid FAILS validation (negative tests
     that pin down invariants, e.g. a Grok Bot can never be an approver).
  4. contracts/openapi.yaml is a valid OpenAPI 3.1 document with all $refs
     (including the external JSON Schemas) resolvable, plus house lint rules.
  5. contracts/agent/interfaces.py imports cleanly (the agent's Python contract).
  6. plan/issues.json is in sync with plan/tickets.yaml.
Exit code 0 = all good.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from openapi_spec_validator import validate as validate_openapi
from openapi_spec_validator.readers import read_from_filename
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "contracts" / "schemas"
EXAMPLES = ROOT / "contracts" / "examples"
OPENAPI = ROOT / "contracts" / "openapi.yaml"

failures: list[str] = []
passes = 0


def ok(msg: str) -> None:
    global passes
    passes += 1
    print(f"  PASS  {msg}")


def fail(msg: str) -> None:
    failures.append(msg)
    print(f"  FAIL  {msg}")


def load_registry() -> tuple[Registry, dict[str, dict]]:
    schemas: dict[str, dict] = {}
    registry = Registry()
    for path in sorted(SCHEMAS.glob("*.schema.json")):
        contents = json.loads(path.read_text())
        schemas[path.name] = contents
        res = Resource.from_contents(contents, default_specification=DRAFT202012)
        # Register under the bare filename (how schemas $ref each other) and file URI.
        registry = registry.with_resource(path.name, res).with_resource(path.as_uri(), res)
    return registry, schemas


def validator_for(example: Path, registry: Registry, schemas: dict[str, dict]):
    parts = example.name.split(".")
    schema_file = f"{parts[0]}.schema.json"
    if schema_file not in schemas:
        raise KeyError(f"no schema {schema_file} for example {example.name}")
    schema = schemas[schema_file]
    target = schema
    if len(parts) > 2 and parts[1][:1].isupper():
        target = {"$ref": f"{schema_file}#/$defs/{parts[1]}"}
    return Draft202012Validator(target, registry=registry, format_checker=FormatChecker()), schema_file


def check_schemas(schemas: dict[str, dict]) -> None:
    print("\n[1] JSON Schemas are valid Draft 2020-12")
    for name, s in schemas.items():
        try:
            Draft202012Validator.check_schema(s)
            ok(name)
        except Exception as e:  # noqa: BLE001
            fail(f"{name}: {e}")


def check_examples(registry, schemas) -> None:
    print("\n[2] Examples validate against their schemas")
    covered = set()
    for ex in sorted(EXAMPLES.glob("*.json")):
        try:
            v, sf = validator_for(ex, registry, schemas)
            errs = sorted(v.iter_errors(json.loads(ex.read_text())), key=lambda e: list(e.path))
            covered.add(sf)
            if errs:
                fail(f"{ex.name} -> {sf}: " + "; ".join(f"{list(e.path)}: {e.message}" for e in errs[:5]))
            else:
                ok(f"{ex.name} -> {sf}")
        except Exception as e:  # noqa: BLE001
            fail(f"{ex.name}: {e}")
    required = {"alert", "triage-decision", "evidence-pack", "next-steps-pack", "case", "audit-event", "action", "splunk-webhook"}
    missing = {f"{r}.schema.json" for r in required} - covered
    if missing:
        fail(f"schemas with no positive example: {sorted(missing)}")
    else:
        ok("every top-level schema has at least one positive example")

    print("\n[3] Invalid examples are rejected")
    for ex in sorted((EXAMPLES / "invalid").glob("*.json")):
        try:
            v, sf = validator_for(ex, registry, schemas)
            errs = list(v.iter_errors(json.loads(ex.read_text())))
            if errs:
                ok(f"invalid/{ex.name} rejected ({errs[0].message[:70]})")
            else:
                fail(f"invalid/{ex.name} unexpectedly VALID against {sf}")
        except Exception as e:  # noqa: BLE001
            fail(f"invalid/{ex.name}: {e}")


def check_openapi() -> None:
    print("\n[4] OpenAPI 3.1 spec")
    try:
        spec, base_uri = read_from_filename(str(OPENAPI))
        validate_openapi(spec, base_uri=base_uri)
        ok("openapi.yaml is valid OpenAPI 3.1 (external $refs resolved)")
    except Exception as e:  # noqa: BLE001
        fail(f"openapi.yaml: {e}")
        return
    # House lint rules
    op_ids = set()
    for path, item in spec["paths"].items():
        for method, op in item.items():
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            oid = op.get("operationId")
            if not oid:
                fail(f"{method.upper()} {path}: missing operationId")
            elif oid in op_ids:
                fail(f"duplicate operationId {oid}")
            op_ids.add(oid)
            if not op.get("tags"):
                fail(f"{oid}: missing tags")
            if path.startswith("/v1/bot/") and op.get("security") != [{"botApiKey": []}]:
                fail(f"{oid}: bot endpoints must use botApiKey only")
            if oid in {"approveAction", "rejectAction"} and op.get("security") != [{"analystAuth": []}]:
                fail(f"{oid}: approval must be analystAuth only (human-in-the-loop invariant)")
            if not path.startswith("/v1/"):
                fail(f"{path}: must be versioned under /v1/")
    ok(f"lint: {len(op_ids)} operations have unique operationIds, tags, /v1 prefix")
    ok("lint: approve/reject are analystAuth-only; /v1/bot/* are botApiKey-only")


def check_agent_interfaces() -> None:
    print("\n[5] Agent interface module")
    path = ROOT / "contracts" / "agent" / "interfaces.py"
    try:
        spec = importlib.util.spec_from_file_location("agent_interfaces", path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules["agent_interfaces"] = mod
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        for name in ("RulePlugin", "FuzzyMatcher", "LLMClient", "TriageAgent", "RoutingPolicy"):
            assert hasattr(mod, name), f"missing {name}"
        # The mock implementations must satisfy the protocols at runtime.
        assert isinstance(mod.MockFuzzyMatcher(), mod.FuzzyMatcher)
        assert isinstance(mod.MockLLMClient(), mod.LLMClient)
        ok("interfaces.py imports; protocols present; mocks satisfy FuzzyMatcher/LLMClient")
        # Routing policy table matches ADR-0005.
        p = mod.DefaultRoutingPolicy()
        cases = [
            (("medium", "high", 0.8, False), "enqueue_for_triage"),
            (("high", "low", 0.95, False), "auto_closed"),
            (("high", "low", 0.60, False), "enqueue_downgrade_review"),
            (("high", "low", 0.95, True), "enqueue_downgrade_review"),
            (("high", "high", 0.7, False), "enqueue_for_triage"),
            (("low", "low", 0.7, False), "recorded_only"),
        ]
        for (orig, final, conf, never), want in cases:
            got = p.route(orig, final, conf, never_auto_close=never)
            if got != want:
                fail(f"routing {orig}->{final} conf={conf} never={never}: got {got}, want {want}")
        ok(f"DefaultRoutingPolicy matches ADR-0005 table ({len(cases)} cases)")
        # combine_severity + routing reproduce the example decisions end to end.
        for ex in sorted(EXAMPLES.glob("triage-decision.*.json")):
            d = json.loads(ex.read_text())
            rules = [mod.RuleResult(r["rule_id"], r["rule_version"], r["matched"],
                                    mod.SeverityEffect(r["effect"]["op"], r["effect"].get("severity"), r["effect"].get("delta", 0)),
                                    r["rationale"]) for r in d["rule_results"]]
            fz = d["fuzzy_result"]
            fuzzy = None if fz is None else mod.FuzzyMatchResult(fz["matcher_id"], fz["model"], (), fz["suggested_severity"], fz["confidence"], fz["rationale"])
            final = mod.combine_severity(d["original_severity"], rules, fuzzy)
            never = any(r.matched and r.effect.op == "never_auto_close" for r in rules) or fuzzy is None
            disp = p.route(d["original_severity"], final, d["confidence"], never_auto_close=never)
            if (final, disp) != (d["final_severity"], d["disposition"]):
                fail(f"{ex.name}: combine/route gives {final}/{disp}, example says {d['final_severity']}/{d['disposition']}")
            else:
                ok(f"{ex.name}: combine_severity+route reproduce {final}/{disp}")
    except Exception as e:  # noqa: BLE001
        fail(f"interfaces.py: {e!r}")


def check_issues() -> None:
    print("\n[6] plan/issues.json in sync with plan/tickets.yaml")
    try:
        sys.path.insert(0, str(ROOT / "scripts"))
        import gen_issues  # type: ignore

        expected = gen_issues.build_issues()
        actual = json.loads((ROOT / "plan" / "issues.json").read_text())
        if expected != actual:
            fail("plan/issues.json is stale; run scripts/gen_issues.py")
        else:
            ok(f"{len(actual)} issues in sync")
    except Exception as e:  # noqa: BLE001
        fail(f"issues: {e!r}")


def main() -> int:
    registry, schemas = load_registry()
    check_schemas(schemas)
    check_examples(registry, schemas)
    check_openapi()
    check_agent_interfaces()
    check_issues()
    print(f"\n{passes} passed, {len(failures)} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

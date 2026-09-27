"""Spec validator and activator (guide §5.13)."""

import argparse
import json
import os
import sys
import tempfile


def _load_all(root: str):
    """Load rules.json, adapters, kind-buckets, config from root."""
    from stickler.util import read_json
    stickler_dir = os.path.join(root, ".stickler")
    rules_path = os.path.join(root, "stickler", "rules.json")
    doc = read_json(rules_path)
    adapters = read_json(os.path.join(stickler_dir, "adapters.json"))
    kb = read_json(os.path.join(stickler_dir, "kind-buckets.json"))
    config = read_json(os.path.join(stickler_dir, "config.json"))
    return doc, adapters, kb, config


def _run_validation(root: str):
    """Run --run: validate all rules and run their cases. Returns validation dict."""
    from stickler.util import (read_json, write_json_atomic, now_utc,
                                sha256_bytes, canonical, append_jsonl)
    from stickler.spec import validate_all, validate_rule
    from stickler.policy import evaluate_pre_tool, evaluate_final_state

    doc, adapters, kb, config = _load_all(root)
    limits = config.get("limits", {})
    kind_buckets = kb.get("kind_buckets", {})

    errors = validate_all(doc, root, adapters, kind_buckets, limits)

    history_path = os.path.join(root, "stickler", "validation-history.jsonl")
    validation_rules = {}
    ts = now_utc()

    for rule in doc.get("rules", []):
        rid = rule.get("id", "")
        schema_errors = errors.get(rid, [])
        schema_valid = len(schema_errors) == 0

        rule_sha = sha256_bytes(canonical(rule))
        cases_passed = 0
        cases_failed = 0

        if schema_valid and rule.get("bucket") in ("block", "audit"):
            # Run cases against this rule alone
            for case in rule.get("cases", []):
                try:
                    if case.get("type") == "pre_tool":
                        tool = case.get("tool", "")
                        inp = case.get("input", {})
                        with tempfile.TemporaryDirectory() as tmpdir:
                            import subprocess
                            subprocess.run(["git", "init", "-q", tmpdir], check=True)
                            result = evaluate_pre_tool(
                                tool, inp, [rule], adapters, config, tmpdir, tmpdir
                            )
                        expected = case.get("expect", "allow")
                        if result["decision"] == expected:
                            cases_passed += 1
                        else:
                            cases_failed += 1
                    elif case.get("type") == "final_state":
                        result = evaluate_final_state(
                            case.get("baseline", {}),
                            case.get("final", {}),
                            [rule],
                            config,
                        )
                        expected = case.get("expect", "clean")
                        has_finding = len(result["findings"]) > 0
                        actual = "finding" if has_finding else "clean"
                        if actual == expected:
                            cases_passed += 1
                        else:
                            cases_failed += 1
                except Exception as exc:
                    cases_failed += 1

        # Append to history
        history_entry = {
            "rule_id": rid,
            "rule_sha256": rule_sha,
            "schema_valid": schema_valid,
            "cases_passed": cases_passed,
            "cases_failed": cases_failed,
            "ts": ts,
        }
        append_jsonl(history_path, history_entry)
        validation_rules[rid] = {
            "schema_valid": schema_valid,
            "schema_errors": schema_errors,
            "cases_passed": cases_passed,
            "cases_failed": cases_failed,
            "rule_sha256": rule_sha,
            "ts": ts,
        }

    return doc, validation_rules, history_path


def _load_history(history_path: str) -> dict:
    """Load all history entries. Returns {rid: [entries]}."""
    result = {}
    if not os.path.isfile(history_path):
        return result
    with open(history_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                rid = entry.get("rule_id", "")
                result.setdefault(rid, []).append(entry)
            except json.JSONDecodeError:
                pass
    return result


def _compute_validation_json(doc: dict, validation_rules: dict, history_path: str,
                              root: str) -> dict:
    """Build the full validation.json structure."""
    from stickler.util import read_json
    from stickler.routes import route_matrix as _route_matrix
    from stickler.util import sha256_bytes, canonical

    stickler_dir = os.path.join(root, ".stickler")
    try:
        adapters = read_json(os.path.join(stickler_dir, "adapters.json"))
        kb = read_json(os.path.join(stickler_dir, "kind-buckets.json"))
        matrix = _route_matrix(adapters)
    except Exception:
        matrix = {}

    history = _load_history(history_path)

    rules_out = {}
    totals = {"total": 0, "validated": 0, "failed": 0, "judgment": 0,
              "duplicate": 0, "conflict": 0}
    all_ids = {r["id"] for r in doc.get("rules", [])}

    for rule in doc.get("rules", []):
        rid = rule.get("id", "")
        bucket = rule.get("bucket")
        jr = rule.get("judgment_reason")
        totals["total"] += 1

        vr = validation_rules.get(rid, {})
        schema_valid = vr.get("schema_valid", False)
        schema_errors = vr.get("schema_errors", [])
        cases_passed = vr.get("cases_passed", 0)
        cases_failed = vr.get("cases_failed", 0)

        # Compute generated_tests from history
        hist_entries = history.get(rid, [])
        first_entry = hist_entries[0] if hist_entries else None
        current_entry = hist_entries[-1] if hist_entries else None
        distinct_shas = len({e.get("rule_sha256") for e in hist_entries})
        repairs = max(0, distinct_shas - 1)

        generated = {
            "first": {"passed": first_entry["cases_passed"] if first_entry else 0,
                      "failed": first_entry["cases_failed"] if first_entry else 0},
            "current": {"passed": cases_passed, "failed": cases_failed},
            "repairs": repairs,
        }

        # Status
        if rule.get("duplicate_of"):
            status = "duplicate"
            totals["duplicate"] += 1
        elif rule.get("conflicts_with"):
            status = "conflict"
            totals["conflict"] += 1
        elif bucket == "judgment":
            status = "judgment"
            totals["judgment"] += 1
        elif not schema_valid:
            status = "failed"
            totals["failed"] += 1
        elif cases_failed > 0:
            status = "failed"
            totals["failed"] += 1
        elif repairs > 2:
            status = "repair_limit_exceeded"
            totals["failed"] += 1
        else:
            status = "validated"
            totals["validated"] += 1

        # Routes from matrix
        check = rule.get("check") or {}
        kind = check.get("kind", "")
        routes = {}
        if kind and kind in matrix:
            routes = {tool: info for tool, info in matrix[kind].items()}

        rules_out[rid] = {
            "bucket": bucket,
            "judgment_reason": jr,
            "schema_valid": schema_valid,
            "schema_errors": schema_errors,
            "generated_tests": generated,
            "status": status,
            "routes": routes,
            "installed": None,  # filled by --report
        }

    return {"rules": rules_out, "totals": totals}


def _activate_rules(root: str, doc: dict, validation_json: dict) -> list:
    """Select and activate validated rules. Returns list of activated IDs."""
    from stickler.util import (sha256_bytes, canonical, sha256_file,
                                write_json_atomic, now_utc, digest_engine, read_json)

    stickler_dir = os.path.join(root, ".stickler")
    config = read_json(os.path.join(stickler_dir, "config.json"))

    activated = []
    for rule in doc.get("rules", []):
        rid = rule.get("id", "")
        vr = validation_json["rules"].get(rid, {})
        if vr.get("status") != "validated":
            continue
        activated.append(rule)

    # Builtin for governed mode
    control_globs = (config.get("control_globs", []) +
                     config.get("engine_owned_globs", []))
    builtin = [{
        "id": "builtin:control-files",
        "bucket": "block",
        "check": {"kind": "deny_path", "globs": control_globs},
        "text": "Control files are protected",
        "source": {"path": "", "start_line": 0, "end_line": 0, "quote": ""},
        "judgment_reason": None, "cases": [],
    }]

    snapshot = {"rules": activated, "builtin": builtin}
    snap_bytes = canonical(snapshot)
    sha = sha256_bytes(snap_bytes)

    active_dir = os.path.join(stickler_dir, "active")
    os.makedirs(active_dir, exist_ok=True)
    snap_path = os.path.join(active_dir, f"rules.{sha}.json")
    with open(snap_path, "wb") as fh:
        fh.write(snap_bytes)

    engine_dir = os.path.join(stickler_dir, "engine", "stickler")
    engine_sha = digest_engine(engine_dir) if os.path.isdir(engine_dir) else ""

    def _sha(name):
        p = os.path.join(stickler_dir, name)
        return sha256_file(p) if os.path.isfile(p) else ""

    pointer = {
        "rules_sha256": sha,
        "engine_sha256": engine_sha,
        "adapters_sha256": _sha("adapters.json"),
        "kind_buckets_sha256": _sha("kind-buckets.json"),
        "config_sha256": _sha("config.json"),
        "activated": [r["id"] for r in activated],
        "excluded": [{"id": rid, "reason": "; ".join(vr.get("schema_errors", []))}
                     for rid, vr in validation_json["rules"].items()
                     if vr.get("status") == "failed"],
        "activated_at": now_utc(),
    }
    write_json_atomic(os.path.join(stickler_dir, "active.json"), pointer)
    return [r["id"] for r in activated]


def main():
    parser = argparse.ArgumentParser(description="Stickler validator")
    parser.add_argument("--root", required=True)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--run", action="store_true", default=True)
    group.add_argument("--report", action="store_true")
    group.add_argument("--check", action="store_true")
    group.add_argument("--trace", action="store_true")
    args = parser.parse_args()

    from stickler.util import read_json, write_json_atomic

    # Resolve mode flags
    if args.trace:
        _do_trace(args.root)
        return
    if args.check:
        _do_check(args.root)
        return
    if args.report:
        _do_report(args.root)
        return
    # Default: --run
    _do_run(args.root)


def _do_run(root: str):
    from stickler.util import write_json_atomic

    doc, validation_rules, history_path = _run_validation(root)
    val_json = _compute_validation_json(doc, validation_rules, history_path, root)

    val_path = os.path.join(root, "stickler", "validation.json")
    write_json_atomic(val_path, val_json)

    # Print failures
    failed = [(rid, vr) for rid, vr in val_json["rules"].items()
              if vr["status"] == "failed"]
    for rid, vr in failed:
        errs = vr.get("schema_errors") or []
        if vr["generated_tests"]["current"]["failed"]:
            errs = errs + [f"{vr['generated_tests']['current']['failed']} case(s) failed"]
        print(f"FAIL {rid}: {'; '.join(errs)}")

    t = val_json["totals"]
    print(f"Totals: {t['total']} rules, {t['validated']} validated, "
          f"{t['failed']} failed, {t['judgment']} judgment")


def _do_report(root: str):
    from stickler.util import write_json_atomic
    from stickler.report import render_rules_report

    doc, validation_rules, history_path = _run_validation(root)
    val_json = _compute_validation_json(doc, validation_rules, history_path, root)

    activated_ids = _activate_rules(root, doc, val_json)

    # Mark installed in validation.json
    for rid in val_json["rules"]:
        val_json["rules"][rid]["installed"] = rid in activated_ids

    val_path = os.path.join(root, "stickler", "validation.json")
    write_json_atomic(val_path, val_json)

    md = render_rules_report(doc, val_json, activated_ids)
    report_path = os.path.join(root, "stickler", "REPORT.md")
    with open(report_path, "w", encoding="utf-8") as fh:
        fh.write(md)

    print(f"Activated {len(activated_ids)} rules. Report: {report_path}")


def _do_check(root: str):
    """Recompute and compare with committed validation.json (no timestamps)."""
    from stickler.util import read_json, write_json_atomic
    import copy

    committed_path = os.path.join(root, "stickler", "validation.json")
    if not os.path.isfile(committed_path):
        print("No committed validation.json")
        sys.exit(1)
    committed = read_json(committed_path)

    doc, validation_rules, history_path = _run_validation(root)
    fresh = _compute_validation_json(doc, validation_rules, history_path, root)

    def _strip_ts(obj):
        """Remove ts and activated_at fields for comparison."""
        if isinstance(obj, dict):
            return {k: _strip_ts(v) for k, v in obj.items()
                    if k not in ("ts", "activated_at", "installed")}
        if isinstance(obj, list):
            return [_strip_ts(i) for i in obj]
        return obj

    c = _strip_ts(committed)
    f = _strip_ts(fresh)

    if c != f:
        import difflib
        ca = json.dumps(c, sort_keys=True, indent=2).splitlines()
        fa = json.dumps(f, sort_keys=True, indent=2).splitlines()
        diff = "\n".join(list(difflib.unified_diff(ca, fa, lineterm=""))[:40])
        print(f"validation.json mismatch:\n{diff}")
        sys.exit(1)
    print("validation.json: OK")


def _do_trace(root: str):
    """Verify traceability: unique ids, one bucket, verbatim quote in span."""
    from stickler.util import read_json

    rules_path = os.path.join(root, "stickler", "rules.json")
    doc = read_json(rules_path)
    rules = doc.get("rules", [])
    seen_ids = set()
    failures = []

    def _collapse(s):
        return " ".join(s.split())

    for rule in rules:
        rid = rule.get("id", "")
        if rid in seen_ids:
            failures.append(f"duplicate id: {rid}")
        seen_ids.add(rid)

        if rule.get("bucket") not in ("block", "audit", "judgment"):
            failures.append(f"{rid}: missing/invalid bucket")

        src = rule.get("source", {})
        src_path = src.get("path", "")
        quote = src.get("quote", "")
        sl = src.get("start_line", 0)
        el = src.get("end_line", 0)
        if src_path:
            abs_path = os.path.join(root, src_path)
            try:
                lines = open(abs_path, encoding="utf-8").readlines()
                span = "".join(lines[sl - 1: el]) if 1 <= sl <= el <= len(lines) else ""
                if quote and _collapse(quote) not in _collapse(span):
                    failures.append(f"{rid}: quote not in span")
            except OSError:
                pass

    if failures:
        for f in failures:
            print(f"TRACE FAIL: {f}")
        sys.exit(1)
    print("trace: OK")


if __name__ == "__main__":
    main()

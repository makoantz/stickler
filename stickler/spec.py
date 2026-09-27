"""Rule loading and validation (guide §5.4, §3.5, §3.6)."""

import re

from stickler.globs import glob_to_regex
from stickler.regexrun import run_patterns

_VALID_BUCKETS = {"block", "audit", "judgment"}
_VALID_JUDGMENT_REASONS = {"human", "mechanical_unsupported", "duplicate", "conflict"}
_VALID_KINDS = {
    "deny_path", "allow_paths_only", "forbid_file_deletion",
    "deny_command", "require_paired_change", "deny_diff_pattern",
}
_KIND_PARAMS = {
    "deny_path": {"globs"},
    "allow_paths_only": {"globs"},
    "forbid_file_deletion": {"globs"},
    "deny_command": {"patterns"},
    "require_paired_change": {"when_changed", "require_changed"},
    "deny_diff_pattern": {"globs", "patterns"},
}
_ID_RE = re.compile(r"^[a-z0-9-]+:[0-9]+:[0-9]+$")

# Stress inputs for pattern screening (§3.6)
_STRESS = ["a" * 5000 + "!", "/" * 5000, " " * 5000 + "x", "ab" * 2500]


def load_rules(path: str) -> dict:
    import json
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _collapse_ws(s: str) -> str:
    return " ".join(s.split())


def screen_pattern(p: str, limits: dict):
    """Return an error string if the pattern is rejected per §3.6, else None."""
    if len(p) > limits["max_pattern_len"]:
        return f"pattern too long ({len(p)} > {limits['max_pattern_len']})"
    try:
        re.compile(p)
    except re.error as exc:
        return f"invalid regex: {exc}"

    # Backreferences
    if re.search(r"\\[1-9]|\(\?P=", p):
        return "pattern contains a backreference"

    # Lookarounds
    if re.search(r"\(\?[=!]|\(\?<[=!]", p):
        return "pattern contains a lookaround"

    # Quantified group containing a quantifier, followed by * + ? {
    # Scan with a stack tracking whether current group contains a quantifier.
    _QUANTIFIER = set("*+?{")
    stack = []   # each entry: bool (group contains quantifier)
    i = 0
    while i < len(p):
        c = p[i]
        if c == "\\" and i + 1 < len(p):
            i += 2
            continue
        if c == "(":
            stack.append(False)
        elif c == ")":
            if stack:
                has_q = stack.pop()
                # Check if this group is followed by a quantifier
                j = i + 1
                if has_q and j < len(p) and p[j] in _QUANTIFIER:
                    return "pattern contains a quantified group with a nested quantifier"
                # Propagate upward: the parent group now contains a quantifier
                if has_q and stack:
                    stack[-1] = True
        elif c in _QUANTIFIER and stack:
            stack[-1] = True
        i += 1

    # Stress test
    rule_id = "screen"
    hits, err = run_patterns([(rule_id, p)], _STRESS, limits["screen_deadline_ms"] / 1000)
    if err is not None:
        return f"pattern failed stress test: {err}"
    return None


def validate_rule(rule: dict, all_rules: dict, root: str, adapters: dict,
                  kind_buckets: dict, limits: dict) -> list:
    """Return a list of schema error strings for `rule` (§3.5)."""
    import os
    errors = []
    all_by_id = {r["id"]: r for r in all_rules.get("rules", [])}

    rid = rule.get("id", "")

    # --- id format ---
    if not _ID_RE.match(rid):
        errors.append(f"id {rid!r} does not match ^[a-z0-9-]+:[0-9]+:[0-9]+$")

    # --- source ---
    src = rule.get("source", {})
    src_path = src.get("path", "")
    abs_path = os.path.join(root, src_path) if src_path else ""
    if not src_path or not os.path.isfile(abs_path):
        errors.append(f"source.path {src_path!r} does not exist under root")
    else:
        try:
            lines = open(abs_path, encoding="utf-8").readlines()
            n_lines = len(lines)
            sl = src.get("start_line", 0)
            el = src.get("end_line", 0)
            if not (1 <= sl <= el <= n_lines):
                errors.append(
                    f"source span [{sl},{el}] invalid for file with {n_lines} lines"
                )
            else:
                span_text = "".join(lines[sl - 1: el])
                quote = src.get("quote", "")
                if _collapse_ws(quote) not in _collapse_ws(span_text):
                    errors.append(f"quote not found in source span")
        except (OSError, UnicodeDecodeError) as exc:
            errors.append(f"cannot read source file: {exc}")

    # --- bucket ---
    bucket = rule.get("bucket")
    if bucket not in _VALID_BUCKETS:
        errors.append(f"bucket {bucket!r} not in {sorted(_VALID_BUCKETS)}")

    jr = rule.get("judgment_reason")
    check = rule.get("check")
    cases = rule.get("cases", [])

    if bucket == "judgment":
        if jr not in _VALID_JUDGMENT_REASONS:
            errors.append(f"judgment_reason {jr!r} not in {sorted(_VALID_JUDGMENT_REASONS)}")
        if check is not None:
            errors.append("judgment rule must have check: null")
        if cases:
            errors.append("judgment rule must have empty cases")
    elif bucket in ("block", "audit"):
        if jr is not None:
            errors.append("block/audit rule must have judgment_reason: null")
        if not isinstance(check, dict):
            errors.append("block/audit rule must have a check object")
        else:
            kind = check.get("kind")
            if kind not in _VALID_KINDS:
                errors.append(f"check.kind {kind!r} not in {sorted(_VALID_KINDS)}")
            else:
                # Parameters
                expected_params = _KIND_PARAMS[kind]
                for param in expected_params:
                    val = check.get(param)
                    if not isinstance(val, list) or not val:
                        errors.append(
                            f"check.{param} must be a non-empty list for kind {kind!r}"
                        )
                    elif param == "globs":
                        for g in val:
                            try:
                                glob_to_regex(g)
                            except ValueError as exc:
                                errors.append(f"invalid glob {g!r}: {exc}")
                    elif param == "patterns":
                        for p in val:
                            err = screen_pattern(p, limits)
                            if err:
                                errors.append(f"invalid pattern {p!r}: {err}")
                # No extra params
                for key in check:
                    if key != "kind" and key not in expected_params:
                        errors.append(f"unexpected check key {key!r} for kind {kind!r}")
                # Bucket must agree with kind_buckets
                expected_bucket = kind_buckets.get(kind)
                if expected_bucket and bucket != expected_bucket:
                    errors.append(
                        f"bucket {bucket!r} disagrees with kind_buckets[{kind!r}]={expected_bucket!r}"
                    )

        # Cases
        adapter_tools = set(adapters.get("tools", {}).keys())
        if bucket == "block":
            pre_tool = [c for c in cases if c.get("type") == "pre_tool"]
            if len(pre_tool) < 3:
                errors.append(
                    f"block rule needs at least 3 pre_tool cases, has {len(pre_tool)}"
                )
            else:
                expects = {c.get("expect") for c in pre_tool}
                if "allow" not in expects:
                    errors.append("block rule needs at least one allow pre_tool case")
                if "block" not in expects:
                    errors.append("block rule needs at least one block pre_tool case")
            for c in cases:
                if c.get("tool") and c["tool"] not in adapter_tools:
                    errors.append(f"case tool {c['tool']!r} not in adapters")
        elif bucket == "audit":
            final_state = [c for c in cases if c.get("type") == "final_state"]
            if len(final_state) < 3:
                errors.append(
                    f"audit rule needs at least 3 final_state cases, has {len(final_state)}"
                )
            else:
                expects = {c.get("expect") for c in final_state}
                if "clean" not in expects:
                    errors.append("audit rule needs at least one clean final_state case")
                if "finding" not in expects:
                    errors.append("audit rule needs at least one finding final_state case")
            for c in cases:
                if c.get("tool") and c["tool"] not in adapter_tools:
                    errors.append(f"case tool {c['tool']!r} not in adapters")

    # --- duplicate_of ---
    dup_of = rule.get("duplicate_of")
    if dup_of is not None:
        target = all_by_id.get(dup_of)
        if target is None:
            errors.append(f"duplicate_of {dup_of!r} references a non-existent rule")
        elif target.get("duplicate_of") is not None:
            errors.append(f"duplicate_of {dup_of!r} is itself a duplicate")

    # --- conflicts_with ---
    for cid in rule.get("conflicts_with", []):
        other = all_by_id.get(cid)
        if other is None:
            errors.append(f"conflicts_with {cid!r} references a non-existent rule")
        elif rid not in other.get("conflicts_with", []):
            errors.append(f"conflicts_with {cid!r} is not symmetric")

    return errors


def validate_all(doc: dict, root: str, adapters: dict, kind_buckets: dict,
                 limits: dict) -> dict:
    """Validate all rules in `doc`. Returns {id: [error_strings]}."""
    rules = doc.get("rules", [])
    errors = {}
    seen_ids = {}

    # Count patterns for the limit check
    pattern_count = 0

    for rule in rules:
        rid = rule.get("id", "")

        # Uniqueness
        if rid in seen_ids:
            errors.setdefault(rid, []).append(f"duplicate id {rid!r}")
        seen_ids[rid] = True

        # Per-rule validation
        rule_errors = validate_rule(rule, doc, root, adapters, kind_buckets, limits)
        if rule_errors:
            errors[rid] = errors.get(rid, []) + rule_errors

        # Pattern count limit
        check = rule.get("check") or {}
        kind = check.get("kind", "")
        patterns = []
        if kind in ("deny_command", "deny_diff_pattern"):
            patterns = check.get("patterns", [])
        pattern_count += len(patterns)
        if pattern_count > limits.get("max_patterns", 50):
            errors.setdefault(rid, []).append(
                f"total pattern count {pattern_count} exceeds limit {limits['max_patterns']}"
            )

    return errors

"""Pre-tool evaluation and final-state dispatch (guide §5.5)."""

from stickler.adapters import extract_ops
from stickler.globs import any_match
from stickler.paths import repo_paths
from stickler.regexrun import run_patterns


def _control_paths(config: dict) -> list:
    return list(config.get("control_globs", [])) + list(config.get("engine_owned_globs", []))


def _is_control(path, config):
    return path is not None and any_match(_control_paths(config), path)


def evaluate_pre_tool(tool: str, tool_input: dict, rules: list, adapters: dict,
                      config: dict, cwd: str, root: str) -> dict:
    """Evaluate a PreToolUse call against the rule set.

    Returns a Decision dict per guide §5.5.
    """
    on_error = config.get("on_error", "allow")
    missing_path_field = config.get("missing_path_field", "block")
    limits = config.get("limits", {})
    max_cmd = limits.get("max_command_bytes", 65536)
    pre_deadline = limits.get("pre_tool_regex_deadline_ms", 1500) / 1000

    try:
        ops, coverage, error = extract_ops(tool, tool_input, adapters)
    except Exception as exc:
        return _error_decision(tool, on_error, ops=[], coverage="error",
                               error=f"extract_ops failed: {exc}")

    # Malformed input
    if coverage == "malformed":
        if missing_path_field == "block":
            msg = "Stickler cannot determine the target path"
            return {
                "decision": "block",
                "rule_ids": [],
                "messages": [f"Stickler blocked this {tool} call: {msg}."],
                "coverage": "malformed",
                "error": error,
                "ops": ops,
            }
        return _allow(ops, "malformed", error)

    # Unknown tool or unsupported route → allow
    if coverage in ("unknown_tool", "unsupported_route"):
        return _allow(ops, coverage, error)

    # Resolve paths for all ops
    try:
        for op in ops:
            targets = []
            for p in op.get("paths", []):
                op_cwd = op.get("cwd") or cwd
                lex, res = repo_paths(p, op_cwd, root)
                targets.append([lex, res])
            # Rename: from and to
            if op.get("from"):
                op_cwd = op.get("cwd") or cwd
                lex, res = repo_paths(op["from"], op_cwd, root)
                op["_from_targets"] = [[lex, res]]
            if op.get("to"):
                op_cwd = op.get("cwd") or cwd
                lex, res = repo_paths(op["to"], op_cwd, root)
                op["_to_targets"] = [[lex, res]]
            op["_targets"] = targets
    except Exception as exc:
        return _error_decision(tool, on_error, ops=ops, coverage="error",
                               error=f"path resolution failed: {exc}")

    # Evaluate path rules
    blocking_ids = []
    blocking_msgs = []
    try:
        for rule in rules:
            check = rule.get("check") or {}
            kind = check.get("kind")
            rid = rule["id"]
            is_builtin = rid.startswith("builtin:")

            if kind in ("deny_path", "allow_paths_only", "forbid_file_deletion"):
                globs = check.get("globs", [])
                for op in ops:
                    op_kind = op.get("operation")

                    # Collect path pairs to check
                    pairs = list(op.get("_targets", []))
                    if op_kind == "rename":
                        pairs += list(op.get("_from_targets", []))
                        pairs += list(op.get("_to_targets", []))

                    if kind == "deny_path":
                        for lex, res in pairs:
                            # Skip control paths for user rules
                            if not is_builtin and (_is_control(lex, config) or _is_control(res, config)):
                                continue
                            if any_match(globs, lex) or any_match(globs, res):
                                blocking_ids.append(rid)
                                src = rule.get("source", {})
                                blocking_msgs.append(
                                    f"Stickler blocked this {tool} call: "
                                    f"rule {rid} ({src.get('path','?')} line {src.get('start_line','?')}): "
                                    f"{rule.get('text','')!r}"
                                )
                                break

                    elif kind == "allow_paths_only":
                        # All mutated paths must match — if any doesn't, block
                        for lex, res in pairs:
                            if not is_builtin and (_is_control(lex, config) or _is_control(res, config)):
                                continue
                            if lex is None or res is None:
                                blocking_ids.append(rid)
                                src = rule.get("source", {})
                                blocking_msgs.append(
                                    f"Stickler blocked this {tool} call: "
                                    f"rule {rid} ({src.get('path','?')} line {src.get('start_line','?')}): "
                                    f"{rule.get('text','')!r}"
                                )
                                break
                            if not any_match(globs, lex) or not any_match(globs, res):
                                blocking_ids.append(rid)
                                src = rule.get("source", {})
                                blocking_msgs.append(
                                    f"Stickler blocked this {tool} call: "
                                    f"rule {rid} ({src.get('path','?')} line {src.get('start_line','?')}): "
                                    f"{rule.get('text','')!r}"
                                )
                                break

                    elif kind == "forbid_file_deletion":
                        # Only delete ops and rename-from
                        delete_pairs = []
                        if op_kind == "delete":
                            delete_pairs = list(op.get("_targets", []))
                        elif op_kind == "rename":
                            delete_pairs = list(op.get("_from_targets", []))
                        for lex, res in delete_pairs:
                            if not is_builtin and (_is_control(lex, config) or _is_control(res, config)):
                                continue
                            if any_match(globs, lex) or any_match(globs, res):
                                blocking_ids.append(rid)
                                src = rule.get("source", {})
                                blocking_msgs.append(
                                    f"Stickler blocked this {tool} call: "
                                    f"rule {rid} ({src.get('path','?')} line {src.get('start_line','?')}): "
                                    f"{rule.get('text','')!r}"
                                )
                                break

    except Exception as exc:
        return _error_decision(tool, on_error, ops=ops, coverage="error",
                               error=f"path rule evaluation failed: {exc}")

    # Evaluate deny_command rules
    deny_cmd_rules = [r for r in rules if (r.get("check") or {}).get("kind") == "deny_command"]
    if deny_cmd_rules:
        for op in ops:
            cmd = op.get("command")
            if cmd is None:
                continue
            if len(cmd.encode()) > max_cmd:
                msg = f"command too long ({len(cmd.encode())} bytes > {max_cmd})"
                if on_error == "block":
                    return _error_decision(tool, on_error, ops=ops, coverage="error",
                                           error=msg)
                # allow but log error
                return _allow(ops, "error", msg)

            patterns = []
            for rule in deny_cmd_rules:
                patterns += [(rule["id"], p) for p in rule["check"].get("patterns", [])]
            try:
                hits, err = run_patterns(patterns, [cmd], pre_deadline)
            except Exception as exc:
                return _error_decision(tool, on_error, ops=ops, coverage="error",
                                       error=f"run_patterns failed: {exc}")
            if err is not None:
                return _error_decision(tool, on_error, ops=ops, coverage="error",
                                       error=err)
            for hit_id, _ in hits:
                if hit_id not in blocking_ids:
                    blocking_ids.append(hit_id)
                    rule = next(r for r in deny_cmd_rules if r["id"] == hit_id)
                    src = rule.get("source", {})
                    blocking_msgs.append(
                        f"Stickler blocked this {tool} call: "
                        f"rule {hit_id} ({src.get('path','?')} line {src.get('start_line','?')}): "
                        f"{rule.get('text','')!r}"
                    )

    blocking_ids_sorted = sorted(set(blocking_ids))
    if blocking_ids_sorted:
        # Deduplicate messages preserving first-seen order
        seen = set()
        msgs = []
        for m in blocking_msgs:
            if m not in seen:
                seen.add(m)
                msgs.append(m)
        return {
            "decision": "block",
            "rule_ids": blocking_ids_sorted,
            "messages": msgs[:5],
            "coverage": coverage,
            "error": None,
            "ops": ops,
        }

    return _allow(ops, coverage, None)


def _allow(ops, coverage, error):
    return {"decision": "allow", "rule_ids": [], "messages": [],
            "coverage": coverage, "error": error, "ops": ops}


def _error_decision(tool, on_error, ops, coverage, error):
    decision = on_error  # "allow" or "block"
    msgs = []
    if decision == "block":
        msgs = [f"Stickler blocked this {tool} call: it could not evaluate the call ({error})."]
    return {"decision": decision, "rule_ids": [], "messages": msgs,
            "coverage": coverage, "error": error, "ops": ops}


def evaluate_final_state(baseline_files: dict, final_files: dict, rules: list,
                         config: dict) -> dict:
    """Evaluate final-state audit (guide §5.5). Used by validator and scorer."""
    from stickler.inventory import inventory_from_map
    from stickler.audit import audit

    base, content_base = inventory_from_map(baseline_files)
    final, content_final = inventory_from_map(final_files)
    findings, unsupported, errors = audit(base, final, rules, config,
                                          content_base, content_final)
    return {"findings": findings, "unsupported": unsupported, "errors": errors}

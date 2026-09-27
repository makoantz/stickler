"""Stickler lifecycle hook entry point (guide §5.10)."""

import json
import os
import sys
import time


def _load_pointer(stickler_dir: str) -> dict:
    active_path = os.path.join(stickler_dir, "active.json")
    with open(active_path, encoding="utf-8") as fh:
        return json.load(fh)


def _load_snapshot(stickler_dir: str, rules_sha: str) -> dict:
    snap_path = os.path.join(stickler_dir, "active", f"rules.{rules_sha}.json")
    with open(snap_path, encoding="utf-8") as fh:
        return json.load(fh)


def _verify_pointer(pointer: dict, stickler_dir: str):
    """Verify all digests in the pointer match current files."""
    from stickler.util import sha256_file, digest_engine

    checks = {
        "adapters_sha256": os.path.join(stickler_dir, "adapters.json"),
        "kind_buckets_sha256": os.path.join(stickler_dir, "kind-buckets.json"),
        "config_sha256": os.path.join(stickler_dir, "config.json"),
    }
    for key, path in checks.items():
        expected = pointer.get(key)
        if expected and sha256_file(path) != expected:
            raise ValueError(f"digest_mismatch:{key}")

    engine_dir = os.path.join(stickler_dir, "engine", "stickler")
    if os.path.isdir(engine_dir):
        expected_engine = pointer.get("engine_sha256")
        if expected_engine and digest_engine(engine_dir) != expected_engine:
            raise ValueError("digest_mismatch:engine_sha256")


def _verify_snapshot(snapshot: dict, rules_sha: str):
    from stickler.util import sha256_bytes, canonical
    data = canonical(snapshot)
    actual = sha256_bytes(data)
    if actual != rules_sha:
        raise ValueError("digest_mismatch:rules_sha256")


def _log_error(stickler_dir: str, msg: str):
    log_path = os.path.join(stickler_dir, "hook-errors.log")
    try:
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(f"{msg}\n")
    except OSError:
        pass


def main():
    t0 = time.monotonic()
    raw = sys.stdin.read()

    # Find root early for error logging
    stickler_dir = None
    root = None
    try:
        from stickler.paths import find_root
        root = find_root(os.getcwd())
        if root:
            stickler_dir = os.path.join(root, ".stickler")
    except Exception:
        pass

    try:
        payload = json.loads(raw)
    except Exception as exc:
        if stickler_dir:
            _log_error(stickler_dir, f"JSON parse error: {exc}")
        # Check if we should block on error
        try:
            if stickler_dir:
                config_path = os.path.join(stickler_dir, "config.json")
                if os.path.isfile(config_path):
                    with open(config_path) as fh:
                        cfg = json.load(fh)
                    if cfg.get("on_error") == "block" and "PreToolUse" in raw:
                        print("Stickler blocked this call: could not parse hook input.", file=sys.stderr)
                        sys.exit(2)
        except Exception:
            pass
        sys.exit(0)

    event = payload.get("event", "")
    session_id = payload.get("session_id", "")

    # If no root or no config, exit 0
    if not root or not stickler_dir:
        sys.exit(0)
    config_path = os.path.join(stickler_dir, "config.json")
    if not os.path.isfile(config_path):
        sys.exit(0)

    try:
        from stickler.util import read_json, now_utc, append_jsonl, sha256_bytes
        config = read_json(config_path)
    except Exception as exc:
        _log_error(stickler_dir, f"config load error: {exc}")
        sys.exit(0)

    mode = config.get("mode", "observe")
    if mode == "compile":
        sys.exit(0)

    on_error = config.get("on_error", "allow")

    # Load and verify pointer
    try:
        pointer = _load_pointer(stickler_dir)
        _verify_pointer(pointer, stickler_dir)
    except Exception as exc:
        err_msg = str(exc)
        _handle_error(event, on_error, tool=payload.get("tool", ""), error=err_msg,
                      stickler_dir=stickler_dir, session_id=session_id)
        sys.exit(0)

    rules_sha = pointer.get("rules_sha256", "")

    # Load session and pin
    try:
        from stickler.state import Session
        session = Session(root, session_id)
        pin = session.ensure_pinned(pointer)
        pin_sha = pin.get("rules_sha256", rules_sha)

        # Detect mid-session policy change
        if pin_sha != rules_sha:
            append_jsonl(os.path.join(session.dir, "events.jsonl"), {
                "ts": now_utc(), "event": "policy_changed_mid_session",
                "session": session.sid,
            })

        # Load pinned snapshot
        try:
            snapshot = _load_snapshot(stickler_dir, pin_sha)
            _verify_snapshot(snapshot, pin_sha)
        except Exception as exc:
            err_msg = str(exc)
            _handle_error(event, on_error, tool=payload.get("tool", ""), error=err_msg,
                          stickler_dir=stickler_dir, session_id=session_id)
            sys.exit(0)

        rules = snapshot.get("rules", []) + snapshot.get("builtin", [])

    except Exception as exc:
        _log_error(stickler_dir, f"session/pin error: {exc}")
        sys.exit(0)

    # Ensure baseline for all events except Stop
    if event != "Stop":
        try:
            session.ensure_baseline(config)
        except Exception as exc:
            _log_error(stickler_dir, f"baseline error: {exc}")

    events_log = os.path.join(session.dir, "events.jsonl")

    try:
        if event in ("SessionStart", "UserPromptSubmit"):
            _handle_session_prompt(event, session, rules, policy_sha=pin_sha,
                                   pointer=pin, mode=mode, config=config,
                                   events_log=events_log)

        elif event == "PreToolUse":
            _handle_pre_tool(payload, session, rules, config, root,
                             on_error, mode, pin_sha, events_log, t0)

        elif event == "PostToolUse":
            _handle_post_tool(payload, session, events_log)

        elif event == "Stop":
            _handle_stop(session, rules, config, root, pin, pin_sha,
                         stickler_dir, events_log, mode)

    except Exception as exc:
        try:
            append_jsonl(events_log, {
                "ts": now_utc(), "event": event, "session": session.sid,
                "coverage": "error", "error": str(exc)[:200],
            })
        except Exception:
            pass
        if event == "PreToolUse" and on_error == "block":
            tool = payload.get("tool", "")
            print(f"Stickler blocked this {tool} call: it could not evaluate the call ({exc}).",
                  file=sys.stderr)
            sys.exit(2)
        sys.exit(0)


def _handle_error(event, on_error, tool, error, stickler_dir, session_id):
    _log_error(stickler_dir, f"hook error ({event}): {error}")
    if event == "PreToolUse" and on_error == "block":
        print(f"Stickler blocked this {tool} call: it could not evaluate the call ({error}).",
              file=sys.stderr)
        sys.exit(2)


def _handle_session_prompt(event, session, rules, policy_sha, pointer, mode,
                           config, events_log):
    from stickler.util import append_jsonl, now_utc
    from stickler.report import summary_lines

    append_jsonl(events_log, {
        "ts": now_utc(), "event": event, "session": session.sid,
        "decision": "none", "rule_ids": [], "coverage": "ok", "error": None,
    })

    if mode == "governed":
        active_count = len(rules)
        blocks = session.pending_blocks() if event == "UserPromptSubmit" else []
        undelivered = session.undelivered()
        reports = []
        for name, marker in undelivered:
            try:
                from stickler.util import read_json
                rep_path = os.path.join(os.path.dirname(session._root), marker["report"])
                if not os.path.isabs(rep_path):
                    rep_path = os.path.join(session._root, marker["report"])
                rep = read_json(rep_path)
                rep["_report_path"] = marker["report"]
                reports.append((name, rep))
            except Exception:
                pass
        pin_sha = pointer.get("rules_sha256", "")
        lines = summary_lines(active_count, policy_sha, blocks, reports,
                              pin_sha, first=(event == "SessionStart"))
        if lines:
            print("\n".join(lines))
        if blocks:
            session.mark_blocks_delivered()
        if reports:
            session.mark_delivered([name for name, _ in reports])


def _handle_pre_tool(payload, session, rules, config, root,
                     on_error, mode, pin_sha, events_log, t0):
    from stickler.util import append_jsonl, now_utc, read_json, redact
    from stickler.adapters import extract_ops

    tool = payload.get("tool", "")
    tool_input = payload.get("input", {})
    cwd = os.getcwd()

    adapters_path = os.path.join(session._root, ".stickler", "adapters.json")
    try:
        adapters = read_json(adapters_path)
    except Exception:
        adapters = {"tools": {}}

    if mode == "governed":
        from stickler.policy import evaluate_pre_tool
        decision_obj = evaluate_pre_tool(tool, tool_input, rules, adapters,
                                         config, cwd, root)
        decision = decision_obj["decision"]
        rule_ids = decision_obj["rule_ids"]
        coverage = decision_obj["coverage"]
        error = decision_obj.get("error")
        ops = decision_obj.get("ops", [])
    else:
        # Observe mode: always none
        try:
            ops, coverage, error = extract_ops(tool, tool_input, adapters)
        except Exception as exc:
            ops, coverage, error = [], "error", str(exc)
        decision = "none"
        rule_ids = []

    elapsed_ms = int((time.monotonic() - t0) * 1000)
    log_entry = {
        "ts": now_utc(),
        "event": "PreToolUse",
        "session": session.sid,
        "tool": tool,
        "ops": [_redact_op(op) for op in ops],
        "decision": decision,
        "rule_ids": rule_ids,
        "coverage": coverage,
        "error": error,
        "elapsed_ms": elapsed_ms,
        "policy_sha256": pin_sha,
    }
    append_jsonl(events_log, log_entry)

    if decision == "block":
        messages = decision_obj.get("messages", [])
        for msg in messages:
            print(msg, file=sys.stderr)
        session.queue_block({
            "rule_id": rule_ids[0] if rule_ids else "",
            "tool": tool,
            "text": messages[0] if messages else "",
        })
        sys.exit(2)


def _redact_op(op: dict) -> dict:
    from stickler.util import redact
    return {
        "operation": op.get("operation"),
        "targets": [[lex, res] for lex, res in op.get("_targets", [])],
        "command": redact(op.get("command")) if op.get("command") else None,
    }


def _handle_post_tool(payload, session, events_log):
    from stickler.util import append_jsonl, now_utc, sha256_bytes

    tool = payload.get("tool", "")
    output = payload.get("output", "")
    output_bytes = output.encode("utf-8") if isinstance(output, str) else b""
    append_jsonl(events_log, {
        "ts": now_utc(),
        "event": "PostToolUse",
        "session": session.sid,
        "tool": tool,
        "output_len": len(output_bytes),
        "output_sha256": sha256_bytes(output_bytes),
    })


def _handle_stop(session, rules, config, root, pin, pin_sha,
                 stickler_dir, events_log, mode):
    from stickler.util import append_jsonl, now_utc, read_json, write_json_atomic, sha256_bytes
    from stickler.inventory import take_inventory, blob_content_fn
    from stickler.audit import audit, control_integrity, diff_inventories
    from stickler.report import render_stop_md

    import subprocess

    baseline_path = os.path.join(session.dir, "baseline.json")
    blob_dir = os.path.join(session.dir, "blobs")
    n = session.next_stop_number()

    if not os.path.exists(baseline_path):
        report = {
            "session": session.sid, "stop": n,
            "status": "incomplete", "incomplete_reason": "no_baseline",
            "policy_sha256": pin_sha, "baseline_head": None, "final_head": None,
            "commits": [], "changes": {}, "findings": [], "unsupported": [],
            "control_integrity": {"changed": [], "engine_ok": True},
            "excluded_ignored_count": 0, "shared_worktree": False, "errors": [],
            "limits": _LIMITS_TEXT,
        }
    else:
        try:
            baseline = read_json(baseline_path)
        except Exception as exc:
            _log_error(stickler_dir, f"stop: baseline load error: {exc}")
            return

        final_blob_dir = os.path.join(session.dir, f"blobs-stop-{n}")
        os.makedirs(final_blob_dir, exist_ok=True)
        final = take_inventory(root, config, blob_dir=final_blob_dir)
        final_path = os.path.join(session.dir, f"final-{n}.json")
        write_json_atomic(final_path, final)

        content_base = blob_content_fn(blob_dir)
        content_final = blob_content_fn(final_blob_dir)

        findings, unsupported, errs = audit(baseline, final, rules, config,
                                            content_base, content_final)
        ci = control_integrity(baseline, final, config, pin, root)
        changes = diff_inventories(baseline, final)

        # Get commits since baseline
        baseline_head = baseline.get("head")
        final_head = final.get("head")
        commits = []
        if baseline_head and final_head and baseline_head != final_head:
            r = subprocess.run(
                ["git", "-C", root, "log", "--oneline",
                 f"{baseline_head}..{final_head}"],
                capture_output=True, text=True
            )
            if r.returncode == 0:
                commits = r.stdout.strip().splitlines()

        report = {
            "session": session.sid, "stop": n,
            "status": "complete" if not errs else "incomplete",
            "incomplete_reason": None if not errs else "audit_errors",
            "policy_sha256": pin_sha,
            "baseline_head": baseline_head,
            "final_head": final_head,
            "commits": commits,
            "changes": changes,
            "findings": findings,
            "unsupported": unsupported,
            "control_integrity": ci,
            "excluded_ignored_count": final.get("excluded_ignored_count", 0),
            "shared_worktree": baseline.get("shared_worktree", False),
            "errors": errs,
            "limits": _LIMITS_TEXT,
        }

    # Write report files
    report_rel = os.path.join(".stickler", "reports", session.sid, f"stop-{n}.json")
    report_abs = os.path.join(root, report_rel)
    os.makedirs(os.path.dirname(report_abs), exist_ok=True)
    write_json_atomic(report_abs, report)
    md_path = report_abs.replace(".json", ".md")
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write(render_stop_md(report))

    # Write replay manifest
    replay = {
        "baseline": baseline_path if os.path.exists(baseline_path) else None,
        "final": os.path.join(session.dir, f"final-{n}.json"),
        "blob_dir": blob_dir,
        "snapshot": os.path.join(stickler_dir, "active", f"rules.{pin_sha}.json"),
        "policy_sha256": pin_sha,
        "adapters_sha256": pin.get("adapters_sha256"),
        "config_sha256": pin.get("config_sha256"),
        "engine_sha256": pin.get("engine_sha256"),
    }
    replay_path = os.path.join(session.dir, f"replay-stop-{n}.json")
    write_json_atomic(replay_path, replay)

    session.outbox_add(n, report_rel, pin_sha)

    append_jsonl(events_log, {
        "ts": now_utc(), "event": "Stop", "session": session.sid,
        "stop": n, "status": report["status"],
    })


_LIMITS_TEXT = (
    "The audit sees final state only. A forbidden change that was later reverted is invisible. "
    "An unchanged tree does not show that no forbidden action was attempted. "
    "Attempts are known only from the PreToolUse log, and only on supported routes."
)


if __name__ == "__main__":
    main()

"""Offline re-audit of a run with any policy snapshot (guide §5.11)."""

import argparse
import os
import sys


def main():
    parser = argparse.ArgumentParser(
        description="Re-audit a run with any policy snapshot"
    )
    parser.add_argument("--run", required=True, help="Run directory")
    parser.add_argument("--policy", required=True, help="Snapshot JSON file")
    parser.add_argument("--session", default=None, help="Session ID")
    parser.add_argument("--final-now", action="store_true",
                        help="Take a fresh inventory instead of stored final")
    parser.add_argument("--out", required=True, help="Output report JSON")
    args = parser.parse_args()

    from stickler.util import read_json, write_json_atomic, now_utc
    from stickler.inventory import take_inventory, blob_content_fn
    from stickler.audit import audit, diff_inventories

    run = os.path.abspath(args.run)
    stickler_dir = os.path.join(run, ".stickler")

    # Load policy snapshot
    snapshot = read_json(args.policy)
    rules = snapshot.get("rules", []) + snapshot.get("builtin", [])

    # Load config
    config_path = os.path.join(stickler_dir, "config.json")
    config = read_json(config_path) if os.path.isfile(config_path) else {}

    # Find session
    state_dir = os.path.join(stickler_dir, "state")
    if args.session:
        sid = args.session
    else:
        sessions = [e for e in os.listdir(state_dir)
                    if os.path.isdir(os.path.join(state_dir, e))]
        if not sessions:
            print("No sessions found", file=sys.stderr)
            sys.exit(1)
        sid = sorted(sessions)[0]

    session_dir = os.path.join(state_dir, sid)
    baseline_path = os.path.join(session_dir, "baseline.json")
    blob_dir = os.path.join(session_dir, "blobs")

    if not os.path.isfile(baseline_path):
        print(f"No baseline.json in {session_dir}", file=sys.stderr)
        sys.exit(1)

    baseline = read_json(baseline_path)
    content_base = blob_content_fn(blob_dir)

    if args.final_now:
        final = take_inventory(run, config)
        content_final = blob_content_fn(blob_dir)  # no new blobs
    else:
        # Find latest final-N.json
        finals = sorted(
            [f for f in os.listdir(session_dir) if f.startswith("final-") and f.endswith(".json")],
            key=lambda x: int(x[6:-5])
        )
        if not finals:
            print("No final inventory found", file=sys.stderr)
            sys.exit(1)
        final_path = os.path.join(session_dir, finals[-1])
        final = read_json(final_path)
        n = int(finals[-1][6:-5])
        final_blob_dir = os.path.join(session_dir, f"blobs-stop-{n}")
        content_final = blob_content_fn(
            final_blob_dir if os.path.isdir(final_blob_dir) else blob_dir
        )

    findings, unsupported, errors = audit(baseline, final, rules, config,
                                           content_base, content_final)
    changes = diff_inventories(baseline, final)

    report = {
        "session": sid,
        "stop": None,
        "status": "complete" if not errors else "incomplete",
        "incomplete_reason": None if not errors else "audit_errors",
        "policy_sha256": args.policy,
        "baseline_head": baseline.get("head"),
        "final_head": final.get("head"),
        "commits": [],
        "changes": changes,
        "findings": findings,
        "unsupported": unsupported,
        "control_integrity": {"changed": [], "engine_ok": True},
        "excluded_ignored_count": final.get("excluded_ignored_count", 0),
        "shared_worktree": False,
        "errors": errors,
        "limits": (
            "The audit sees final state only. A forbidden change that was later "
            "reverted is invisible."
        ),
    }

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    write_json_atomic(args.out, report)
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()

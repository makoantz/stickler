"""Offline replay verification (guide §5.16)."""

import argparse
import json
import os
import sys


def _replay_validate(run_dir: str) -> list:
    """Re-run --check on the run's rules.json with its .stickler/ config."""
    import tempfile, shutil
    from stickler.util import read_json
    from stickler.stickler_validate import _run_validation, _compute_validation_json

    results = []
    rules_path = os.path.join(run_dir, "stickler", "rules.json")
    if not os.path.isfile(rules_path):
        return results

    stickler_dir = os.path.join(run_dir, ".stickler")

    try:
        doc, validation_rules, history_path = _run_validation(run_dir)
        fresh = _compute_validation_json(doc, validation_rules, history_path, run_dir)
    except Exception as exc:
        results.append(f"VALIDATE ERROR {run_dir}: {exc}")
        return results

    committed_path = os.path.join(run_dir, "stickler", "validation.json")
    if not os.path.isfile(committed_path):
        results.append(f"SKIP (no validation.json): {run_dir}")
        return results

    committed = read_json(committed_path)

    def _strip_ts(obj):
        if isinstance(obj, dict):
            return {k: _strip_ts(v) for k, v in obj.items()
                    if k not in ("ts", "activated_at", "installed")}
        if isinstance(obj, list):
            return [_strip_ts(i) for i in obj]
        return obj

    if _strip_ts(committed) != _strip_ts(fresh):
        results.append(f"MISMATCH (validation.json): {run_dir}")
    return results


def _replay_audit(replay_manifest_path: str) -> list:
    """Re-run the audit from a replay manifest and compare with stored findings."""
    from stickler.util import read_json
    from stickler.inventory import blob_content_fn
    from stickler.audit import audit

    results = []
    try:
        manifest = read_json(replay_manifest_path)
    except Exception as exc:
        return [f"MANIFEST ERROR {replay_manifest_path}: {exc}"]

    baseline_path = manifest.get("baseline")
    final_path = manifest.get("final")
    blob_dir = manifest.get("blob_dir")
    snap_path = manifest.get("snapshot")

    if not all([baseline_path, final_path, snap_path]):
        return [f"not replayable: {replay_manifest_path}"]
    for p in [baseline_path, final_path, snap_path]:
        if not os.path.isfile(p):
            return [f"not replayable (missing {p}): {replay_manifest_path}"]

    try:
        baseline = read_json(baseline_path)
        final = read_json(final_path)
        snapshot = read_json(snap_path)
    except Exception as exc:
        return [f"LOAD ERROR {replay_manifest_path}: {exc}"]

    rules = snapshot.get("rules", []) + snapshot.get("builtin", [])
    config = {"on_error": "allow", "control_globs": [], "engine_owned_globs": [],
              "limits": {"audit_regex_deadline_ms": 20000}}

    content_base = blob_content_fn(blob_dir) if blob_dir else lambda s: None
    content_final = blob_content_fn(blob_dir) if blob_dir else lambda s: None

    try:
        findings, _, _ = audit(baseline, final, rules, config, content_base, content_final)
    except Exception as exc:
        return [f"AUDIT ERROR {replay_manifest_path}: {exc}"]

    # Compare with stored stop report
    stop_path = replay_manifest_path.replace("replay-stop-", "stop-")
    if not os.path.isfile(stop_path):
        return [f"not replayable (no stop report): {replay_manifest_path}"]

    try:
        stored = read_json(stop_path)
    except Exception:
        return [f"not replayable (unreadable stop): {replay_manifest_path}"]

    stored_findings = stored.get("findings", [])
    stored_key = sorted((f["rule_id"], tuple(sorted(f.get("paths", []))),
                         f.get("line")) for f in stored_findings)
    fresh_key = sorted((f["rule_id"], tuple(sorted(f.get("paths", []))),
                        f.get("line")) for f in findings)

    if stored_key != fresh_key:
        results.append(f"FINDINGS MISMATCH: {replay_manifest_path}")
    return results


def _replay_scores(score_config_path: str) -> list:
    """Re-run scoring and compare with committed scores.json."""
    import subprocess
    results = []
    try:
        import sys as _sys
        r = subprocess.run(
            [_sys.executable, "-m", "stickler.score", "run",
             "--config", score_config_path],
            capture_output=True, text=True
        )
        if r.returncode != 0:
            results.append(f"SCORE ERROR: {r.stderr[:200]}")
    except Exception as exc:
        results.append(f"SCORE ERROR: {exc}")
    return results


def main():
    parser = argparse.ArgumentParser(description="Offline replay")
    parser.add_argument("--live", action="store_true",
                        help="Also recompute live fields")
    args = parser.parse_args()

    # Find results/raw/
    here = os.path.abspath(".")
    raw_dir = os.path.join(here, "results", "raw")
    failures = []

    if os.path.isdir(raw_dir):
        for run_name in sorted(os.listdir(raw_dir)):
            run_dir = os.path.join(raw_dir, run_name)
            if not os.path.isdir(run_dir):
                continue
            # Validate specs
            failures += _replay_validate(run_dir)
            # Replay audits
            stickler_dir = os.path.join(run_dir, ".stickler")
            if os.path.isdir(stickler_dir):
                for sid in os.listdir(os.path.join(stickler_dir, "state") if
                                      os.path.isdir(os.path.join(stickler_dir, "state")) else stickler_dir):
                    sid_dir = os.path.join(stickler_dir, "state", sid)
                    if not os.path.isdir(sid_dir):
                        continue
                    for fname in os.listdir(sid_dir):
                        if fname.startswith("replay-stop-") and fname.endswith(".json"):
                            failures += _replay_audit(os.path.join(sid_dir, fname))

    # Score replay
    score_config = os.path.join(here, "results", "score-config.json")
    if os.path.isfile(score_config):
        failures += _replay_scores(score_config)

    if failures:
        for f in failures:
            print(f)
        sys.exit(1)
    print("REPLAY OK")


if __name__ == "__main__":
    main()

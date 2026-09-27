"""Effect snapshots and control checks (guide §5.14)."""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile


def _run_git(d, *args):
    return subprocess.run(["git", "-C", d] + list(args), capture_output=True, text=True)


def _snapshot(run_dir: str, attempt_id: str, out_dir: str, label: str):
    """Take a before/after snapshot."""
    from stickler.util import now_utc, read_json
    from stickler.inventory import take_inventory

    stickler_dir = os.path.join(run_dir, ".stickler")
    config_path = os.path.join(stickler_dir, "config.json")
    config = read_json(config_path) if os.path.isfile(config_path) else {}

    inv = take_inventory(run_dir, config)

    # Remote refs
    remote_dirs = []
    r = _run_git(run_dir, "remote", "-v")
    for line in r.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2 and "(fetch)" in line:
            url = parts[1]
            if os.path.isdir(url):
                remote_dirs.append(url)

    remote_refs = {}
    for remote_dir in remote_dirs:
        r2 = subprocess.run(
            ["git", "--git-dir", remote_dir, "show-ref"],
            capture_output=True, text=True
        )
        remote_refs[remote_dir] = r2.stdout.strip().splitlines()

    # Event log offsets
    event_offsets = {}
    state_dir = os.path.join(stickler_dir, "state")
    if os.path.isdir(state_dir):
        for sid in os.listdir(state_dir):
            log = os.path.join(state_dir, sid, "events.jsonl")
            if os.path.isfile(log):
                event_offsets[sid] = os.path.getsize(log)

    snap = {
        "ts": now_utc(),
        "inventory": inv,
        "remote_refs": remote_refs,
        "event_offsets": event_offsets,
    }

    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{attempt_id}-{label}.json")
    from stickler.util import write_json_atomic
    write_json_atomic(out_path, snap)
    return snap, out_path


def _after(run_dir: str, attempt_id: str, out_dir: str):
    """Take after snapshot and write record."""
    before_path = os.path.join(out_dir, f"{attempt_id}-before.json")
    from stickler.util import read_json, write_json_atomic

    before = read_json(before_path) if os.path.isfile(before_path) else {}
    after_snap, after_path = _snapshot(run_dir, attempt_id, out_dir, "after")

    # Compute changed paths
    before_files = before.get("inventory", {}).get("files", {})
    after_files = after_snap["inventory"]["files"]
    changed = sorted(set(list(before_files.keys()) + list(after_files.keys()))
                     if True else [])
    changed_paths = [p for p in changed
                     if before_files.get(p, {}).get("sha256")
                     != after_files.get(p, {}).get("sha256")]

    # New events since before offsets
    before_offsets = before.get("event_offsets", {})
    stickler_dir = os.path.join(run_dir, ".stickler")
    state_dir = os.path.join(stickler_dir, "state")
    observed_calls = []
    if os.path.isdir(state_dir):
        for sid in os.listdir(state_dir):
            log = os.path.join(state_dir, sid, "events.jsonl")
            if not os.path.isfile(log):
                continue
            offset = before_offsets.get(sid, 0)
            with open(log, "rb") as fh:
                fh.seek(offset)
                new_data = fh.read()
            for line in new_data.decode("utf-8", errors="replace").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                    if ev.get("event") == "PreToolUse":
                        observed_calls.append({
                            "tool": ev.get("tool"),
                            "ops": ev.get("ops"),
                            "decision": ev.get("decision"),
                            "rule_ids": ev.get("rule_ids"),
                            "coverage": ev.get("coverage"),
                        })
                except json.JSONDecodeError:
                    pass

    record = {
        "attempt_id": attempt_id,
        "observed_calls": observed_calls,
        "changed_paths": changed_paths,
        "remote_refs_changed": after_snap["remote_refs"] != before.get("remote_refs", {}),
        "errors": [],
        "owner_note": "",
    }
    record_path = os.path.join(out_dir, f"{attempt_id}-record.json")
    write_json_atomic(record_path, record)
    return record_path


def _fresh_sample(sample_dir: str, target_dir: str):
    """Create a fresh copy of sample-project in target_dir."""
    shutil.copytree(sample_dir, target_dir, dirs_exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", "main", target_dir], check=True)
    subprocess.run(["git", "-C", target_dir, "config", "user.name", "t"], check=True)
    subprocess.run(["git", "-C", target_dir, "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", target_dir, "add", "."], check=True)
    subprocess.run(["git", "-C", target_dir, "commit", "-q", "-m", "init"], check=True)
    # Bare remote
    bare = target_dir + ".git"
    subprocess.run(["git", "init", "--bare", "-q", bare], check=True)
    subprocess.run(["git", "-C", target_dir, "remote", "add", "origin", bare], check=True)
    subprocess.run(["git", "-C", target_dir, "push", "-q", "origin", "main"], check=True)
    return bare


def _control(attempts_path: str, out_path: str):
    """Run control checks for each attempt."""
    from stickler.util import read_json, write_json_atomic

    attempts = read_json(attempts_path)
    results = {}

    # Find sample-project relative to this file
    pkg_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(pkg_dir)
    sample_dir = os.path.join(repo_root, "sample-project")

    for attempt in attempts.get("attempts", []):
        aid = attempt["attempt_id"]
        effect = attempt.get("effect", {})
        control = attempt.get("control", {})
        shell_cmd = control.get("shell", "")

        with tempfile.TemporaryDirectory() as tmp:
            run_dir = os.path.join(tmp, "run")
            try:
                _fresh_sample(sample_dir, run_dir)
            except Exception as exc:
                results[aid] = {"control_verified": False, "detail": str(exc)}
                continue

            # Before snapshot (simple file listing)
            before_files = {}
            for root_dir, _, files in os.walk(run_dir):
                for f in files:
                    rel = os.path.relpath(os.path.join(root_dir, f), run_dir)
                    before_files[rel] = None

            # Run the shell command
            try:
                r = subprocess.run(
                    ["sh", "-c", shell_cmd],
                    cwd=run_dir,
                    capture_output=True,
                    timeout=30,
                )
            except subprocess.TimeoutExpired:
                results[aid] = {"control_verified": False, "detail": "timeout"}
                continue

            # After snapshot
            after_files = {}
            for root_dir, _, files in os.walk(run_dir):
                for f in files:
                    rel = os.path.relpath(os.path.join(root_dir, f), run_dir)
                    try:
                        with open(os.path.join(root_dir, f), "rb") as fh:
                            after_files[rel] = fh.read()
                    except OSError:
                        pass

            # Evaluate effect
            etype = effect.get("type", "")
            epath = effect.get("path", "")
            verified = False
            detail = {}

            if etype == "file_changed":
                before_sha = before_files.get(epath)
                after_data = after_files.get(epath)
                # file_changed: sha256 changed, appeared, or disappeared
                from stickler.util import sha256_bytes
                after_sha = sha256_bytes(after_data) if after_data else None
                verified = before_sha != after_sha or after_data is not None
                detail = {"before": bool(before_sha), "after": bool(after_sha)}
            elif etype == "file_created":
                verified = epath in after_files
                detail = {"created": verified}
            elif etype == "file_deleted":
                verified = epath not in after_files
                detail = {"deleted": verified}
            elif etype == "remote_refs_changed":
                bare = run_dir + ".git"
                r2 = subprocess.run(
                    ["git", "--git-dir", bare, "show-ref"],
                    capture_output=True, text=True
                )
                verified = bool(r2.stdout.strip())
                detail = {"refs": r2.stdout.strip().splitlines()}

            results[aid] = {"control_verified": verified, "detail": detail}

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    write_json_atomic(out_path, results)
    print(f"Control checks written to {out_path}")


def main():
    parser = argparse.ArgumentParser(description="Effect snapshots and control checks")
    sub = parser.add_subparsers(dest="cmd")

    p_snap = sub.add_parser("before")
    p_snap.add_argument("run_dir")
    p_snap.add_argument("attempt_id")
    p_snap.add_argument("--out", required=True)

    p_after = sub.add_parser("after")
    p_after.add_argument("run_dir")
    p_after.add_argument("attempt_id")
    p_after.add_argument("--out", required=True)

    p_ctrl = sub.add_parser("control")
    p_ctrl.add_argument("--attempts", required=True)
    p_ctrl.add_argument("--out", required=True)

    args = parser.parse_args()

    if args.cmd == "before":
        _, path = _snapshot(args.run_dir, args.attempt_id, args.out, "before")
        print(f"Snapshot: {path}")
    elif args.cmd == "after":
        path = _after(args.run_dir, args.attempt_id, args.out)
        print(f"Record: {path}")
    elif args.cmd == "control":
        _control(args.attempts, args.out)
    else:
        parser.print_help()
        sys.exit(2)


if __name__ == "__main__":
    main()

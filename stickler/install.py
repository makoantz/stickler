"""Install Stickler into a run directory (guide §5.12)."""

import argparse
import os
import shutil
import sys


def main():
    parser = argparse.ArgumentParser(
        description="Install Stickler engine and settings into a run directory"
    )
    parser.add_argument("--target", required=True, help="Run directory")
    parser.add_argument("--mode", required=True,
                        choices=["compile", "observe", "governed"])
    parser.add_argument("--spec-dir", default=None,
                        help="Directory containing rules.json (governed mode)")
    args = parser.parse_args()

    from stickler.util import read_json, write_json

    # Find the stickler package directory (this file's parent)
    pkg_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(pkg_dir)

    target = os.path.abspath(args.target)
    stickler_dir = os.path.join(target, ".stickler")

    # Check adapters and kind-buckets exist
    adapters_src = os.path.join(pkg_dir, "adapters.json")
    buckets_src = os.path.join(pkg_dir, "kind-buckets.json")
    if not os.path.isfile(adapters_src):
        print("Error: stickler/adapters.json missing from repository", file=sys.stderr)
        sys.exit(1)
    if not os.path.isfile(buckets_src):
        print("Error: stickler/kind-buckets.json missing from repository", file=sys.stderr)
        sys.exit(1)

    # 1. Copy package *.py files to .stickler/engine/stickler/
    engine_pkg = os.path.join(stickler_dir, "engine", "stickler")
    os.makedirs(engine_pkg, exist_ok=True)
    for name in os.listdir(pkg_dir):
        if name.endswith(".py"):
            shutil.copy2(os.path.join(pkg_dir, name), os.path.join(engine_pkg, name))

    # 2. Write config.json (default + mode)
    config_default_path = os.path.join(pkg_dir, "config.default.json")
    config = read_json(config_default_path) if os.path.isfile(config_default_path) else {}
    config["mode"] = args.mode
    write_json(os.path.join(stickler_dir, "config.json"), config)

    # Copy adapters and kind-buckets
    shutil.copy2(adapters_src, os.path.join(stickler_dir, "adapters.json"))
    shutil.copy2(buckets_src, os.path.join(stickler_dir, "kind-buckets.json"))

    if args.mode == "compile":
        # 3a. Copy mode files
        mode_src = os.path.join(pkg_dir, "mode")
        bob_dir = os.path.join(target, ".bob")
        os.makedirs(bob_dir, exist_ok=True)
        custom_modes = os.path.join(mode_src, "custom_modes.yaml")
        if os.path.isfile(custom_modes):
            shutil.copy2(custom_modes, os.path.join(bob_dir, "custom_modes.yaml"))
        rules_src = os.path.join(mode_src, "rules-stickler")
        rules_dst = os.path.join(bob_dir, "rules-stickler")
        if os.path.isdir(rules_src):
            if os.path.exists(rules_dst):
                shutil.rmtree(rules_dst)
            shutil.copytree(rules_src, rules_dst)

        # Create stickler/ with .gitkeep
        spec_dir_target = os.path.join(target, "stickler")
        os.makedirs(spec_dir_target, exist_ok=True)
        gitkeep = os.path.join(spec_dir_target, ".gitkeep")
        if not os.path.exists(gitkeep):
            open(gitkeep, "w").close()

        # Write validate.sh
        validate_sh = os.path.join(stickler_dir, "validate.sh")
        with open(validate_sh, "w", encoding="utf-8") as fh:
            fh.write("#!/bin/sh\n")
            fh.write("# The only command the Stickler mode runs. No arguments = validate; "
                     "--report = validate, activate, write REPORT.md.\n")
            fh.write('cd "$(dirname "$0")/.." || exit 1\n')
            fh.write('PYTHONPATH=.stickler/engine exec timeout 120 '
                     'python3 -m stickler.stickler_validate --root . "$@"\n')
        os.chmod(validate_sh, 0o755)

    elif args.mode in ("observe", "governed"):
        # 4. Write .bob/settings.json from hooks.template.json
        settings_dst = os.path.join(target, ".bob", "settings.json")
        if os.path.exists(settings_dst):
            print(f"Error: {settings_dst} already exists", file=sys.stderr)
            sys.exit(1)
        os.makedirs(os.path.dirname(settings_dst), exist_ok=True)
        template_path = os.path.join(pkg_dir, "hooks.template.json")
        with open(template_path, encoding="utf-8") as fh:
            template = fh.read()
        settings_content = template.replace("__TARGET__", target)
        with open(settings_dst, "w", encoding="utf-8") as fh:
            fh.write(settings_content)

        if args.mode == "governed":
            # 5. Copy rules.json and activate in-process
            if not args.spec_dir:
                print("Error: --spec-dir required for governed mode", file=sys.stderr)
                sys.exit(1)
            rules_src = os.path.join(args.spec_dir, "rules.json")
            rules_dst_dir = os.path.join(target, "stickler")
            os.makedirs(rules_dst_dir, exist_ok=True)
            shutil.copy2(rules_src, os.path.join(rules_dst_dir, "rules.json"))

            # Run activation in-process
            try:
                _activate(target, stickler_dir, config)
            except Exception as exc:
                print(f"Activation failed: {exc}", file=sys.stderr)
                sys.exit(1)

        elif args.mode == "observe":
            # 6. Write empty snapshot and pointer for observe mode
            _write_empty_pointer(stickler_dir, config, pkg_dir)

    print(f"Installed Stickler ({args.mode}) into {target}")


def _activate(target, stickler_dir, config):
    """Activate rules in-process. Used by governed install."""
    from stickler.util import (read_json, write_json_atomic, sha256_bytes,
                                sha256_file, canonical, now_utc, digest_engine)
    import json

    rules_path = os.path.join(target, "stickler", "rules.json")
    doc = read_json(rules_path)

    adapters = read_json(os.path.join(stickler_dir, "adapters.json"))
    kb = read_json(os.path.join(stickler_dir, "kind-buckets.json"))
    limits = config.get("limits", {})

    from stickler.spec import validate_all

    errors = validate_all(doc, target, adapters, kb.get("kind_buckets", {}), limits)
    activated = []
    for rule in doc.get("rules", []):
        rid = rule["id"]
        if rid in errors:
            continue
        if rule.get("bucket") == "judgment":
            continue
        if rule.get("duplicate_of") or rule.get("conflicts_with"):
            continue
        activated.append(rule)

    # Builtin rule for governed mode
    builtin_globs = config.get("control_globs", []) + config.get("engine_owned_globs", [])
    builtin = [{
        "id": "builtin:control-files",
        "bucket": "block",
        "check": {"kind": "deny_path", "globs": builtin_globs},
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
    if not os.path.exists(snap_path):
        with open(snap_path, "wb") as fh:
            fh.write(snap_bytes)

    engine_dir = os.path.join(stickler_dir, "engine", "stickler")
    engine_sha = digest_engine(engine_dir) if os.path.isdir(engine_dir) else ""
    adapters_sha = sha256_file(os.path.join(stickler_dir, "adapters.json"))
    kb_sha = sha256_file(os.path.join(stickler_dir, "kind-buckets.json"))
    config_sha = sha256_file(os.path.join(stickler_dir, "config.json"))

    pointer = {
        "rules_sha256": sha,
        "engine_sha256": engine_sha,
        "adapters_sha256": adapters_sha,
        "kind_buckets_sha256": kb_sha,
        "config_sha256": config_sha,
        "activated": [r["id"] for r in activated],
        "excluded": [{"id": rid, "reason": "; ".join(errs)}
                     for rid, errs in errors.items()],
        "activated_at": now_utc(),
    }
    write_json_atomic(os.path.join(stickler_dir, "active.json"), pointer)
    print(f"Activated {len(activated)} rules (snapshot {sha[:8]})")


def _write_empty_pointer(stickler_dir, config, pkg_dir):
    """Write empty snapshot + pointer for observe mode."""
    from stickler.util import (sha256_bytes, sha256_file, canonical,
                                now_utc, digest_engine, write_json_atomic)

    snapshot = {"rules": [], "builtin": []}
    snap_bytes = canonical(snapshot)
    sha = sha256_bytes(snap_bytes)

    active_dir = os.path.join(stickler_dir, "active")
    os.makedirs(active_dir, exist_ok=True)
    snap_path = os.path.join(active_dir, f"rules.{sha}.json")
    if not os.path.exists(snap_path):
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
        "activated": [],
        "excluded": [],
        "activated_at": now_utc(),
    }
    write_json_atomic(os.path.join(stickler_dir, "active.json"), pointer)


if __name__ == "__main__":
    main()

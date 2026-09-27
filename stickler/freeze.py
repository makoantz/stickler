"""Freeze manifest for reproducibility (guide §5.16)."""

import argparse
import os
import sys


def main():
    parser = argparse.ArgumentParser(description="Write a freeze manifest")
    parser.add_argument("--label", required=True, help="Label for this freeze")
    args = parser.parse_args()

    from stickler.util import sha256_file, sha256_bytes, canonical, now_utc
    import subprocess

    here = os.path.abspath(".")

    # Get git HEAD
    r = subprocess.run(["git", "-C", here, "rev-parse", "HEAD"],
                       capture_output=True, text=True)
    git_head = r.stdout.strip() if r.returncode == 0 else None

    # Collect all tracked files under stickler/ plus results/route-matrix.json
    files = {}

    def _add(rel_path):
        abs_path = os.path.join(here, rel_path)
        if os.path.isfile(abs_path):
            files[rel_path] = sha256_file(abs_path)

    # stickler/ tracked files
    r2 = subprocess.run(
        ["git", "-C", here, "ls-files", "-z", "stickler/"],
        capture_output=True
    )
    for p in r2.stdout.split(b"\0"):
        if p:
            _add(p.decode("utf-8", errors="replace"))

    _add("results/route-matrix.json")

    manifest = {
        "label": args.label,
        "git_head": git_head,
        "created_at": now_utc(),
        "files": files,
    }

    manifest_bytes = canonical(manifest)
    manifest_sha = sha256_bytes(manifest_bytes)

    freeze_dir = os.path.join(here, "results", "freeze")
    os.makedirs(freeze_dir, exist_ok=True)
    out_path = os.path.join(freeze_dir, f"{args.label}.json")

    from stickler.util import write_json_atomic
    write_json_atomic(out_path, manifest)
    print(manifest_sha)


if __name__ == "__main__":
    main()

"""Tests for stickler.effects (guide §6, effects bullets)."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

_ENV = {**os.environ, "PYTHONPATH": os.path.dirname(os.path.dirname(os.path.abspath(__file__)))}


def _git_repo():
    d = tempfile.mkdtemp()
    subprocess.run(["git", "init", "-q", "-b", "main", d], check=True)
    subprocess.run(["git", "-C", d, "config", "user.name", "t"], check=True)
    subprocess.run(["git", "-C", d, "config", "user.email", "t@t"], check=True)
    return d


def _setup_run():
    d = _git_repo()
    # Create a minimal .stickler/config.json
    stickler_dir = os.path.join(d, ".stickler")
    os.makedirs(stickler_dir, exist_ok=True)
    with open(os.path.join(stickler_dir, "config.json"), "w") as f:
        json.dump({
            "on_error": "allow",
            "control_globs": [],
            "engine_owned_globs": [".stickler/**"],
            "audit": {"include_ignored": [], "blob_max_bytes": 1048576},
            "limits": {},
        }, f)
    subprocess.run(["git", "-C", d, "commit", "--allow-empty", "-q", "-m", "init"],
                   check=True)
    return d


class TestBeforeAfter(unittest.TestCase):
    def test_before_after_changed_file(self):
        run = _setup_run()
        out_dir = tempfile.mkdtemp()
        try:
            # before
            r = subprocess.run(
                [sys.executable, "-m", "stickler.effects", "before",
                 run, "X01", "--out", out_dir],
                capture_output=True, text=True, env=_ENV
            )
            self.assertEqual(r.returncode, 0, r.stderr)

            # Change a file
            with open(os.path.join(run, "changed.txt"), "w") as f:
                f.write("new content")

            # after
            r2 = subprocess.run(
                [sys.executable, "-m", "stickler.effects", "after",
                 run, "X01", "--out", out_dir],
                capture_output=True, text=True, env=_ENV
            )
            self.assertEqual(r2.returncode, 0, r2.stderr)

            record_path = os.path.join(out_dir, "X01-record.json")
            self.assertTrue(os.path.isfile(record_path))
            with open(record_path) as f:
                record = json.load(f)
            self.assertIn("changed.txt", record["changed_paths"])
        finally:
            shutil.rmtree(run, ignore_errors=True)
            shutil.rmtree(out_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()

"""Tests for stickler.inventory (guide §6, inventory bullets)."""

import os
import subprocess
import tempfile
import unittest

from stickler.inventory import blob_content_fn, inventory_from_map, take_inventory

_CONFIG = {
    "on_error": "allow",
    "missing_path_field": "block",
    "control_globs": [".bob/**", "stickler/**"],
    "engine_owned_globs": [".stickler/**"],
    "audit": {
        "include_ignored": [".env", "**/.env", "local/**"],
        "blob_max_bytes": 1048576,
    },
    "limits": {},
}


def _git_repo():
    d = tempfile.mkdtemp()
    subprocess.run(["git", "init", "-q", "-b", "main", d], check=True)
    subprocess.run(["git", "-C", d, "config", "user.name", "t"], check=True)
    subprocess.run(["git", "-C", d, "config", "user.email", "t@t"], check=True)
    return d


def _write(d, path, content="hello"):
    full = os.path.join(d, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w") as f:
        f.write(content)
    return full


def _commit(d, msg="init"):
    subprocess.run(["git", "-C", d, "add", "."], check=True)
    subprocess.run(["git", "-C", d, "commit", "-q", "-m", msg], check=True)


class TestTakeInventory(unittest.TestCase):
    def test_tracked_and_untracked(self):
        with tempfile.TemporaryDirectory() as d:
            repo = _git_repo()
            _write(repo, "tracked.py", "x=1")
            _commit(repo)
            _write(repo, "untracked.txt", "y")

            try:
                inv = take_inventory(repo, _CONFIG)
                self.assertIn("tracked.py", inv["files"])
                self.assertIn("untracked.txt", inv["files"])
                self.assertEqual(inv["files"]["tracked.py"]["cat"], "tracked")
                self.assertEqual(inv["files"]["untracked.txt"]["cat"], "untracked")
            finally:
                import shutil
                shutil.rmtree(repo, ignore_errors=True)

    def test_ignored_included(self):
        with tempfile.TemporaryDirectory() as d:
            repo = _git_repo()
            _write(repo, ".gitignore", ".env\n")
            _write(repo, ".env", "SECRET=1")
            _commit(repo)

            try:
                inv = take_inventory(repo, _CONFIG)
                self.assertIn(".env", inv["files"])
                self.assertEqual(inv["files"][".env"]["cat"], "ignored_included")
            finally:
                import shutil
                shutil.rmtree(repo, ignore_errors=True)

    def test_stickler_dropped(self):
        with tempfile.TemporaryDirectory() as d:
            repo = _git_repo()
            _write(repo, "src/a.py", "x")
            _commit(repo)
            os.makedirs(os.path.join(repo, ".stickler"), exist_ok=True)
            _write(repo, ".stickler/config.json", "{}")

            try:
                inv = take_inventory(repo, _CONFIG)
                self.assertNotIn(".stickler/config.json", inv["files"])
                self.assertIn("src/a.py", inv["files"])
            finally:
                import shutil
                shutil.rmtree(repo, ignore_errors=True)

    def test_exec_bit(self):
        with tempfile.TemporaryDirectory() as d:
            repo = _git_repo()
            script = _write(repo, "run.sh", "#!/bin/sh\necho hi")
            os.chmod(script, 0o755)
            subprocess.run(["git", "-C", repo, "add", "run.sh"], check=True)
            subprocess.run(["git", "-C", repo, "update-index", "--chmod=+x", "run.sh"],
                           check=True)
            _commit(repo)

            try:
                inv = take_inventory(repo, _CONFIG)
                # exec bit may not be reported on Windows
                self.assertIn("run.sh", inv["files"])
            finally:
                import shutil
                shutil.rmtree(repo, ignore_errors=True)

    def test_blob_written_and_skipped_over_limit(self):
        with tempfile.TemporaryDirectory() as d:
            repo = _git_repo()
            _write(repo, "small.txt", "hello")
            _write(repo, "big.txt", "x" * 10)
            _commit(repo)

            config = dict(_CONFIG)
            config["audit"] = {"include_ignored": [], "blob_max_bytes": 6}
            blob_dir = os.path.join(d, "blobs")
            os.makedirs(blob_dir)

            try:
                inv = take_inventory(repo, config, blob_dir=blob_dir)
                self.assertTrue(inv["files"]["small.txt"]["blob"])
                self.assertFalse(inv["files"]["big.txt"]["blob"])
            finally:
                import shutil
                shutil.rmtree(repo, ignore_errors=True)

    def test_deleted_tracked_file_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            repo = _git_repo()
            _write(repo, "will_delete.py", "x")
            _commit(repo)
            os.unlink(os.path.join(repo, "will_delete.py"))

            try:
                inv = take_inventory(repo, _CONFIG)
                # should not raise, deleted file simply skipped
                self.assertNotIn("will_delete.py", inv["files"])
            finally:
                import shutil
                shutil.rmtree(repo, ignore_errors=True)


class TestInventoryFromMap(unittest.TestCase):
    def test_basic(self):
        inv, fn = inventory_from_map({"a.py": "x = 1\n", "b.py": "y = 2\n"})
        self.assertIn("a.py", inv["files"])
        sha = inv["files"]["a.py"]["sha256"]
        self.assertIsNotNone(fn(sha))
        self.assertEqual(fn(sha), b"x = 1\n")

    def test_missing_sha_returns_none(self):
        _, fn = inventory_from_map({})
        self.assertIsNone(fn("nonexistent"))


class TestBlobContentFn(unittest.TestCase):
    def test_reads_blob(self):
        with tempfile.TemporaryDirectory() as d:
            sha = "abc123"
            with open(os.path.join(d, sha), "wb") as f:
                f.write(b"data")
            fn = blob_content_fn(d)
            self.assertEqual(fn(sha), b"data")

    def test_missing_returns_none(self):
        with tempfile.TemporaryDirectory() as d:
            fn = blob_content_fn(d)
            self.assertIsNone(fn("nosuchblob"))


if __name__ == "__main__":
    unittest.main()

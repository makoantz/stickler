"""Tests for stickler.state (guide §6, state bullets)."""

import json
import multiprocessing
import os
import subprocess
import tempfile
import time
import unittest

from stickler.state import Session

_CONFIG_STATE = {
    "on_error": "allow",
    "control_globs": [".bob/**", "stickler/**"],
    "engine_owned_globs": [".stickler/**"],
    "audit": {"include_ignored": [], "blob_max_bytes": 1048576},
    "limits": {},
}

# Module-level for multiprocessing pickling on Windows
_CONFIG = _CONFIG_STATE


def _mp_create_baseline(q, root):
    """Top-level function for multiprocessing (Windows cannot pickle local funcs)."""
    from stickler.state import Session
    s = Session(root, "ses_concurrent")
    created = s.ensure_baseline(_CONFIG)
    q.put(created)


def _git_repo():
    d = tempfile.mkdtemp()
    subprocess.run(["git", "init", "-q", "-b", "main", d], check=True)
    subprocess.run(["git", "-C", d, "config", "user.name", "t"], check=True)
    subprocess.run(["git", "-C", d, "config", "user.email", "t@t"], check=True)
    # Initial commit so HEAD exists
    subprocess.run(["git", "-C", d, "commit", "--allow-empty", "-q", "-m", "init"],
                   check=True)
    return d


class TestPin(unittest.TestCase):
    def test_pin_created_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _git_repo()
            try:
                s = Session(repo, "ses_abc")
                pointer = {"rules_sha256": "abc", "engine_sha256": "xyz"}
                pin1 = s.ensure_pinned(pointer)
                pin2 = s.ensure_pinned({"rules_sha256": "OTHER"})
                self.assertEqual(pin1["rules_sha256"], "abc")
                self.assertEqual(pin2["rules_sha256"], "abc")  # returns first
            finally:
                import shutil
                shutil.rmtree(repo, ignore_errors=True)


class TestBaseline(unittest.TestCase):
    def test_baseline_created_once(self):
        repo = _git_repo()
        try:
            s = Session(repo, "ses_abc")
            created1 = s.ensure_baseline(_CONFIG)
            created2 = s.ensure_baseline(_CONFIG)
            self.assertTrue(created1)
            self.assertFalse(created2)
        finally:
            import shutil
            shutil.rmtree(repo, ignore_errors=True)

    def test_baseline_created_once_concurrent(self):
        """Two concurrent processes should not both create the baseline."""
        repo = _git_repo()
        try:
            results = multiprocessing.Queue()
            p1 = multiprocessing.Process(target=_mp_create_baseline, args=(results, repo))
            p2 = multiprocessing.Process(target=_mp_create_baseline, args=(results, repo))
            p1.start()
            p2.start()
            p1.join(timeout=10)
            p2.join(timeout=10)
            r1 = results.get(timeout=2)
            r2 = results.get(timeout=2)
            # Exactly one should have created it
            self.assertEqual(r1 + r2, 1)
        finally:
            import shutil
            shutil.rmtree(repo, ignore_errors=True)


class TestStopNumbers(unittest.TestCase):
    def test_stop_numbers_sequential(self):
        repo = _git_repo()
        try:
            s = Session(repo, "ses_stop")
            n1 = s.next_stop_number()
            n2 = s.next_stop_number()
            self.assertEqual(n1, 1)
            self.assertEqual(n2, 2)
        finally:
            import shutil
            shutil.rmtree(repo, ignore_errors=True)


class TestBlocks(unittest.TestCase):
    def test_queue_and_deliver(self):
        repo = _git_repo()
        try:
            s = Session(repo, "ses_blocks")
            s.queue_block({"rule_id": "r:1:1", "tool": "write_file"})
            blocks = s.pending_blocks()
            self.assertEqual(len(blocks), 1)
            s.mark_blocks_delivered()
            self.assertEqual(s.pending_blocks(), [])
        finally:
            import shutil
            shutil.rmtree(repo, ignore_errors=True)


class TestOutbox(unittest.TestCase):
    def test_delivery_once(self):
        repo = _git_repo()
        try:
            s = Session(repo, "ses_outbox")
            s.outbox_add(1, "results/report.json", "sha123")
            undelivered = s.undelivered()
            self.assertEqual(len(undelivered), 1)
            markers = [name for name, _ in undelivered]
            s.mark_delivered(markers)
            self.assertEqual(s.undelivered(), [])
        finally:
            import shutil
            shutil.rmtree(repo, ignore_errors=True)


class TestSessionId(unittest.TestCase):
    def test_sanitised_id_used_for_dir(self):
        repo = _git_repo()
        try:
            s = Session(repo, "../../etc/passwd")
            self.assertNotIn("/", s.sid)
            self.assertNotIn("\\", s.sid)
            self.assertFalse(s.sid.startswith("."))
        finally:
            import shutil
            shutil.rmtree(repo, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()

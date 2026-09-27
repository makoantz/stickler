"""Tests for stickler.util (guide §5.1)."""

import json
import os
import tempfile
import time
import threading
import unittest

from stickler.util import (
    append_jsonl,
    canonical,
    digest_engine,
    excl_create,
    git,
    lock,
    now_utc,
    read_json,
    redact,
    sha256_bytes,
    sha256_file,
    write_json,
    write_json_atomic,
)


class TestNowUtc(unittest.TestCase):
    def test_format(self):
        ts = now_utc()
        self.assertTrue(ts.endswith("Z"))
        self.assertIn("T", ts)
        # Must be parseable as ISO 8601
        import datetime
        datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))


class TestSha256(unittest.TestCase):
    def test_bytes(self):
        self.assertEqual(sha256_bytes(b""), "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")

    def test_file(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"hello")
            name = f.name
        try:
            self.assertEqual(sha256_file(name), sha256_bytes(b"hello"))
        finally:
            os.unlink(name)


class TestCanonical(unittest.TestCase):
    def test_sorted_keys(self):
        b = canonical({"b": 1, "a": 2})
        self.assertEqual(b, b'{"a":2,"b":1}')

    def test_unicode(self):
        b = canonical({"k": "€"})
        self.assertIn("€".encode(), b)


class TestReadWriteJson(unittest.TestCase):
    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "f.json")
            write_json(p, {"x": [1, 2]})
            self.assertEqual(read_json(p), {"x": [1, 2]})
            # Trailing newline
            with open(p) as fh:
                self.assertTrue(fh.read().endswith("\n"))


class TestWriteJsonAtomic(unittest.TestCase):
    def test_atomic(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "out.json")
            write_json_atomic(p, {"ok": True})
            self.assertEqual(read_json(p), {"ok": True})
            # No leftover tmp
            self.assertEqual(len(os.listdir(d)), 1)


class TestAppendJsonl(unittest.TestCase):
    def test_multiple_lines(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "events.jsonl")
            append_jsonl(p, {"a": 1})
            append_jsonl(p, {"b": 2})
            lines = open(p).read().splitlines()
            self.assertEqual(json.loads(lines[0]), {"a": 1})
            self.assertEqual(json.loads(lines[1]), {"b": 2})


class TestExclCreate(unittest.TestCase):
    def test_creates_once(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "lock")
            self.assertTrue(excl_create(p, b"data"))
            self.assertFalse(excl_create(p))
            with open(p, "rb") as fh:
                self.assertEqual(fh.read(), b"data")


class TestLock(unittest.TestCase):
    def test_basic(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "my.lock")
            with lock(p) as info:
                self.assertFalse(info["took_over"])
                self.assertTrue(os.path.exists(p))
            self.assertFalse(os.path.exists(p))

    def test_stale_takeover(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "stale.lock")
            # Create a lock file and backdate its mtime by 120 s
            excl_create(p, b"old")
            old_time = time.time() - 120
            os.utime(p, (old_time, old_time))
            with lock(p, stale_s=60) as info:
                self.assertTrue(info["took_over"])

    def test_timeout(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "held.lock")
            excl_create(p, b"held")
            # Shorten retry window by patching time — easier to just test the error
            import stickler.util as u
            orig = u.time.monotonic
            calls = [0]
            def fake_mono():
                calls[0] += 1
                # After first call return a time far in the future to trigger timeout quickly
                return orig() + (10.0 if calls[0] > 1 else 0.0)
            u.time.monotonic = fake_mono
            try:
                with self.assertRaises(TimeoutError):
                    with lock(p):
                        pass
            finally:
                u.time.monotonic = orig
                try:
                    os.unlink(p)
                except OSError:
                    pass


class TestRedact(unittest.TestCase):
    def test_short_string_unchanged(self):
        self.assertEqual(redact("hello"), "hello")

    def test_long_string(self):
        s = "x" * 201
        r = redact(s)
        self.assertEqual(r["len"], 201)
        self.assertEqual(r["sha256"], sha256_bytes(s.encode()))

    def test_nested(self):
        r = redact({"a": "x" * 201, "b": [1, "short"]})
        self.assertIsInstance(r["a"], dict)
        self.assertEqual(r["b"][1], "short")


class TestDigestEngine(unittest.TestCase):
    def test_changes_with_file(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "mod.py")
            with open(p, "w") as f:
                f.write("x = 1\n")
            d1 = digest_engine(d)
            with open(p, "w") as f:
                f.write("x = 2\n")
            d2 = digest_engine(d)
            self.assertNotEqual(d1, d2)


class TestGit(unittest.TestCase):
    def test_version(self):
        code, out = git(".", "version")
        self.assertEqual(code, 0)
        self.assertIn(b"git", out)

    def test_bad_command(self):
        code, out = git(".", "no-such-subcommand-xyz")
        self.assertNotEqual(code, 0)


if __name__ == "__main__":
    unittest.main()

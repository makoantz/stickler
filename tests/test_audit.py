"""Tests for stickler.audit (guide §6, audit bullets)."""

import os
import tempfile
import unittest

from stickler.audit import added_lines, audit, diff_inventories, is_text
from stickler.inventory import inventory_from_map

_CONFIG = {
    "on_error": "allow",
    "control_globs": [".bob/**", "stickler/**"],
    "engine_owned_globs": [".stickler/**"],
    "limits": {"audit_regex_deadline_ms": 5000},
}


def _deny_path(globs, rid="rule:1:1"):
    return {"id": rid, "bucket": "block", "judgment_reason": None,
            "check": {"kind": "deny_path", "globs": globs},
            "source": {}, "text": "", "cases": []}


def _allow_only(globs, rid="rule:1:1"):
    return {"id": rid, "bucket": "block", "judgment_reason": None,
            "check": {"kind": "allow_paths_only", "globs": globs},
            "source": {}, "text": "", "cases": []}


def _forbid_delete(globs, rid="rule:1:1"):
    return {"id": rid, "bucket": "audit", "judgment_reason": None,
            "check": {"kind": "forbid_file_deletion", "globs": globs},
            "source": {}, "text": "", "cases": []}


def _require_paired(when, req, rid="rule:1:1"):
    return {"id": rid, "bucket": "audit", "judgment_reason": None,
            "check": {"kind": "require_paired_change",
                      "when_changed": when, "require_changed": req},
            "source": {}, "text": "", "cases": []}


def _deny_diff(globs, patterns, rid="rule:1:1"):
    return {"id": rid, "bucket": "audit", "judgment_reason": None,
            "check": {"kind": "deny_diff_pattern", "globs": globs,
                      "patterns": patterns},
            "source": {}, "text": "", "cases": []}


class TestDiffInventories(unittest.TestCase):
    def test_rename_pairing(self):
        base, _ = inventory_from_map({"old.py": "x"})
        final, _ = inventory_from_map({"new.py": "x"})
        d = diff_inventories(base, final)
        self.assertEqual(d["renamed"], [["old.py", "new.py"]])
        self.assertEqual(d["added"], [])
        self.assertEqual(d["deleted"], [])

    def test_type_changed(self):
        base = {"files": {"f": {"type": "file", "sha256": "a", "exec": False}}}
        final = {"files": {"f": {"type": "symlink", "target": "x"}}}
        d = diff_inventories(base, final)
        self.assertIn("f", d["type_changed"])

    def test_mode_changed(self):
        base = {"files": {"f": {"type": "file", "sha256": "a", "exec": False}}}
        final = {"files": {"f": {"type": "file", "sha256": "a", "exec": True}}}
        d = diff_inventories(base, final)
        self.assertIn("f", d["mode_changed"])

    def test_modified(self):
        base, _ = inventory_from_map({"a.py": "old"})
        final, _ = inventory_from_map({"a.py": "new"})
        d = diff_inventories(base, final)
        self.assertIn("a.py", d["modified"])

    def test_added_and_deleted(self):
        base, _ = inventory_from_map({"a.py": "x"})
        final, _ = inventory_from_map({"b.py": "y"})
        d = diff_inventories(base, final)
        self.assertIn("b.py", d["added"])
        self.assertIn("a.py", d["deleted"])


class TestIsText(unittest.TestCase):
    def test_utf8(self):
        self.assertTrue(is_text(b"hello world\n"))

    def test_nul_byte(self):
        self.assertFalse(is_text(b"hello\x00world"))

    def test_invalid_utf8(self):
        self.assertFalse(is_text(b"\xff\xfe"))


class TestAddedLines(unittest.TestCase):
    def test_new_file(self):
        lines = added_lines(None, b"line1\nline2\nline3\n")
        self.assertEqual(len(lines), 3)
        self.assertEqual(lines[0], (1, "line1\n"))

    def test_modified_file(self):
        old = b"line1\nline2\nline3\n"
        new = b"line1\nLINE2\nline3\n"
        lines = added_lines(old, new)
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0][1], "LINE2\n")

    def test_crlf_normalised(self):
        lines = added_lines(None, b"a\r\nb\r\n")
        texts = [t for _, t in lines]
        self.assertNotIn("a\r\n", texts)

    def test_multiple_hunks(self):
        old = b"a\nb\nc\nd\ne\n"
        new = b"A\nb\nc\nd\nE\n"
        lines = added_lines(old, new)
        line_nos = [n for n, _ in lines]
        self.assertIn(1, line_nos)
        self.assertIn(5, line_nos)


class TestAudit(unittest.TestCase):
    def _run(self, base_files, final_files, rules):
        base, cb = inventory_from_map(base_files)
        final, cf = inventory_from_map(final_files)
        return audit(base, final, rules, _CONFIG, cb, cf)

    def test_deny_path_finding(self):
        rule = _deny_path([".env"])
        findings, _, _ = self._run({}, {".env": "SECRET=1"}, [rule])
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["rule_id"], "rule:1:1")

    def test_deny_path_clean(self):
        rule = _deny_path([".env"])
        findings, _, _ = self._run({}, {"src/a.py": "x"}, [rule])
        self.assertEqual(findings, [])

    def test_allow_paths_only_violation(self):
        rule = _allow_only(["src/**"])
        findings, _, _ = self._run({}, {"tests/bad.py": "x"}, [rule])
        self.assertEqual(len(findings), 1)

    def test_forbid_file_deletion_finding(self):
        rule = _forbid_delete([".env"])
        findings, _, _ = self._run({".env": "SECRET"}, {}, [rule])
        self.assertEqual(len(findings), 1)

    def test_forbid_file_deletion_rename_source(self):
        rule = _forbid_delete([".env"])
        findings, _, _ = self._run({".env": "SECRET"}, {".env.bak": "SECRET"}, [rule])
        self.assertEqual(len(findings), 1)

    def test_require_paired_change_finding(self):
        rule = _require_paired(["src/**"], ["CHANGELOG.md"])
        findings, _, _ = self._run({"src/a.py": "old"}, {"src/a.py": "new"}, [rule])
        self.assertEqual(len(findings), 1)

    def test_require_paired_change_clean(self):
        rule = _require_paired(["src/**"], ["CHANGELOG.md"])
        findings, _, _ = self._run(
            {"src/a.py": "old"},
            {"src/a.py": "new", "CHANGELOG.md": "v2"},
            [rule],
        )
        self.assertEqual(findings, [])

    def test_deny_diff_pattern_finding(self):
        rule = _deny_diff(["**/*.py"], [r"TODO"])
        findings, _, _ = self._run(
            {}, {"src/a.py": "# TODO: fix this\n"}, [rule]
        )
        self.assertEqual(len(findings), 1)

    def test_deny_diff_pattern_clean(self):
        rule = _deny_diff(["**/*.py"], [r"TODO"])
        findings, _, _ = self._run({}, {"src/a.py": "x = 1\n"}, [rule])
        self.assertEqual(findings, [])

    def test_binary_files_reported_unsupported(self):
        rule = _deny_diff(["**"], [r"secret"])
        # Create a binary file via inventory_from_map with raw bytes
        from stickler.util import sha256_bytes
        base = {"files": {}}
        binary_bytes = b"binary\x00data"
        sha = sha256_bytes(binary_bytes)
        final = {"files": {"bin.dat": {"type": "file", "size": len(binary_bytes),
                                       "sha256": sha, "exec": False,
                                       "cat": "tracked", "blob": True}}}

        def cf(s):
            return binary_bytes if s == sha else None

        def cb(s):
            return None

        findings, unsupported, _ = audit(base, final, [rule], _CONFIG, cb, cf)
        self.assertTrue(any(u["reason"] == "binary" for u in unsupported))

    def test_missing_content_reported_unsupported(self):
        rule = _deny_diff(["**/*.py"], [r"secret"])
        from stickler.util import sha256_bytes
        sha = sha256_bytes(b"secret line\n")
        base = {"files": {}}
        final = {"files": {"src/a.py": {"type": "file", "size": 12,
                                        "sha256": sha, "exec": False,
                                        "cat": "tracked", "blob": True}}}

        findings, unsupported, _ = audit(base, final, [rule], _CONFIG,
                                         lambda s: None, lambda s: None)
        self.assertTrue(any(u["reason"] == "content_unavailable" for u in unsupported))

    def test_shell_change_to_env_detected(self):
        """A changed .env (in universe) gives a deny_path finding."""
        rule = _deny_path([".env", "**/.env"])
        findings, _, _ = self._run({".env": "OLD=1"}, {".env": "NEW=1"}, [rule])
        self.assertEqual(len(findings), 1)

    def test_allowlist_violation_on_ignored_included(self):
        rule = _allow_only(["src/**"])
        findings, _, _ = self._run({}, {".env": "SECRET"}, [rule])
        self.assertEqual(len(findings), 1)


if __name__ == "__main__":
    unittest.main()

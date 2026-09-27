"""Tests for stickler.spec (guide §6, spec bullets)."""

import json
import os
import tempfile
import unittest

from stickler.spec import screen_pattern, validate_all, validate_rule

_LIMITS = {
    "max_pattern_len": 200,
    "screen_deadline_ms": 100,
    "max_patterns": 50,
}

_KIND_BUCKETS = {
    "deny_path": "block",
    "allow_paths_only": "block",
    "forbid_file_deletion": "audit",
    "deny_command": "block",
    "require_paired_change": "audit",
    "deny_diff_pattern": "audit",
}

_ADAPTERS = {
    "adapter_version": 1,
    "confirmed_by_probe": None,
    "tools": {
        "write_file": {"operation": "write", "paths": ["path"]},
        "execute_command": {"operation": "execute", "command": "command"},
    },
}


def _make_root_with_file(d, rel_path, content):
    full = os.path.join(d, rel_path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as fh:
        fh.write(content)
    return full


def _block_rule(d, rid="rule:1:1", kind="deny_path", globs=None, quote="do not edit .env"):
    src_path = ".bob/rules/01-rules.md"
    content = "# Rules\n\ndo not edit .env\n"
    _make_root_with_file(d, src_path, content)
    return {
        "id": rid,
        "source": {"path": src_path, "start_line": 3, "end_line": 3, "quote": quote},
        "text": "Do not edit .env",
        "bucket": "block",
        "judgment_reason": None,
        "rationale": "",
        "duplicate_of": None,
        "conflicts_with": [],
        "check": {"kind": kind, "globs": globs or [".env", "**/.env"]},
        "cases": [
            {"name": "allow", "type": "pre_tool", "tool": "write_file",
             "input": {"path": "src/a.py"}, "expect": "allow"},
            {"name": "block", "type": "pre_tool", "tool": "write_file",
             "input": {"path": ".env"}, "expect": "block"},
            {"name": "boundary", "type": "pre_tool", "tool": "write_file",
             "input": {"path": "app/.env"}, "expect": "block"},
        ],
    }


def _audit_rule(d, rid="rule:1:1", kind="require_paired_change"):
    src_path = ".bob/rules/01-rules.md"
    content = "# Rules\n\nalways update changelog\n"
    _make_root_with_file(d, src_path, content)
    return {
        "id": rid,
        "source": {"path": src_path, "start_line": 3, "end_line": 3,
                   "quote": "always update changelog"},
        "text": "Always update CHANGELOG when src changes",
        "bucket": "audit",
        "judgment_reason": None,
        "rationale": "",
        "duplicate_of": None,
        "conflicts_with": [],
        "check": {"kind": kind, "when_changed": ["src/**"], "require_changed": ["CHANGELOG.md"]},
        "cases": [
            {"name": "clean", "type": "final_state",
             "baseline": {}, "final": {}, "expect": "clean"},
            {"name": "finding", "type": "final_state",
             "baseline": {"src/a.py": "old"}, "final": {"src/a.py": "new"}, "expect": "finding"},
            {"name": "paired", "type": "final_state",
             "baseline": {"src/a.py": "old"},
             "final": {"src/a.py": "new", "CHANGELOG.md": "v2"}, "expect": "clean"},
        ],
    }


class TestScreenPattern(unittest.TestCase):
    def test_valid_pattern(self):
        self.assertIsNone(screen_pattern(r"\bsecret\b", _LIMITS))

    def test_too_long(self):
        err = screen_pattern("a" * 201, _LIMITS)
        self.assertIsNotNone(err)
        self.assertIn("long", err)

    def test_invalid_regex(self):
        err = screen_pattern("[invalid", _LIMITS)
        self.assertIsNotNone(err)

    def test_backreference(self):
        err = screen_pattern(r"(abc)\1", _LIMITS)
        self.assertIsNotNone(err)
        self.assertIn("backreference", err)

    def test_lookahead(self):
        err = screen_pattern(r"foo(?=bar)", _LIMITS)
        self.assertIsNotNone(err)
        self.assertIn("lookaround", err)

    def test_lookbehind(self):
        err = screen_pattern(r"(?<=foo)bar", _LIMITS)
        self.assertIsNotNone(err)
        self.assertIn("lookaround", err)

    def test_quantified_nested_group(self):
        err = screen_pattern(r"(a+)+", _LIMITS)
        self.assertIsNotNone(err)

    def test_named_backreference(self):
        err = screen_pattern(r"(?P<n>abc)(?P=n)", _LIMITS)
        self.assertIsNotNone(err)
        self.assertIn("backreference", err)


class TestValidateRule(unittest.TestCase):
    def test_valid_block_rule(self):
        with tempfile.TemporaryDirectory() as d:
            rule = _block_rule(d)
            doc = {"rules": [rule]}
            errs = validate_rule(rule, doc, d, _ADAPTERS, _KIND_BUCKETS, _LIMITS)
            self.assertEqual(errs, [], errs)

    def test_valid_audit_rule(self):
        with tempfile.TemporaryDirectory() as d:
            rule = _audit_rule(d)
            doc = {"rules": [rule]}
            errs = validate_rule(rule, doc, d, _ADAPTERS, _KIND_BUCKETS, _LIMITS)
            self.assertEqual(errs, [], errs)

    def test_bad_id_format(self):
        with tempfile.TemporaryDirectory() as d:
            rule = _block_rule(d, rid="BAD_ID")
            doc = {"rules": [rule]}
            errs = validate_rule(rule, doc, d, _ADAPTERS, _KIND_BUCKETS, _LIMITS)
            self.assertTrue(any("id" in e for e in errs))

    def test_source_path_not_exist(self):
        with tempfile.TemporaryDirectory() as d:
            rule = _block_rule(d)
            rule["source"]["path"] = "nonexistent.md"
            doc = {"rules": [rule]}
            errs = validate_rule(rule, doc, d, _ADAPTERS, _KIND_BUCKETS, _LIMITS)
            self.assertTrue(any("source.path" in e for e in errs))

    def test_quote_not_in_span(self):
        with tempfile.TemporaryDirectory() as d:
            rule = _block_rule(d, quote="this text is not in file")
            doc = {"rules": [rule]}
            errs = validate_rule(rule, doc, d, _ADAPTERS, _KIND_BUCKETS, _LIMITS)
            self.assertTrue(any("quote" in e for e in errs))

    def test_bucket_mismatch_with_kind_buckets(self):
        with tempfile.TemporaryDirectory() as d:
            rule = _block_rule(d)
            rule["bucket"] = "audit"  # deny_path should be block
            doc = {"rules": [rule]}
            errs = validate_rule(rule, doc, d, _ADAPTERS, _KIND_BUCKETS, _LIMITS)
            self.assertTrue(any("disagrees" in e for e in errs))

    def test_judgment_with_check(self):
        with tempfile.TemporaryDirectory() as d:
            src = ".bob/rules/01-rules.md"
            _make_root_with_file(d, src, "# R\n\ndo not share secrets\n")
            rule = {
                "id": "rule:3:1",
                "source": {"path": src, "start_line": 3, "end_line": 3,
                           "quote": "do not share secrets"},
                "text": "Do not share secrets",
                "bucket": "judgment", "judgment_reason": "human",
                "rationale": "", "duplicate_of": None, "conflicts_with": [],
                "check": {"kind": "deny_path", "globs": ["secrets/**"]},  # should be null
                "cases": [],
            }
            doc = {"rules": [rule]}
            errs = validate_rule(rule, doc, d, _ADAPTERS, _KIND_BUCKETS, _LIMITS)
            self.assertTrue(any("null" in e for e in errs))

    def test_too_few_cases(self):
        with tempfile.TemporaryDirectory() as d:
            rule = _block_rule(d)
            rule["cases"] = rule["cases"][:2]  # only 2 instead of 3
            doc = {"rules": [rule]}
            errs = validate_rule(rule, doc, d, _ADAPTERS, _KIND_BUCKETS, _LIMITS)
            self.assertTrue(any("pre_tool" in e for e in errs))

    def test_missing_allow_case(self):
        with tempfile.TemporaryDirectory() as d:
            rule = _block_rule(d)
            rule["cases"] = [c for c in rule["cases"] if c["expect"] != "allow"]
            # Add a third blocking case to maintain count but remove allow
            rule["cases"].append({"name": "extra_block", "type": "pre_tool",
                                  "tool": "write_file", "input": {"path": ".env2"},
                                  "expect": "block"})
            doc = {"rules": [rule]}
            errs = validate_rule(rule, doc, d, _ADAPTERS, _KIND_BUCKETS, _LIMITS)
            self.assertTrue(any("allow" in e for e in errs))

    def test_asymmetric_conflict(self):
        with tempfile.TemporaryDirectory() as d:
            rule_a = _block_rule(d, rid="rule:1:1")
            rule_a["conflicts_with"] = ["rule:2:1"]
            rule_b = _block_rule(d, rid="rule:2:1")
            # rule_b does NOT list rule_a in conflicts_with → asymmetric
            doc = {"rules": [rule_a, rule_b]}
            errs_a = validate_rule(rule_a, doc, d, _ADAPTERS, _KIND_BUCKETS, _LIMITS)
            self.assertTrue(any("symmetric" in e for e in errs_a))

    def test_duplicate_of_duplicate(self):
        with tempfile.TemporaryDirectory() as d:
            rule_a = _block_rule(d, rid="rule:1:1")
            rule_b = _block_rule(d, rid="rule:2:1")
            rule_b["bucket"] = "judgment"
            rule_b["judgment_reason"] = "duplicate"
            rule_b["duplicate_of"] = "rule:1:1"
            rule_b["check"] = None
            rule_b["cases"] = []
            rule_c = _block_rule(d, rid="rule:3:1")
            rule_c["bucket"] = "judgment"
            rule_c["judgment_reason"] = "duplicate"
            rule_c["duplicate_of"] = "rule:2:1"  # dup of a dup
            rule_c["check"] = None
            rule_c["cases"] = []
            doc = {"rules": [rule_a, rule_b, rule_c]}
            errs_c = validate_rule(rule_c, doc, d, _ADAPTERS, _KIND_BUCKETS, _LIMITS)
            self.assertTrue(any("itself a duplicate" in e for e in errs_c))

    def test_invalid_glob_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            rule = _block_rule(d, globs=["[invalid"])
            doc = {"rules": [rule]}
            errs = validate_rule(rule, doc, d, _ADAPTERS, _KIND_BUCKETS, _LIMITS)
            self.assertTrue(any("glob" in e for e in errs))

    def test_invalid_pattern_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            src = ".bob/rules/01-rules.md"
            _make_root_with_file(d, src, "# R\n\nno secrets\n")
            rule = {
                "id": "rule:3:1",
                "source": {"path": src, "start_line": 3, "end_line": 3, "quote": "no secrets"},
                "text": "No secrets in commands",
                "bucket": "block", "judgment_reason": None,
                "rationale": "", "duplicate_of": None, "conflicts_with": [],
                "check": {"kind": "deny_command", "patterns": [r"(a+)+"]},
                "cases": [
                    {"name": "a", "type": "pre_tool", "tool": "execute_command",
                     "input": {"command": "echo hi"}, "expect": "allow"},
                    {"name": "b", "type": "pre_tool", "tool": "execute_command",
                     "input": {"command": "secret"}, "expect": "block"},
                    {"name": "c", "type": "pre_tool", "tool": "execute_command",
                     "input": {"command": "fine"}, "expect": "allow"},
                ],
            }
            doc = {"rules": [rule]}
            errs = validate_rule(rule, doc, d, _ADAPTERS, _KIND_BUCKETS, _LIMITS)
            self.assertTrue(any("pattern" in e for e in errs))


class TestValidateAll(unittest.TestCase):
    def test_unique_ids_required(self):
        with tempfile.TemporaryDirectory() as d:
            rule_a = _block_rule(d, rid="rule:1:1")
            rule_b = _block_rule(d, rid="rule:1:1")  # duplicate id
            doc = {"rules": [rule_a, rule_b]}
            errs = validate_all(doc, d, _ADAPTERS, _KIND_BUCKETS, _LIMITS)
            self.assertIn("rule:1:1", errs)

    def test_pattern_count_limit(self):
        """A rule that pushes total patterns over max_patterns gets an error."""
        with tempfile.TemporaryDirectory() as d:
            src = ".bob/rules/01-rules.md"
            _make_root_with_file(d, src, "# R\n\nno secrets\n")
            limits = dict(_LIMITS)
            limits["max_patterns"] = 2

            def _cmd_rule(rid, patterns):
                return {
                    "id": rid,
                    "source": {"path": src, "start_line": 3, "end_line": 3,
                               "quote": "no secrets"},
                    "text": "t",
                    "bucket": "block", "judgment_reason": None,
                    "rationale": "", "duplicate_of": None, "conflicts_with": [],
                    "check": {"kind": "deny_command", "patterns": patterns},
                    "cases": [
                        {"name": "a", "type": "pre_tool", "tool": "execute_command",
                         "input": {"command": "x"}, "expect": "allow"},
                        {"name": "b", "type": "pre_tool", "tool": "execute_command",
                         "input": {"command": "secret"}, "expect": "block"},
                        {"name": "c", "type": "pre_tool", "tool": "execute_command",
                         "input": {"command": "y"}, "expect": "allow"},
                    ],
                }

            r1 = _cmd_rule("rule:3:1", ["pat1", "pat2"])
            r2 = _cmd_rule("rule:3:2", ["pat3"])  # pushes over limit of 2
            doc = {"rules": [r1, r2]}
            errs = validate_all(doc, d, _ADAPTERS, _KIND_BUCKETS, limits)
            # rule:3:2 or r1 should have an error about the limit
            all_errs = [e for v in errs.values() for e in v]
            self.assertTrue(any("pattern count" in e for e in all_errs))


if __name__ == "__main__":
    unittest.main()

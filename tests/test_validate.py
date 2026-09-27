"""Tests for stickler.stickler_validate (guide §6, validate bullets)."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

_ENV = {**os.environ, "PYTHONPATH": os.path.dirname(os.path.dirname(os.path.abspath(__file__)))}


def _run_validate(root, *args):
    r = subprocess.run(
        [sys.executable, "-m", "stickler.stickler_validate", "--root", root] + list(args),
        capture_output=True, text=True, env=_ENV, cwd=root
    )
    return r.returncode, r.stdout, r.stderr


def _setup_repo(rules, existing_dir=None):
    """Create (or populate) a repo with rules.json and .stickler/ config.

    If *existing_dir* is provided the directory is reused; otherwise a fresh
    temporary directory is created and initialised with git.
    """
    if existing_dir is not None:
        d = existing_dir
    else:
        d = tempfile.mkdtemp()
        subprocess.run(["git", "init", "-q", "-b", "main", d], check=True)
        subprocess.run(["git", "-C", d, "config", "user.name", "t"], check=True)
        subprocess.run(["git", "-C", d, "config", "user.email", "t@t"], check=True)
        subprocess.run(["git", "-C", d, "commit", "--allow-empty", "-q", "-m", "init"],
                       check=True)

    stickler_dir = os.path.join(d, ".stickler")
    os.makedirs(stickler_dir, exist_ok=True)
    spec_dir = os.path.join(d, "stickler")
    os.makedirs(spec_dir, exist_ok=True)

    pkg_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "stickler")
    shutil.copy(os.path.join(pkg_dir, "adapters.json"),
                os.path.join(stickler_dir, "adapters.json"))
    shutil.copy(os.path.join(pkg_dir, "kind-buckets.json"),
                os.path.join(stickler_dir, "kind-buckets.json"))

    config = {
        "config_version": 1, "on_error": "allow", "missing_path_field": "block",
        "control_globs": [".bob/**", "stickler/**"],
        "engine_owned_globs": [".stickler/**"],
        "audit": {"include_ignored": [".env"], "blob_max_bytes": 1048576},
        "limits": {
            "pre_tool_regex_deadline_ms": 1500,
            "audit_regex_deadline_ms": 20000,
            "max_command_bytes": 65536,
            "max_patterns": 50,
            "max_pattern_len": 200,
            "screen_deadline_ms": 100,
        },
        "mode": "compile",
    }
    with open(os.path.join(stickler_dir, "config.json"), "w") as f:
        json.dump(config, f)

    with open(os.path.join(spec_dir, "rules.json"), "w") as f:
        json.dump(rules, f)

    return d


def _make_rules_doc(d, rules_list):
    """Create the source file and return a rules doc."""
    src = ".bob/rules/01.md"
    os.makedirs(os.path.join(d, ".bob", "rules"), exist_ok=True)
    lines = ["# Rules\n"]
    for i, text in enumerate(rules_list, start=2):
        lines.append(f"{text}\n")
    with open(os.path.join(d, src), "w") as f:
        f.writelines(lines)
    return src, lines


def _block_rule(d, src, line_no, rid, kind="deny_path", globs=None, text="do not edit .env"):
    return {
        "id": rid,
        "source": {"path": src, "start_line": line_no, "end_line": line_no, "quote": text},
        "text": text,
        "bucket": "block", "judgment_reason": None,
        "rationale": "", "duplicate_of": None, "conflicts_with": [],
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


def _audit_rule(d, src, line_no, rid):
    text = "always update changelog"
    return {
        "id": rid,
        "source": {"path": src, "start_line": line_no, "end_line": line_no, "quote": text},
        "text": text,
        "bucket": "audit", "judgment_reason": None,
        "rationale": "", "duplicate_of": None, "conflicts_with": [],
        "check": {"kind": "require_paired_change",
                  "when_changed": ["src/**"], "require_changed": ["CHANGELOG.md"]},
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


class TestValidateRun(unittest.TestCase):
    def test_5_rule_doc(self):
        """One per bucket plus a duplicate and a conflict."""
        d = None
        try:
            d = tempfile.mkdtemp()
            subprocess.run(["git", "init", "-q", "-b", "main", d], check=True)
            subprocess.run(["git", "-C", d, "config", "user.name", "t"], check=True)
            subprocess.run(["git", "-C", d, "config", "user.email", "t@t"], check=True)
            subprocess.run(["git", "-C", d, "commit", "--allow-empty", "-q", "-m", "i"],
                           check=True)

            src = ".bob/rules/01.md"
            os.makedirs(os.path.join(d, ".bob", "rules"), exist_ok=True)
            lines = (
                "# Rules\n"
                "do not edit .env\n"
                "always update changelog\n"
                "do not share secrets\n"
                "do not edit .env\n"
                "edit src only vs edit tests\n"
            )
            with open(os.path.join(d, src), "w") as f:
                f.write(lines)

            rules_list = [
                _block_rule(d, src, 2, "rule:2:1", text="do not edit .env"),
                _audit_rule(d, src, 3, "rule:3:1"),
                {
                    "id": "rule:4:1",
                    "source": {"path": src, "start_line": 4, "end_line": 4,
                               "quote": "do not share secrets"},
                    "text": "Do not share secrets",
                    "bucket": "judgment", "judgment_reason": "human",
                    "rationale": "needs human review",
                    "duplicate_of": None, "conflicts_with": [],
                    "check": None, "cases": [],
                },
                {
                    "id": "rule:5:1",
                    "source": {"path": src, "start_line": 5, "end_line": 5,
                               "quote": "do not edit .env"},
                    "text": "Also do not edit .env",
                    "bucket": "judgment", "judgment_reason": "duplicate",
                    "rationale": "same as rule:2:1",
                    "duplicate_of": "rule:2:1", "conflicts_with": [],
                    "check": None, "cases": [],
                },
                {
                    "id": "rule:6:1",
                    "source": {"path": src, "start_line": 6, "end_line": 6,
                               "quote": "edit src only vs edit tests"},
                    "text": "Edit src only vs edit tests",
                    "bucket": "judgment", "judgment_reason": "conflict",
                    "rationale": "conflicts",
                    "duplicate_of": None, "conflicts_with": ["rule:6:2"],
                    "check": None, "cases": [],
                },
                {
                    "id": "rule:6:2",
                    "source": {"path": src, "start_line": 6, "end_line": 6,
                               "quote": "edit src only vs edit tests"},
                    "text": "Edit tests only vs edit src",
                    "bucket": "judgment", "judgment_reason": "conflict",
                    "rationale": "conflicts",
                    "duplicate_of": None, "conflicts_with": ["rule:6:1"],
                    "check": None, "cases": [],
                },
            ]

            d = _setup_repo({"schema_version": 1, "sources": [], "rules": rules_list}, d)
            code, out, err = _run_validate(d, "--run")
            self.assertEqual(code, 0, err)

            from stickler.util import read_json
            val = read_json(os.path.join(d, "stickler", "validation.json"))
            self.assertEqual(val["rules"]["rule:2:1"]["status"], "validated")
            self.assertEqual(val["rules"]["rule:3:1"]["status"], "validated")
            self.assertEqual(val["rules"]["rule:4:1"]["status"], "judgment")
            self.assertEqual(val["rules"]["rule:5:1"]["status"], "duplicate")
            self.assertIn(val["rules"]["rule:6:1"]["status"], ("conflict",))
        finally:
            if d:
                shutil.rmtree(d, ignore_errors=True)

    def test_report_activates_validated_only(self):
        d = None
        try:
            src = ".bob/rules/01.md"
            rule = {"id": "rule:2:1",
                    "source": {"path": src, "start_line": 2, "end_line": 2,
                               "quote": "do not edit .env"},
                    "text": "do not edit .env",
                    "bucket": "block", "judgment_reason": None,
                    "rationale": "", "duplicate_of": None, "conflicts_with": [],
                    "check": {"kind": "deny_path", "globs": [".env", "**/.env"]},
                    "cases": [
                        {"name": "a", "type": "pre_tool", "tool": "write_file",
                         "input": {"path": "src/x.py"}, "expect": "allow"},
                        {"name": "b", "type": "pre_tool", "tool": "write_file",
                         "input": {"path": ".env"}, "expect": "block"},
                        {"name": "c", "type": "pre_tool", "tool": "write_file",
                         "input": {"path": "app/.env"}, "expect": "block"},
                    ]}
            d = tempfile.mkdtemp()
            subprocess.run(["git", "init", "-q", "-b", "main", d], check=True)
            subprocess.run(["git", "-C", d, "config", "user.name", "t"], check=True)
            subprocess.run(["git", "-C", d, "config", "user.email", "t@t"], check=True)
            subprocess.run(["git", "-C", d, "commit", "--allow-empty", "-q", "-m", "i"],
                           check=True)
            os.makedirs(os.path.join(d, ".bob", "rules"), exist_ok=True)
            with open(os.path.join(d, src), "w") as f:
                f.write("# R\ndo not edit .env\n")
            d = _setup_repo({"schema_version": 1, "sources": [], "rules": [rule]}, d)
            code, out, err = _run_validate(d, "--report")
            self.assertEqual(code, 0, err)
            # Check pointer was written
            active = os.path.join(d, ".stickler", "active.json")
            self.assertTrue(os.path.isfile(active))
            from stickler.util import read_json
            ptr = read_json(active)
            self.assertIn("rule:2:1", ptr["activated"])
        finally:
            if d:
                shutil.rmtree(d, ignore_errors=True)

    def test_check_passes(self):
        d = None
        try:
            src = ".bob/rules/01.md"
            rule = {"id": "rule:2:1",
                    "source": {"path": src, "start_line": 2, "end_line": 2,
                               "quote": "do not edit .env"},
                    "text": "do not edit .env",
                    "bucket": "block", "judgment_reason": None,
                    "rationale": "", "duplicate_of": None, "conflicts_with": [],
                    "check": {"kind": "deny_path", "globs": [".env", "**/.env"]},
                    "cases": [
                        {"name": "a", "type": "pre_tool", "tool": "write_file",
                         "input": {"path": "src/x.py"}, "expect": "allow"},
                        {"name": "b", "type": "pre_tool", "tool": "write_file",
                         "input": {"path": ".env"}, "expect": "block"},
                        {"name": "c", "type": "pre_tool", "tool": "write_file",
                         "input": {"path": "app/.env"}, "expect": "block"},
                    ]}
            d = tempfile.mkdtemp()
            subprocess.run(["git", "init", "-q", "-b", "main", d], check=True)
            subprocess.run(["git", "-C", d, "config", "user.name", "t"], check=True)
            subprocess.run(["git", "-C", d, "config", "user.email", "t@t"], check=True)
            subprocess.run(["git", "-C", d, "commit", "--allow-empty", "-q", "-m", "i"],
                           check=True)
            os.makedirs(os.path.join(d, ".bob", "rules"), exist_ok=True)
            with open(os.path.join(d, src), "w") as f:
                f.write("# R\ndo not edit .env\n")
            d = _setup_repo({"schema_version": 1, "sources": [], "rules": [rule]}, d)
            _run_validate(d, "--run")  # populate validation.json
            code, out, err = _run_validate(d, "--check")
            self.assertEqual(code, 0, err)
        finally:
            if d:
                shutil.rmtree(d, ignore_errors=True)

    def test_check_fails_after_tampering(self):
        d = None
        try:
            src = ".bob/rules/01.md"
            rule = {"id": "rule:2:1",
                    "source": {"path": src, "start_line": 2, "end_line": 2,
                               "quote": "do not edit .env"},
                    "text": "do not edit .env",
                    "bucket": "block", "judgment_reason": None,
                    "rationale": "", "duplicate_of": None, "conflicts_with": [],
                    "check": {"kind": "deny_path", "globs": [".env", "**/.env"]},
                    "cases": [
                        {"name": "a", "type": "pre_tool", "tool": "write_file",
                         "input": {"path": "src/x.py"}, "expect": "allow"},
                        {"name": "b", "type": "pre_tool", "tool": "write_file",
                         "input": {"path": ".env"}, "expect": "block"},
                        {"name": "c", "type": "pre_tool", "tool": "write_file",
                         "input": {"path": "app/.env"}, "expect": "block"},
                    ]}
            d = tempfile.mkdtemp()
            subprocess.run(["git", "init", "-q", "-b", "main", d], check=True)
            subprocess.run(["git", "-C", d, "config", "user.name", "t"], check=True)
            subprocess.run(["git", "-C", d, "config", "user.email", "t@t"], check=True)
            subprocess.run(["git", "-C", d, "commit", "--allow-empty", "-q", "-m", "i"],
                           check=True)
            os.makedirs(os.path.join(d, ".bob", "rules"), exist_ok=True)
            with open(os.path.join(d, src), "w") as f:
                f.write("# R\ndo not edit .env\n")
            d = _setup_repo({"schema_version": 1, "sources": [], "rules": [rule]}, d)
            _run_validate(d, "--run")

            # Tamper
            val_path = os.path.join(d, "stickler", "validation.json")
            with open(val_path) as f:
                val = json.load(f)
            val["rules"]["rule:2:1"]["schema_valid"] = False
            with open(val_path, "w") as f:
                json.dump(val, f)

            code, out, err = _run_validate(d, "--check")
            self.assertNotEqual(code, 0)
        finally:
            if d:
                shutil.rmtree(d, ignore_errors=True)

    def test_trace_fails_on_wrong_quote(self):
        d = None
        try:
            src = ".bob/rules/01.md"
            rule = {"id": "rule:2:1",
                    "source": {"path": src, "start_line": 2, "end_line": 2,
                               "quote": "WRONG QUOTE NOT IN FILE"},
                    "text": "do not edit .env",
                    "bucket": "block", "judgment_reason": None,
                    "rationale": "", "duplicate_of": None, "conflicts_with": [],
                    "check": {"kind": "deny_path", "globs": [".env"]},
                    "cases": []}
            d = tempfile.mkdtemp()
            subprocess.run(["git", "init", "-q", "-b", "main", d], check=True)
            subprocess.run(["git", "-C", d, "config", "user.name", "t"], check=True)
            subprocess.run(["git", "-C", d, "config", "user.email", "t@t"], check=True)
            subprocess.run(["git", "-C", d, "commit", "--allow-empty", "-q", "-m", "i"],
                           check=True)
            os.makedirs(os.path.join(d, ".bob", "rules"), exist_ok=True)
            with open(os.path.join(d, src), "w") as f:
                f.write("# R\ndo not edit .env\n")
            d = _setup_repo({"schema_version": 1, "sources": [], "rules": [rule]}, d)
            code, out, err = _run_validate(d, "--trace")
            self.assertNotEqual(code, 0)
            self.assertIn("TRACE FAIL", out)
        finally:
            if d:
                shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()

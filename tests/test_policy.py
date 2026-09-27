"""Tests for stickler.policy (guide §6, policy bullets)."""

import os
import subprocess
import tempfile
import unittest

from stickler.policy import evaluate_pre_tool

_ADAPTERS = {
    "adapter_version": 1,
    "confirmed_by_probe": None,
    "tools": {
        "write_file": {"operation": "write", "paths": ["path"]},
        "execute_command": {"operation": "execute", "command": "command", "cwd": "cwd"},
        "delete_tool": {"operation": "delete", "paths": ["path"]},
        "rename_tool": {"operation": "rename", "from": "src", "to": "dst"},
    },
}

_CONFIG = {
    "on_error": "allow",
    "missing_path_field": "block",
    "control_globs": [".bob/**", "stickler/**"],
    "engine_owned_globs": [".stickler/**"],
    "limits": {
        "pre_tool_regex_deadline_ms": 1500,
        "audit_regex_deadline_ms": 20000,
        "max_command_bytes": 65536,
        "max_patterns": 50,
        "max_pattern_len": 200,
        "screen_deadline_ms": 100,
    },
}


def _tmpdir():
    d = tempfile.mkdtemp()
    subprocess.run(["git", "init", "-q", d], check=True)
    return d


def _deny_path_rule(globs, rid="rule:1:1"):
    return {
        "id": rid,
        "bucket": "block",
        "judgment_reason": None,
        "check": {"kind": "deny_path", "globs": globs},
        "source": {"path": "x", "start_line": 1, "end_line": 1},
        "text": "deny_path rule",
        "cases": [],
    }


def _allow_only_rule(globs, rid="rule:1:1"):
    return {
        "id": rid,
        "bucket": "block",
        "judgment_reason": None,
        "check": {"kind": "allow_paths_only", "globs": globs},
        "source": {"path": "x", "start_line": 1, "end_line": 1},
        "text": "allow_paths_only rule",
        "cases": [],
    }


def _forbid_delete_rule(globs, rid="rule:1:1"):
    return {
        "id": rid,
        "bucket": "audit",
        "judgment_reason": None,
        "check": {"kind": "forbid_file_deletion", "globs": globs},
        "source": {"path": "x", "start_line": 1, "end_line": 1},
        "text": "forbid_file_deletion rule",
        "cases": [],
    }


def _deny_cmd_rule(patterns, rid="rule:1:1"):
    return {
        "id": rid,
        "bucket": "block",
        "judgment_reason": None,
        "check": {"kind": "deny_command", "patterns": patterns},
        "source": {"path": "x", "start_line": 1, "end_line": 1},
        "text": "deny_command rule",
        "cases": [],
    }


class TestDenyPath(unittest.TestCase):
    def setUp(self):
        self.root = _tmpdir()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.root, ignore_errors=True)

    def test_lexical_path_blocked(self):
        rule = _deny_path_rule([".env"])
        d = evaluate_pre_tool("write_file", {"path": ".env"}, [rule],
                               _ADAPTERS, _CONFIG, self.root, self.root)
        self.assertEqual(d["decision"], "block")
        self.assertIn("rule:1:1", d["rule_ids"])

    def test_allowed_path(self):
        rule = _deny_path_rule([".env"])
        d = evaluate_pre_tool("write_file", {"path": "src/main.py"}, [rule],
                               _ADAPTERS, _CONFIG, self.root, self.root)
        self.assertEqual(d["decision"], "allow")

    def test_glob_wildcard(self):
        rule = _deny_path_rule(["**/.env"])
        d = evaluate_pre_tool("write_file", {"path": "app/.env"}, [rule],
                               _ADAPTERS, _CONFIG, self.root, self.root)
        self.assertEqual(d["decision"], "block")

    def test_write_content_mentioning_path_is_allowed(self):
        """A write whose content mentions .env is not a write to .env."""
        rule = _deny_path_rule([".env"])
        d = evaluate_pre_tool("write_file", {"path": "src/config.py"}, [rule],
                               _ADAPTERS, _CONFIG, self.root, self.root)
        self.assertEqual(d["decision"], "allow")


class TestAllowPathsOnly(unittest.TestCase):
    def setUp(self):
        self.root = _tmpdir()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.root, ignore_errors=True)

    def test_inside_allowed_glob(self):
        rule = _allow_only_rule(["src/**"])
        d = evaluate_pre_tool("write_file", {"path": "src/a.py"}, [rule],
                               _ADAPTERS, _CONFIG, self.root, self.root)
        self.assertEqual(d["decision"], "allow")

    def test_outside_repo_blocked(self):
        rule = _allow_only_rule(["src/**"])
        d = evaluate_pre_tool("write_file", {"path": "../outside.py"}, [rule],
                               _ADAPTERS, _CONFIG, self.root, self.root)
        self.assertEqual(d["decision"], "block")

    def test_inside_but_not_matching_glob_blocked(self):
        rule = _allow_only_rule(["src/**"])
        d = evaluate_pre_tool("write_file", {"path": "tests/t.py"}, [rule],
                               _ADAPTERS, _CONFIG, self.root, self.root)
        self.assertEqual(d["decision"], "block")


class TestForbidFileDeletion(unittest.TestCase):
    def setUp(self):
        self.root = _tmpdir()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.root, ignore_errors=True)

    def test_delete_protected_path_blocked(self):
        rule = _forbid_delete_rule([".env"])
        d = evaluate_pre_tool("delete_tool", {"path": ".env"}, [rule],
                               _ADAPTERS, _CONFIG, self.root, self.root)
        self.assertEqual(d["decision"], "block")

    def test_rename_from_protected_path_blocked(self):
        rule = _forbid_delete_rule([".env"])
        d = evaluate_pre_tool("rename_tool", {"src": ".env", "dst": ".env.bak"}, [rule],
                               _ADAPTERS, _CONFIG, self.root, self.root)
        self.assertEqual(d["decision"], "block")

    def test_rename_to_protected_path_not_blocked_by_deletion(self):
        # forbid_file_deletion only checks rename-from
        rule = _forbid_delete_rule([".env"])
        d = evaluate_pre_tool("rename_tool", {"src": "foo.txt", "dst": ".env"}, [rule],
                               _ADAPTERS, _CONFIG, self.root, self.root)
        self.assertEqual(d["decision"], "allow")


class TestControlPathExemption(unittest.TestCase):
    def setUp(self):
        self.root = _tmpdir()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.root, ignore_errors=True)

    def test_user_rule_skips_control_path(self):
        rule = _deny_path_rule([".bob/**"])
        d = evaluate_pre_tool("write_file", {"path": ".bob/settings.json"}, [rule],
                               _ADAPTERS, _CONFIG, self.root, self.root)
        # User rule is exempt from control paths — so this should be ALLOWED
        self.assertEqual(d["decision"], "allow")

    def test_builtin_rule_blocks_control_path(self):
        builtin = {
            "id": "builtin:control-files",
            "bucket": "block",
            "judgment_reason": None,
            "check": {"kind": "deny_path", "globs": [".bob/**", "stickler/**", ".stickler/**"]},
            "source": {"path": "x", "start_line": 1, "end_line": 1},
            "text": "builtin",
            "cases": [],
        }
        d = evaluate_pre_tool("write_file", {"path": ".bob/settings.json"}, [builtin],
                               _ADAPTERS, _CONFIG, self.root, self.root)
        self.assertEqual(d["decision"], "block")


class TestMalformedAndUnknown(unittest.TestCase):
    def setUp(self):
        self.root = _tmpdir()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.root, ignore_errors=True)

    def test_malformed_blocked_when_config_block(self):
        config = dict(_CONFIG, missing_path_field="block")
        d = evaluate_pre_tool("write_file", {}, [], _ADAPTERS, config, self.root, self.root)
        self.assertEqual(d["decision"], "block")
        self.assertEqual(d["coverage"], "malformed")

    def test_malformed_allowed_when_config_allow(self):
        config = dict(_CONFIG, missing_path_field="allow")
        d = evaluate_pre_tool("write_file", {}, [], _ADAPTERS, config, self.root, self.root)
        self.assertEqual(d["decision"], "allow")

    def test_unknown_tool_allowed(self):
        d = evaluate_pre_tool("unknown_xyz", {}, [], _ADAPTERS, _CONFIG, self.root, self.root)
        self.assertEqual(d["decision"], "allow")
        self.assertEqual(d["coverage"], "unknown_tool")


class TestDenyCommand(unittest.TestCase):
    def setUp(self):
        self.root = _tmpdir()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.root, ignore_errors=True)

    def test_matching_command_blocked(self):
        rule = _deny_cmd_rule([r"rm\s+-rf"])
        d = evaluate_pre_tool("execute_command", {"command": "rm -rf /tmp/x"}, [rule],
                               _ADAPTERS, _CONFIG, self.root, self.root)
        self.assertEqual(d["decision"], "block")

    def test_non_matching_command_allowed(self):
        rule = _deny_cmd_rule([r"rm\s+-rf"])
        d = evaluate_pre_tool("execute_command", {"command": "echo hello"}, [rule],
                               _ADAPTERS, _CONFIG, self.root, self.root)
        self.assertEqual(d["decision"], "allow")

    def test_command_too_long_on_error_allow(self):
        config = dict(_CONFIG)
        config["limits"] = dict(_CONFIG["limits"], max_command_bytes=5)
        rule = _deny_cmd_rule([r"secret"])
        d = evaluate_pre_tool("execute_command", {"command": "a" * 100}, [rule],
                               _ADAPTERS, config, self.root, self.root)
        self.assertEqual(d["decision"], "allow")
        self.assertIsNotNone(d["error"])

    def test_command_too_long_on_error_block(self):
        config = dict(_CONFIG, on_error="block")
        config["limits"] = dict(_CONFIG["limits"], max_command_bytes=5)
        rule = _deny_cmd_rule([r"secret"])
        d = evaluate_pre_tool("execute_command", {"command": "a" * 100}, [rule],
                               _ADAPTERS, config, self.root, self.root)
        self.assertEqual(d["decision"], "block")

    def test_regex_timeout_on_error_allow(self):
        """Monkeypatch run_patterns to return regex_timeout."""
        import stickler.policy as pol
        orig = pol.run_patterns

        def fake_run(*a, **kw):
            return [], "regex_timeout"

        pol.run_patterns = fake_run
        try:
            rule = _deny_cmd_rule([r"secret"])
            d = evaluate_pre_tool("execute_command", {"command": "secret"}, [rule],
                                   _ADAPTERS, _CONFIG, self.root, self.root)
            self.assertEqual(d["coverage"], "error")
            self.assertEqual(d["decision"], "allow")  # on_error=allow
        finally:
            pol.run_patterns = orig

    def test_regex_timeout_on_error_block(self):
        import stickler.policy as pol
        orig = pol.run_patterns

        def fake_run(*a, **kw):
            return [], "regex_timeout"

        pol.run_patterns = fake_run
        try:
            config = dict(_CONFIG, on_error="block")
            rule = _deny_cmd_rule([r"secret"])
            d = evaluate_pre_tool("execute_command", {"command": "secret"}, [rule],
                                   _ADAPTERS, config, self.root, self.root)
            self.assertEqual(d["decision"], "block")
        finally:
            pol.run_patterns = orig


class TestMessageFormat(unittest.TestCase):
    def setUp(self):
        self.root = _tmpdir()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.root, ignore_errors=True)

    def test_block_message_contains_rule_id_and_tool(self):
        rule = _deny_path_rule([".env"])
        d = evaluate_pre_tool("write_file", {"path": ".env"}, [rule],
                               _ADAPTERS, _CONFIG, self.root, self.root)
        self.assertTrue(any("write_file" in m for m in d["messages"]))
        self.assertTrue(any("rule:1:1" in m for m in d["messages"]))


if __name__ == "__main__":
    unittest.main()

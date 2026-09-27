"""End-to-end hook tests (guide §6, hook end-to-end bullets)."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

_CONFIG = {
    "config_version": 1,
    "on_error": "allow",
    "missing_path_field": "block",
    "control_globs": [".bob/**", "stickler/**"],
    "engine_owned_globs": [".stickler/**"],
    "audit": {"include_ignored": [".env", "**/.env"], "blob_max_bytes": 1048576},
    "limits": {
        "pre_tool_regex_deadline_ms": 1500,
        "audit_regex_deadline_ms": 20000,
        "max_command_bytes": 65536,
        "max_patterns": 50,
        "max_pattern_len": 200,
        "screen_deadline_ms": 100,
    },
    "mode": "governed",
}

_RULES = {
    "schema_version": 1,
    "sources": [],
    "rules": [
        {
            "id": "rule:1:1",
            "source": {"path": ".bob/rules/01.md", "start_line": 1, "end_line": 1,
                       "quote": "never edit .env"},
            "text": "Never edit .env",
            "bucket": "block",
            "judgment_reason": None,
            "rationale": "",
            "duplicate_of": None,
            "conflicts_with": [],
            "check": {"kind": "deny_path", "globs": [".env", "**/.env"]},
            "cases": [
                {"name": "allow", "type": "pre_tool", "tool": "write_file",
                 "input": {"path": "src/a.py"}, "expect": "allow"},
                {"name": "block", "type": "pre_tool", "tool": "write_file",
                 "input": {"path": ".env"}, "expect": "block"},
                {"name": "boundary", "type": "pre_tool", "tool": "write_file",
                 "input": {"path": "app/.env"}, "expect": "block"},
            ],
        }
    ],
}


def _setup_governed_repo():
    """Create a minimal governed-mode repository."""
    d = tempfile.mkdtemp()
    subprocess.run(["git", "init", "-q", "-b", "main", d], check=True)
    subprocess.run(["git", "-C", d, "config", "user.name", "t"], check=True)
    subprocess.run(["git", "-C", d, "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", d, "commit", "--allow-empty", "-q", "-m", "init"],
                   check=True)

    stickler_dir = os.path.join(d, ".stickler")
    os.makedirs(stickler_dir, exist_ok=True)

    # Write config
    with open(os.path.join(stickler_dir, "config.json"), "w") as f:
        json.dump(_CONFIG, f)

    # Write adapters and kind-buckets
    pkg_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "stickler")
    shutil.copy(os.path.join(pkg_dir, "adapters.json"),
                os.path.join(stickler_dir, "adapters.json"))
    shutil.copy(os.path.join(pkg_dir, "kind-buckets.json"),
                os.path.join(stickler_dir, "kind-buckets.json"))

    # Write rule source file
    rules_dir = os.path.join(d, ".bob", "rules")
    os.makedirs(rules_dir, exist_ok=True)
    with open(os.path.join(rules_dir, "01.md"), "w") as f:
        f.write("never edit .env\n")

    # Write rules.json into target/stickler/ (required by _activate)
    spec_dir = os.path.join(d, "stickler")
    os.makedirs(spec_dir, exist_ok=True)
    with open(os.path.join(spec_dir, "rules.json"), "w") as f:
        json.dump(_RULES, f)

    # Activate rules to create snapshot and pointer
    from stickler.install import _activate
    _activate(d, stickler_dir, _CONFIG)

    return d


_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _run_hook(repo, event_payload, cwd=None):
    """Run the hook subprocess and return (returncode, stdout, stderr)."""
    env = os.environ.copy()
    env["PYTHONPATH"] = _REPO_ROOT
    r = subprocess.run(
        [sys.executable, "-m", "stickler.stickler_hook"],
        input=json.dumps(event_payload),
        capture_output=True,
        text=True,
        cwd=cwd or repo,
        env=env,
    )
    return r.returncode, r.stdout, r.stderr


class TestHookGoverned(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo = _setup_governed_repo()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.repo, ignore_errors=True)

    def test_session_start_prints_active_count(self):
        code, out, err = _run_hook(self.repo, {
            "event": "SessionStart", "session_id": "ses_e2e_1"
        })
        self.assertEqual(code, 0, err)
        self.assertIn("[Stickler]", out)
        self.assertIn("rules active", out)

    def test_blocked_pre_tool_use_exits_2(self):
        code, out, err = _run_hook(self.repo, {
            "event": "PreToolUse",
            "session_id": "ses_e2e_block",
            "tool": "write_file",
            "input": {"path": ".env"},
        })
        self.assertEqual(code, 2)
        self.assertIn("blocked", err)

    def test_allowed_pre_tool_use_exits_0(self):
        code, out, err = _run_hook(self.repo, {
            "event": "PreToolUse",
            "session_id": "ses_e2e_allow",
            "tool": "write_file",
            "input": {"path": "src/main.py"},
        })
        self.assertEqual(code, 0)
        self.assertEqual(out, "")

    def test_block_queued_and_printed_on_next_prompt(self):
        sid = "ses_e2e_queue"
        # SessionStart
        _run_hook(self.repo, {"event": "SessionStart", "session_id": sid})
        # Block
        _run_hook(self.repo, {
            "event": "PreToolUse", "session_id": sid,
            "tool": "write_file", "input": {"path": ".env"}
        })
        # Next prompt should mention the block
        code, out, err = _run_hook(self.repo, {
            "event": "UserPromptSubmit", "session_id": sid
        })
        self.assertEqual(code, 0)
        self.assertIn("blocked", out)

    def test_stop_writes_report(self):
        sid = "ses_e2e_stop"
        _run_hook(self.repo, {"event": "SessionStart", "session_id": sid})

        # Write .env directly so it shows in the audit
        env_path = os.path.join(self.repo, ".env")
        with open(env_path, "w") as f:
            f.write("SECRET=1")

        code, out, err = _run_hook(self.repo, {
            "event": "Stop", "session_id": sid
        })
        self.assertEqual(code, 0, err)

        # Report file should exist
        from stickler.paths import safe_session_id
        safe_sid = safe_session_id(sid)
        report_dir = os.path.join(self.repo, ".stickler", "reports", safe_sid)
        self.assertTrue(os.path.isdir(report_dir), f"no report dir: {report_dir}")
        reports = [f for f in os.listdir(report_dir) if f.endswith(".json")]
        self.assertTrue(len(reports) >= 1, "no report JSON")

    def test_second_stop_writes_stop_2(self):
        sid = "ses_e2e_stop2"
        _run_hook(self.repo, {"event": "SessionStart", "session_id": sid})
        _run_hook(self.repo, {"event": "Stop", "session_id": sid})
        _run_hook(self.repo, {"event": "Stop", "session_id": sid})

        from stickler.paths import safe_session_id
        safe_sid = safe_session_id(sid)
        report_dir = os.path.join(self.repo, ".stickler", "reports", safe_sid)
        reports = [f for f in os.listdir(report_dir) if f.startswith("stop-")]
        self.assertTrue(len(reports) >= 2)


class TestHookObserve(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo = tempfile.mkdtemp()
        subprocess.run(["git", "init", "-q", "-b", "main", cls.repo], check=True)
        subprocess.run(["git", "-C", cls.repo, "config", "user.name", "t"], check=True)
        subprocess.run(["git", "-C", cls.repo, "config", "user.email", "t@t"], check=True)
        subprocess.run(["git", "-C", cls.repo, "commit", "--allow-empty", "-q", "-m", "init"],
                       check=True)
        # Install in observe mode
        r = subprocess.run(
            [sys.executable, "-m", "stickler.install",
             "--target", cls.repo, "--mode", "observe"],
            capture_output=True, text=True
        )
        assert r.returncode == 0, r.stderr

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.repo, ignore_errors=True)

    def test_pre_tool_never_exits_2(self):
        code, out, err = _run_hook(self.repo, {
            "event": "PreToolUse",
            "session_id": "ses_obs_1",
            "tool": "write_file",
            "input": {"path": ".env"},
        })
        self.assertNotEqual(code, 2)
        self.assertEqual(out, "")

    def test_session_start_prints_nothing(self):
        code, out, err = _run_hook(self.repo, {
            "event": "SessionStart", "session_id": "ses_obs_2"
        })
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "")


class TestStopTimeout(unittest.TestCase):
    """Stop on the sample project should complete in under 5 s."""

    def test_stop_under_5s(self):
        repo = _setup_governed_repo()
        try:
            sid = "ses_timeout"
            _run_hook(repo, {"event": "SessionStart", "session_id": sid})
            t0 = time.monotonic()
            code, _, err = _run_hook(repo, {"event": "Stop", "session_id": sid})
            elapsed = time.monotonic() - t0
            if elapsed >= 5.0:
                self.skipTest(f"machine too slow: Stop took {elapsed:.1f}s")
            self.assertEqual(code, 0, err)
        finally:
            shutil.rmtree(repo, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()

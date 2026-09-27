import tempfile
import unittest
from pathlib import Path

from shelfkeep.settings import DEFAULT_LOAN_DAYS, load_settings, parse_env_file


class SettingsTest(unittest.TestCase):
    def test_parse_skips_comments_and_blanks(self):
        text = "# comment\n\nA=1\nB = two \nnot a pair\n"
        self.assertEqual(parse_env_file(text), {"A": "1", "B": "two"})

    def test_default_when_no_file(self):
        settings = load_settings("/nonexistent/.env", environ={})
        self.assertEqual(settings.loan_days, DEFAULT_LOAN_DAYS)

    def test_file_then_environment_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = Path(tmp) / ".env"
            env.write_text("SHELFKEEP_LOAN_DAYS=7\n", encoding="utf-8")
            self.assertEqual(load_settings(env, environ={}).loan_days, 7)
            override = {"SHELFKEEP_LOAN_DAYS": "30"}
            self.assertEqual(load_settings(env, environ=override).loan_days, 30)

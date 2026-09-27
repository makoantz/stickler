import time
import unittest

from stickler.regexrun import run_patterns


class RegexRunTest(unittest.TestCase):
    def test_hits(self):
        hits, err = run_patterns([("r1", r"\bgit\s+push\b"), ("r2", "rm -rf")], ["git push origin", "ls"], 2.0)
        self.assertIsNone(err)
        self.assertEqual(hits, [("r1", 0)])

    def test_deadline_kills_catastrophic_pattern(self):
        start = time.monotonic()
        hits, err = run_patterns([("bad", r"(a+)+$")], ["a" * 40 + "b"], 0.5)
        self.assertEqual((hits, err), ([], "regex_timeout"))
        self.assertLess(time.monotonic() - start, 3.0)

    def test_invalid_pattern_is_error(self):
        hits, err = run_patterns([("x", "(")], ["a"], 2.0)
        self.assertEqual(hits, [])
        self.assertTrue(err.startswith("regex_error:"))

    def test_empty_inputs(self):
        self.assertEqual(run_patterns([], ["a"], 1.0), ([], None))

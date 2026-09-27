import unittest

from stickler.globs import any_match, glob_match, glob_to_regex


class GlobTest(unittest.TestCase):
    def test_semantics(self):
        cases = [
            ("src/**", "src/a.py", True), ("src/**", "src/a/b.py", True), ("src/**", "src", False),
            ("src/**", "srcx/a", False), ("**/.env", ".env", True), ("**/.env", "a/b/.env", True),
            ("**/.env", "a/.envx", False), (".env", ".env", True), (".env", "a/.env", False),
            ("*.py", "a.py", True), ("*.py", "d/a.py", False),
            ("tests/**/test_*.py", "tests/test_x.py", True), ("tests/**/test_*.py", "tests/u/test_x.py", True),
            ("a?c", "abc", True), ("a?c", "a/c", False), ("**", "x/y", True), ("a.b", "axb", False),
            ("Src/**", "src/a", False),
        ]
        for glob, path, expected in cases:
            with self.subTest(glob=glob, path=path):
                self.assertEqual(glob_match(glob, path), expected)

    def test_rejects_unsupported(self):
        for bad in ["", "/abs", "a/../b", "./a", "a**", "**b", "x/[ab]", "a{b,c}", "a\\b"]:
            with self.subTest(glob=bad), self.assertRaises(ValueError):
                glob_to_regex(bad)

    def test_none_and_any(self):
        self.assertFalse(glob_match("**", None))
        self.assertTrue(any_match(["x/**", "src/**"], "src/a"))
        self.assertFalse(any_match([], "src/a"))

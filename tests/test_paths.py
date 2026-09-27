import os
import subprocess
import tempfile
import unittest

from stickler.paths import find_root, repo_paths, safe_session_id


class RepoPathsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = self.tmp.name
        self.root = os.path.join(d, "repo")
        os.makedirs(os.path.join(self.root, "src"))
        os.makedirs(os.path.join(d, "outside"))
        os.symlink(os.path.join(d, "outside"), os.path.join(self.root, "link"))
        os.symlink(os.path.join(self.root, ".env"), os.path.join(self.root, "src", "envlink"))

    def tearDown(self):
        self.tmp.cleanup()

    def test_normalisation(self):
        r = self.root
        self.assertEqual(repo_paths("src/a.py", r, r), ("src/a.py", "src/a.py"))
        self.assertEqual(repo_paths("../x", os.path.join(r, "src"), r), ("x", "x"))
        self.assertEqual(repo_paths("../../x", os.path.join(r, "src"), r), (None, None))
        self.assertEqual(repo_paths(os.path.join(r, "src/./a.py"), "/", r), ("src/a.py", "src/a.py"))
        self.assertEqual(repo_paths(".", r, r), (None, None))

    def test_symlinks(self):
        r = self.root
        self.assertEqual(repo_paths("link/f", r, r), ("link/f", None))
        self.assertEqual(repo_paths("src/envlink", r, r), ("src/envlink", ".env"))

    def test_find_root(self):
        r = self.root
        os.makedirs(os.path.join(r, ".stickler"))
        with open(os.path.join(r, ".stickler", "config.json"), "w") as fh:
            fh.write("{}")
        self.assertEqual(find_root(os.path.join(r, "src")), os.path.abspath(r))

    def test_find_root_git_fallback_and_none(self):
        g = os.path.join(self.tmp.name, "g")
        os.makedirs(os.path.join(g, "sub"))
        subprocess.run(["git", "init", "-q", g], check=True)
        self.assertEqual(os.path.realpath(find_root(os.path.join(g, "sub"))), os.path.realpath(g))
        lone = os.path.join(self.tmp.name, "outside")
        if find_root(lone) is not None:
            self.skipTest("temporary directory is inside a git repository")


class SessionIdTest(unittest.TestCase):
    def test_sanitise(self):
        self.assertEqual(safe_session_id("ses_01abc123"), "ses_01abc123")
        self.assertEqual(safe_session_id(None), "nosession")
        s = safe_session_id("../../etc/passwd")
        self.assertNotIn("/", s)
        self.assertFalse(s.startswith("."))
        self.assertLessEqual(len(safe_session_id("x" * 500)), 64)
        self.assertNotEqual(safe_session_id("a/b"), safe_session_id("a_b"))

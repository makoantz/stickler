"""Tests for stickler.install (guide §6, install bullets)."""

import os
import shutil
import subprocess
import tempfile
import unittest


def _git_repo():
    d = tempfile.mkdtemp()
    subprocess.run(["git", "init", "-q", "-b", "main", d], check=True)
    subprocess.run(["git", "-C", d, "config", "user.name", "t"], check=True)
    subprocess.run(["git", "-C", d, "config", "user.email", "t@t"], check=True)
    return d


class TestInstallCompile(unittest.TestCase):
    def test_compile_creates_mode_files_and_validate_sh(self):
        target = _git_repo()
        try:
            import sys
            r = subprocess.run(
                [sys.executable, "-m", "stickler.install",
                 "--target", target, "--mode", "compile"],
                capture_output=True, text=True
            )
            self.assertEqual(r.returncode, 0, r.stderr)
            # .bob/custom_modes.yaml
            self.assertTrue(os.path.isfile(os.path.join(target, ".bob", "custom_modes.yaml")))
            # .stickler/validate.sh
            self.assertTrue(os.path.isfile(os.path.join(target, ".stickler", "validate.sh")))
            # validate.sh is executable
            sh = os.path.join(target, ".stickler", "validate.sh")
            self.assertTrue(os.access(sh, os.X_OK))
        finally:
            shutil.rmtree(target, ignore_errors=True)


class TestInstallObserve(unittest.TestCase):
    def test_observe_creates_settings_json_with_absolute_path(self):
        target = _git_repo()
        try:
            import sys
            r = subprocess.run(
                [sys.executable, "-m", "stickler.install",
                 "--target", target, "--mode", "observe"],
                capture_output=True, text=True
            )
            self.assertEqual(r.returncode, 0, r.stderr)
            settings = os.path.join(target, ".bob", "settings.json")
            self.assertTrue(os.path.isfile(settings))
            with open(settings) as f:
                content = f.read()
            self.assertIn(os.path.abspath(target), content)
        finally:
            shutil.rmtree(target, ignore_errors=True)

    def test_observe_refuses_if_settings_exists(self):
        target = _git_repo()
        try:
            import sys
            os.makedirs(os.path.join(target, ".bob"), exist_ok=True)
            with open(os.path.join(target, ".bob", "settings.json"), "w") as f:
                f.write("{}")
            r = subprocess.run(
                [sys.executable, "-m", "stickler.install",
                 "--target", target, "--mode", "observe"],
                capture_output=True, text=True
            )
            self.assertNotEqual(r.returncode, 0)
        finally:
            shutil.rmtree(target, ignore_errors=True)

    def test_refuses_if_adapters_missing(self):
        """install.py fails if stickler/adapters.json is missing from the package."""
        import stickler.install as inst_mod
        import unittest.mock as mock
        target = _git_repo()
        try:
            # Temporarily remove adapters.json check by patching isfile
            orig_isfile = os.path.isfile
            def patched_isfile(p):
                if p.endswith("adapters.json") and "stickler" in p:
                    return False
                return orig_isfile(p)
            with mock.patch("os.path.isfile", side_effect=patched_isfile):
                import sys
                r = subprocess.run(
                    [sys.executable, "-c",
                     """
import sys, os, unittest.mock as mock
orig = os.path.isfile
def p(path):
    if path.endswith('adapters.json') and 'stickler' in path:
        return False
    return orig(path)
with mock.patch('os.path.isfile', side_effect=p):
    import stickler.install as m
    sys.argv = ['install', '--target', sys.argv[1], '--mode', 'observe']
    m.main()
""", target],
                    capture_output=True, text=True
                )
                self.assertNotEqual(r.returncode, 0)
        finally:
            shutil.rmtree(target, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()

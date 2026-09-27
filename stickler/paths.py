"""Repository root discovery, path normalisation and session-ID sanitising (guide §3.2)."""

import hashlib
import os
import re
import subprocess


def find_root(cwd):
    """Walk up from `cwd` to a directory holding `.stickler/config.json`; fall back to
    `git rev-parse --show-toplevel`; return None if neither is found."""
    d = os.path.abspath(cwd)
    while True:
        if os.path.isfile(os.path.join(d, ".stickler", "config.json")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    try:
        done = subprocess.run(["git", "-C", cwd, "rev-parse", "--show-toplevel"],
                              capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return None
    top = done.stdout.strip()
    return top if done.returncode == 0 and top else None


def _rel(path, bases):
    for base in bases:
        r = os.path.relpath(path, base).replace(os.sep, "/")
        if r != "." and r != ".." and not r.startswith("../"):
            return r
    return None


def repo_paths(raw, cwd, root):
    """Return (lexical, resolved) repo-relative POSIX paths for a tool path argument.

    lexical: `raw` joined to `cwd` and normalised (`.`/`..` removed), symlinks untouched.
    resolved: the same path through os.path.realpath (symlinks followed).
    Either is None when that form lies outside the repository or is the root itself.
    """
    joined = raw if os.path.isabs(raw) else os.path.join(cwd, raw)
    bases = [os.path.abspath(root), os.path.realpath(root)]
    return _rel(os.path.normpath(joined), bases), _rel(os.path.realpath(joined), bases[::-1])


def safe_session_id(raw):
    """A path-safe session ID: [A-Za-z0-9._-], at most 64 characters, not starting with
    a dot; a short hash of the raw value is appended whenever sanitising changed it."""
    raw = str(raw or "nosession")
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", raw)[:64].strip(".") or "session"
    if safe != raw:
        safe = f"{safe[:55]}-{hashlib.sha256(raw.encode()).hexdigest()[:8]}"
    return safe

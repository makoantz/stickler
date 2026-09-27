"""Stickler glob semantics (guide §3.1). Shared by the engine, validator and scorer."""

import functools
import re


@functools.lru_cache(maxsize=1024)
def glob_to_regex(glob):
    """Translate a Stickler glob into an anchored regular expression string.

    Globs are case-sensitive POSIX paths relative to the repository root.
    `*` matches within one segment, `?` one non-`/` character, `**` any number of
    whole segments (it must be a whole segment). `dir/**` matches everything below
    `dir` but not `dir` itself. A glob with no `/` matches at the root only.
    Raises ValueError for absolute paths, `.`/`..` segments, `[`, `{` or `\\`.
    """
    if not glob or glob.startswith("/") or "\\" in glob:
        raise ValueError(f"glob must be a relative POSIX path: {glob!r}")
    if any(seg in (".", "..") for seg in glob.split("/")) or "[" in glob or "{" in glob:
        raise ValueError(f"unsupported glob syntax: {glob!r}")
    out, i, n = [], 0, len(glob)
    while i < n:
        if glob.startswith("**", i):
            whole = (i == 0 or glob[i - 1] == "/") and (i + 2 == n or glob[i + 2] == "/")
            if not whole:
                raise ValueError(f"'**' must be a whole path segment: {glob!r}")
            if i + 2 == n:
                out.append(".*")
                i += 2
            else:
                out.append("(?:[^/]+/)*")
                i += 3
        elif glob[i] == "*":
            out.append("[^/]*")
            i += 1
        elif glob[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(glob[i]))
            i += 1
    return r"\A" + "".join(out) + r"\Z"


@functools.lru_cache(maxsize=1024)
def _compiled(glob):
    return re.compile(glob_to_regex(glob))


def glob_match(glob, path):
    """True if the repo-relative POSIX `path` matches `glob`. `path` None never matches."""
    return path is not None and _compiled(glob).match(path) is not None


def any_match(globs, path):
    return any(glob_match(g, path) for g in globs)

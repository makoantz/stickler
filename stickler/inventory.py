"""File-system inventory (guide §5.6, §3.10)."""

import hashlib
import os
import subprocess


def take_inventory(root: str, config: dict, blob_dir: str = None) -> dict:
    """Build a universe inventory of the repository at `root` (guide §3.10)."""
    from stickler.util import now_utc, sha256_bytes, excl_create

    blob_max = config.get("audit", {}).get("blob_max_bytes", 1048576)
    include_ignored_globs = config.get("audit", {}).get("include_ignored", [])
    engine_owned = config.get("engine_owned_globs", [".stickler/**"])

    # Get head commit
    r = subprocess.run(
        ["git", "-C", root, "rev-parse", "HEAD"],
        capture_output=True, text=True
    )
    head = r.stdout.strip() if r.returncode == 0 else None

    # Collect file sets via git ls-files
    def _ls(extra_args):
        r2 = subprocess.run(
            ["git", "-C", root, "ls-files", "-z"] + extra_args,
            capture_output=True
        )
        raw = r2.stdout
        if not raw:
            return []
        return [p.decode("utf-8", errors="replace")
                for p in raw.split(b"\0") if p]

    tracked = set(_ls(["--cached"]))
    untracked = set(_ls(["--others", "--exclude-standard"]))
    ignored_all = set(_ls(["--others", "--ignored", "--exclude-standard"]))

    # Filter ignored by include_ignored globs
    from stickler.globs import any_match as _any_match

    def _is_engine_owned(p):
        return _any_match(engine_owned, p)

    def _is_include_ignored(p):
        return _any_match(include_ignored_globs, p)

    ignored_included = {p for p in ignored_all if _is_include_ignored(p)}
    ignored_excluded_count = len(ignored_all) - len(ignored_included)

    files = {}
    errors = []

    def _record(rel_path, cat):
        if rel_path.startswith(".git/") or _is_engine_owned(rel_path):
            return
        abs_path = os.path.join(root, rel_path)
        try:
            lstat = os.lstat(abs_path)
        except OSError:
            return  # deleted tracked file — skip
        import stat
        if stat.S_ISLNK(lstat.st_mode):
            try:
                target = os.readlink(abs_path)
            except OSError as exc:
                errors.append(f"readlink {rel_path}: {exc}")
                target = ""
            files[rel_path] = {"type": "symlink", "target": target, "cat": cat}
            return
        if not stat.S_ISREG(lstat.st_mode):
            files[rel_path] = {"type": "other", "cat": cat}
            return
        try:
            with open(abs_path, "rb") as fh:
                data = fh.read()
        except OSError as exc:
            errors.append(f"read {rel_path}: {exc}")
            return
        sha = sha256_bytes(data)
        exec_bit = bool(lstat.st_mode & 0o111)
        entry = {
            "type": "file",
            "size": lstat.st_size,
            "sha256": sha,
            "exec": exec_bit,
            "cat": cat,
        }
        if blob_dir is not None and lstat.st_size <= blob_max:
            blob_path = os.path.join(blob_dir, sha)
            excl_create(blob_path, data)
            entry["blob"] = True
        else:
            entry["blob"] = False
        files[rel_path] = entry

    for p in sorted(tracked):
        _record(p, "tracked")
    for p in sorted(untracked):
        _record(p, "untracked")
    for p in sorted(ignored_included):
        _record(p, "ignored_included")

    return {
        "taken_at": now_utc(),
        "head": head,
        "universe": "tracked+untracked+include_ignored",
        "excluded_ignored_count": ignored_excluded_count,
        "files": files,
        "errors": errors,
    }


def inventory_from_map(files: dict) -> tuple:
    """Build an in-memory inventory from a {path: text_content} map.

    Returns (inventory_dict, content_fn).
    content_fn(sha256) -> bytes | None.
    """
    from stickler.util import sha256_bytes
    blobs = {}
    inv_files = {}
    for path, text in files.items():
        data = text.encode("utf-8") if isinstance(text, str) else text
        sha = sha256_bytes(data)
        blobs[sha] = data
        inv_files[path] = {
            "type": "file",
            "size": len(data),
            "sha256": sha,
            "exec": False,
            "cat": "tracked",
            "blob": True,
        }

    def content_fn(sha):
        return blobs.get(sha)

    inventory = {
        "taken_at": "",
        "head": None,
        "universe": "tracked+untracked+include_ignored",
        "excluded_ignored_count": 0,
        "files": inv_files,
        "errors": [],
    }
    return inventory, content_fn


def blob_content_fn(blob_dir: str):
    """Return a function sha256 -> bytes | None reading from blob_dir."""
    def _fn(sha):
        path = os.path.join(blob_dir, sha)
        try:
            with open(path, "rb") as fh:
                return fh.read()
        except OSError:
            return None
    return _fn

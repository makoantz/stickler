"""Stickler utility helpers (guide §5.1)."""

import contextlib
import datetime
import hashlib
import json
import os
import subprocess
import tempfile
import time


def now_utc() -> str:
    """ISO 8601 UTC timestamp with Z suffix."""
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_file(path: str) -> str:
    """SHA-256 of a file, streamed in 64 KB chunks."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical(obj) -> bytes:
    """Canonical JSON bytes: sorted keys, no spaces, UTF-8."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def read_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path: str, obj) -> None:
    """Write JSON with sorted keys, 2-space indent, trailing newline."""
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, sort_keys=True, indent=2, ensure_ascii=False)
        fh.write("\n")


def write_json_atomic(path: str, obj) -> None:
    """Write JSON atomically: temp file in same directory, then os.replace."""
    dir_ = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=dir_, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, sort_keys=True, indent=2, ensure_ascii=False)
            fh.write("\n")
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def append_jsonl(path: str, obj) -> None:
    """Append one canonical JSON line to path using O_WRONLY|O_CREAT|O_APPEND."""
    line = canonical(obj) + b"\n"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o666)
    try:
        os.write(fd, line)
    finally:
        os.close(fd)


def excl_create(path: str, data: bytes = b"") -> bool:
    """Create path exclusively. Returns False if the file already exists."""
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o666)
        try:
            os.write(fd, data)
        finally:
            os.close(fd)
        return True
    except FileExistsError:
        return False


@contextlib.contextmanager
def lock(path: str, stale_s: int = 60):
    """File-based lock using excl_create. Retries every 50 ms for up to 5 s.

    Yields a dict with key 'took_over' (True if a stale lock was removed).
    """
    deadline = time.monotonic() + 5.0
    took_over = False
    while True:
        if excl_create(path, now_utc().encode()):
            break
        # Check for stale lock
        try:
            age = time.time() - os.path.getmtime(path)
            if age > stale_s:
                os.unlink(path)
                took_over = True
                continue
        except OSError:
            pass
        if time.monotonic() >= deadline:
            raise TimeoutError(f"could not acquire lock {path!r} within 5 s")
        time.sleep(0.05)
    try:
        yield {"took_over": took_over}
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def redact(value, limit: int = 200):
    """Recursively redact strings longer than limit (guide §3.9)."""
    if isinstance(value, str):
        if len(value) > limit:
            return {"len": len(value), "sha256": sha256_bytes(value.encode())}
        return value
    if isinstance(value, dict):
        return {k: redact(v, limit) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v, limit) for v in value]
    return value


def digest_engine(pkg_dir: str) -> str:
    """SHA-256 over sorted lines '<relpath> <sha256>\\n' for every *.py in pkg_dir."""
    import pathlib
    lines = []
    for p in sorted(pathlib.Path(pkg_dir).glob("*.py")):
        lines.append(f"{p.name} {sha256_file(str(p))}\n")
    return sha256_bytes("".join(lines).encode())


def git(root: str, *args, timeout: int = 20):
    """Run git -C root *args. Returns (returncode, stdout_bytes)."""
    result = subprocess.run(
        ["git", "-C", root, *args],
        capture_output=True,
        timeout=timeout,
    )
    return result.returncode, result.stdout

#!/usr/bin/env python3
"""Stickler task-0 probe hook (stdlib only).

Usage (from .bob/settings.json):  python3 <run>/probe/probe_hook.py <role>
  role "log"     : append the redacted payload to .probe/events.jsonl; exit 0.
                   For SessionStart / UserPromptSubmit also print a context marker.
  role "control_any" : registered with no matcher; applies only the probe_block_ case,
                   so blocking (E4) is tested whatever the file tool is called.
  role "control" : registered with a tool matcher; controlled cases keyed on marker
                   substrings in the tool input:
                   probe_block_  -> reason on stderr, exit 2
                   probe_exit1_  -> exit 1
                   probe_sleep_  -> start marker, sleep 8 s, done marker, exit 0
The log directory is the directory two levels above this file, i.e. the run root.
"""

import datetime
import hashlib
import json
import os
import sys
import time

RUN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(RUN_ROOT, ".probe")
MARKER = "STICKLER-PROBE-MARKER-7Q"
REASON = "STICKLER-REASON-4K7: blocked by the Stickler probe (controlled case)"
SHORT = 200


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def redact(value):
    """Keep structure and short strings; replace long strings by length + sha256."""
    if isinstance(value, dict):
        return {k: redact(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, str) and len(value) > SHORT:
        digest = hashlib.sha256(value.encode("utf-8", "replace")).hexdigest()
        return {"_redacted": True, "len": len(value), "sha256": digest}
    return value


def strings(value):
    if isinstance(value, dict):
        for v in value.values():
            yield from strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from strings(v)
    elif isinstance(value, str):
        yield value


def append(name, record):
    os.makedirs(LOG_DIR, exist_ok=True)
    line = json.dumps(record, sort_keys=True) + "\n"
    fd = os.open(os.path.join(LOG_DIR, name), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        os.write(fd, line.encode("utf-8"))
    finally:
        os.close(fd)


def main():
    role = sys.argv[1] if len(sys.argv) > 1 else "log"
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw)
        parsed = True
    except ValueError:
        payload, parsed = {}, False
    event = payload.get("event") if isinstance(payload, dict) else None
    base = {
        "ts": now(), "role": role, "pid": os.getpid(), "cwd": os.getcwd(),
        "parsed": parsed, "raw_len": len(raw), "event": event,
        "tool": payload.get("tool") if isinstance(payload, dict) else None,
        "top_keys": sorted(payload) if isinstance(payload, dict) else None,
        "env_keys": sorted(k for k in os.environ if k.upper().startswith(("BOB", "IBM"))),
    }
    if role == "log":
        append("events.jsonl", dict(base, payload=redact(payload)))
        if event in ("SessionStart", "UserPromptSubmit"):
            print(f"{MARKER} event={event} (printed by the Stickler probe hook)")
        return 0

    if role not in ("control", "control_any"):
        sys.stderr.write(f"probe: unknown role {role}\n")
        return 0
    texts = list(strings(payload.get("input", {}) if isinstance(payload, dict) else {}))
    joined = "\n".join(texts)
    base["markers"] = sorted({t[t.index("probe_"):][:40] for t in texts if "probe_" in t})
    if "probe_block_" in joined:
        append("control.jsonl", dict(base, case="block", exit=2))
        sys.stderr.write(REASON + "\n")
        return 2
    if role == "control_any":
        append("control.jsonl", dict(base, case="none", exit=0))
        return 0
    if "probe_exit1_" in joined:
        append("control.jsonl", dict(base, case="exit1", exit=1))
        sys.stderr.write("probe: controlled exit 1\n")
        return 1
    if "probe_sleep_" in joined:
        append("control.jsonl", dict(base, case="sleep", phase="start", t=time.time()))
        time.sleep(8)
        append("control.jsonl", dict(base, case="sleep", phase="done", t=time.time()))
        return 0
    append("control.jsonl", dict(base, case="none", exit=0))
    return 0


if __name__ == "__main__":
    sys.exit(main())

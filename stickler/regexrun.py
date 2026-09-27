"""Run generated regexes under a hard deadline (SOW §4.1C). Never call re on
generated patterns in the hook or audit process itself; always go through here."""

import json
import os
import subprocess
import sys

WORKER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "regex_worker.py")


def run_patterns(patterns, texts, deadline_s):
    """Evaluate [(key, pattern), ...] against `texts` in a child process.

    Returns (hits, error): hits is a list of (key, text_index); error is None,
    "regex_timeout" or "regex_error: <message>". When error is set, hits is empty
    and the caller applies the configured on_error policy.
    """
    if not patterns or not texts:
        return [], None
    request = json.dumps({"patterns": [list(p) for p in patterns], "texts": list(texts)})
    try:
        done = subprocess.run([sys.executable, "-I", WORKER], input=request, capture_output=True,
                              text=True, timeout=deadline_s)
    except subprocess.TimeoutExpired:
        return [], "regex_timeout"
    if done.returncode != 0:
        lines = done.stderr.strip().splitlines() or ["unknown error"]
        return [], "regex_error: " + lines[-1][:200]
    return [tuple(h) for h in json.loads(done.stdout)["hits"]], None

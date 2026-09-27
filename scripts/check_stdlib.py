#!/usr/bin/env python3
"""Acceptance A1: every import in this repository is standard library or local."""

import ast
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
LOCAL = {"stickler", "shelfkeep", "tests", "probe"}
bad = []
for path in sorted(ROOT.rglob("*.py")):
    if any(part in {".git", "results", "__pycache__", ".venv"} for part in path.relative_to(ROOT).parts):
        continue
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        names = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names = [node.module]
        for name in names:
            top = name.split(".")[0]
            if top not in sys.stdlib_module_names and top not in LOCAL:
                bad.append(f"{path.relative_to(ROOT)}: {name}")
print("\n".join(bad) if bad else "stdlib-only: OK")
sys.exit(1 if bad else 0)

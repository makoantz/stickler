"""Adapter loading, route matrix and kind-bucket derivation (guide §5.2, §3.3, §3.4)."""

import argparse
import re
import sys

from stickler.util import read_json, write_json

# Valid operations per guide §3.3
_VALID_OPERATIONS = {"read", "write", "create", "delete", "rename", "execute", "other"}

# Field-path pattern: a.b, a[].b, etc.
_FIELD_PATH_RE = re.compile(
    r"^[A-Za-z_]\w*(\[\])?(\.[A-Za-z_]\w*(\[\])?)*$"
)

# All six check kinds
_KINDS = [
    "deny_path",
    "allow_paths_only",
    "forbid_file_deletion",
    "deny_command",
    "require_paired_change",
    "deny_diff_pattern",
]


def load_adapters(path: str) -> dict:
    """Load and validate adapters.json (guide §3.3). Raises ValueError on bad shape."""
    doc = read_json(path)
    if not isinstance(doc, dict):
        raise ValueError("adapters.json must be a JSON object")
    if "tools" not in doc or not isinstance(doc["tools"], dict):
        raise ValueError("adapters.json missing 'tools' object")
    for tool_name, entry in doc["tools"].items():
        if not isinstance(entry, dict):
            raise ValueError(f"tool {tool_name!r}: entry must be an object")
        op = entry.get("operation")
        if op not in _VALID_OPERATIONS:
            raise ValueError(
                f"tool {tool_name!r}: unknown operation {op!r}; "
                f"must be one of {sorted(_VALID_OPERATIONS)}"
            )
        for key in ("paths", "from", "to", "command", "cwd"):
            val = entry.get(key)
            if val is None:
                continue
            if key == "paths":
                if not isinstance(val, list):
                    raise ValueError(f"tool {tool_name!r}: 'paths' must be a list")
                for fp in val:
                    if not isinstance(fp, str) or not _FIELD_PATH_RE.match(fp):
                        raise ValueError(
                            f"tool {tool_name!r}: invalid field path {fp!r} in 'paths'"
                        )
            else:
                if not isinstance(val, str) or not _FIELD_PATH_RE.match(val):
                    raise ValueError(
                        f"tool {tool_name!r}: invalid field path {val!r} for key {key!r}"
                    )
    return doc


def route_matrix(adapters: dict) -> dict:
    """Build the route matrix per guide §3.4.

    Returns {kind: {tool: {"status": "supported"|"unsupported", "reason": str}}}
    Omits tools that are irrelevant to a kind.
    """
    matrix = {k: {} for k in _KINDS}

    for tool_name, entry in adapters["tools"].items():
        op = entry.get("operation")
        paths = entry.get("paths", [])
        has_paths = bool(paths)
        has_from = bool(entry.get("from"))
        has_to = bool(entry.get("to"))
        has_command = bool(entry.get("command"))

        # deny_path and allow_paths_only: write, create, delete, rename
        if op in ("write", "create", "delete", "rename"):
            if op == "rename":
                if has_from and has_to:
                    status, reason = "supported", "rename with from/to fields"
                else:
                    status, reason = "unsupported", "rename missing from or to field"
            else:
                if has_paths:
                    status, reason = "supported", f"{op} with paths field"
                else:
                    status, reason = "unsupported", f"{op} missing paths field"
            matrix["deny_path"][tool_name] = {"status": status, "reason": reason}
            matrix["allow_paths_only"][tool_name] = {"status": status, "reason": reason}

        # forbid_file_deletion: delete, rename
        if op in ("delete", "rename"):
            if op == "rename":
                if has_from:
                    status, reason = "supported", "rename source via from field"
                else:
                    status, reason = "unsupported", "rename missing from field"
            else:
                if has_paths:
                    status, reason = "supported", "delete with paths field"
                else:
                    status, reason = "unsupported", "delete missing paths field"
            matrix["forbid_file_deletion"][tool_name] = {"status": status, "reason": reason}

        # deny_command: execute
        if op == "execute":
            if has_command:
                status, reason = "supported", "execute with command field"
            else:
                status, reason = "unsupported", "execute missing command field"
            matrix["deny_command"][tool_name] = {"status": status, "reason": reason}

        # require_paired_change, deny_diff_pattern are always audit — no per-tool routing needed

    return matrix


def kind_buckets(matrix: dict) -> dict:
    """Derive kind buckets from the route matrix per guide §3.4."""
    buckets = {}

    for kind in ("deny_path", "allow_paths_only"):
        tools = matrix.get(kind, {})
        has_supported = any(v["status"] == "supported" for v in tools.values())
        buckets[kind] = "block" if has_supported else "audit"

    # forbid_file_deletion
    tools = matrix.get("forbid_file_deletion", {})
    has_supported = any(v["status"] == "supported" for v in tools.values())
    buckets["forbid_file_deletion"] = "block" if has_supported else "audit"

    # deny_command
    tools = matrix.get("deny_command", {})
    has_supported = any(v["status"] == "supported" for v in tools.values())
    buckets["deny_command"] = "block" if has_supported else "unsupported"

    # require_paired_change and deny_diff_pattern are always audit
    buckets["require_paired_change"] = "audit"
    buckets["deny_diff_pattern"] = "audit"

    return buckets


def main():
    parser = argparse.ArgumentParser(description="Derive kind-buckets and route matrix from adapters")
    parser.add_argument("--adapters", default="stickler/adapters.json")
    parser.add_argument("--buckets", default="stickler/kind-buckets.json")
    parser.add_argument("--matrix", default="results/route-matrix.json")
    args = parser.parse_args()

    import hashlib, json, os
    from stickler.util import sha256_file

    adapters = load_adapters(args.adapters)
    adapters_sha = sha256_file(args.adapters)

    matrix = route_matrix(adapters)
    buckets = kind_buckets(matrix)

    # Write kind-buckets.json
    os.makedirs(os.path.dirname(args.buckets) or ".", exist_ok=True)
    write_json(args.buckets, {"kind_buckets": buckets, "adapters_sha256": adapters_sha})

    # Write route-matrix.json
    os.makedirs(os.path.dirname(args.matrix) or ".", exist_ok=True)
    write_json(args.matrix, {"adapters_sha256": adapters_sha, "matrix": matrix})

    for kind, bucket in buckets.items():
        print(f"  {kind}: {bucket}")


if __name__ == "__main__":
    main()

"""Adapter field resolution and op extraction (guide §5.3)."""


def resolve_field(obj, field_path: str):
    """Collect string values at field_path from obj.

    Segments separated by '.'; '[]' suffix on a segment means iterate a list.
    Returns list[str] or None (missing, wrong type, or empty result).
    """
    parts = field_path.split(".")
    current = [obj]
    for part in parts:
        if part.endswith("[]"):
            key = part[:-2]
            next_ = []
            for item in current:
                if not isinstance(item, dict):
                    return None
                val = item.get(key)
                if val is None:
                    return None
                if not isinstance(val, list):
                    return None
                next_.extend(val)
            current = next_
        else:
            next_ = []
            for item in current:
                if not isinstance(item, dict):
                    return None
                val = item.get(part)
                if val is None:
                    return None
                next_.append(val)
            current = next_

    # All collected values must be strings
    result = []
    for v in current:
        if not isinstance(v, str):
            return None
        result.append(v)
    return result if result else None


def extract_ops(tool: str, tool_input: dict, adapters: dict):
    """Extract operations from a tool call.

    Returns (ops, coverage, error) where:
    - ops: list of {"operation", "paths", "from", "to", "command", "cwd"}
    - coverage: "ok" | "unknown_tool" | "unsupported_route" | "malformed"
    - error: str or None
    """
    tools = adapters.get("tools", {})

    if tool not in tools:
        return [{"operation": "other", "paths": [], "from": None, "to": None,
                 "command": None, "cwd": None}], "unknown_tool", None

    entry = tools[tool]
    op = entry.get("operation", "other")

    # Read and other operations — always OK
    if op in ("read", "other"):
        return [{"operation": op, "paths": [], "from": None, "to": None,
                 "command": None, "cwd": None}], "ok", None

    # Resolve cwd (optional for any operation)
    cwd = None
    if "cwd" in entry:
        cwd_vals = resolve_field(tool_input, entry["cwd"])
        if cwd_vals:
            cwd = cwd_vals[0]

    # Check for unsupported route
    if op in ("write", "create", "delete"):
        path_fields = entry.get("paths", [])
        if not path_fields:
            return [{"operation": op, "paths": [], "from": None, "to": None,
                     "command": None, "cwd": cwd}], "unsupported_route", None
        # Resolve each path field
        paths = []
        for fp in path_fields:
            vals = resolve_field(tool_input, fp)
            if vals is None:
                return [{"operation": op, "paths": [], "from": None, "to": None,
                         "command": None, "cwd": cwd}], "malformed", \
                       f"field {fp!r} missing or non-string in tool input"
            paths.extend(vals)
        return [{"operation": op, "paths": paths, "from": None, "to": None,
                 "command": None, "cwd": cwd}], "ok", None

    if op == "rename":
        from_fp = entry.get("from")
        to_fp = entry.get("to")
        if not from_fp or not to_fp:
            return [{"operation": op, "paths": [], "from": None, "to": None,
                     "command": None, "cwd": cwd}], "unsupported_route", None
        from_vals = resolve_field(tool_input, from_fp)
        to_vals = resolve_field(tool_input, to_fp)
        if from_vals is None:
            return [{"operation": op, "paths": [], "from": None, "to": None,
                     "command": None, "cwd": cwd}], "malformed", \
                   f"field {from_fp!r} missing or non-string in tool input"
        if to_vals is None:
            return [{"operation": op, "paths": [], "from": None, "to": None,
                     "command": None, "cwd": cwd}], "malformed", \
                   f"field {to_fp!r} missing or non-string in tool input"
        return [{"operation": op, "paths": [], "from": from_vals[0], "to": to_vals[0],
                 "command": None, "cwd": cwd}], "ok", None

    if op == "execute":
        cmd_fp = entry.get("command")
        if not cmd_fp:
            return [{"operation": op, "paths": [], "from": None, "to": None,
                     "command": None, "cwd": cwd}], "unsupported_route", None
        cmd_vals = resolve_field(tool_input, cmd_fp)
        if cmd_vals is None:
            return [{"operation": op, "paths": [], "from": None, "to": None,
                     "command": None, "cwd": cwd}], "malformed", \
                   f"field {cmd_fp!r} missing or non-string in tool input"
        return [{"operation": op, "paths": [], "from": None, "to": None,
                 "command": cmd_vals[0], "cwd": cwd}], "ok", None

    # Fallback for unknown op (shouldn't reach here after load_adapters validation)
    return [{"operation": op, "paths": [], "from": None, "to": None,
             "command": None, "cwd": cwd}], "ok", None

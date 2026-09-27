"""Diff inventories and audit findings (guide §5.7, §3.11)."""

import difflib
import re

from stickler.globs import any_match
from stickler.regexrun import run_patterns


def diff_inventories(base: dict, final: dict) -> dict:
    """Compute changes between two inventories (guide §3.11).

    Returns {"added", "modified", "deleted", "renamed", "type_changed", "mode_changed"}.
    """
    base_files = base.get("files", {})
    final_files = final.get("files", {})

    base_keys = set(base_files)
    final_keys = set(final_files)

    added_raw = final_keys - base_keys
    deleted_raw = base_keys - final_keys
    common = base_keys & final_keys

    modified = []
    type_changed = []
    mode_changed = []

    for p in sorted(common):
        b = base_files[p]
        f = final_files[p]
        if b.get("type") != f.get("type"):
            type_changed.append(p)
        elif b.get("type") == "file":
            if b.get("sha256") != f.get("sha256"):
                modified.append(p)
            elif b.get("exec") != f.get("exec"):
                mode_changed.append(p)
        elif b.get("type") == "symlink":
            if b.get("target") != f.get("target"):
                modified.append(p)

    # Rename detection: pair deleted with added of same sha256 (file only), sorted order
    sha_to_deleted = {}
    for p in sorted(deleted_raw):
        b = base_files[p]
        if b.get("type") == "file":
            sha = b.get("sha256")
            if sha and sha not in sha_to_deleted:
                sha_to_deleted[sha] = p

    sha_to_added = {}
    for p in sorted(added_raw):
        f = final_files[p]
        if f.get("type") == "file":
            sha = f.get("sha256")
            if sha and sha not in sha_to_added:
                sha_to_added[sha] = p

    renamed = []
    rename_deleted = set()
    rename_added = set()
    for sha, dp in sorted(sha_to_deleted.items()):
        if sha in sha_to_added:
            ap = sha_to_added[sha]
            renamed.append([dp, ap])
            rename_deleted.add(dp)
            rename_added.add(ap)

    added = sorted(added_raw - rename_added)
    deleted = sorted(deleted_raw - rename_deleted)

    return {
        "added": added,
        "modified": modified,
        "deleted": deleted,
        "renamed": renamed,
        "type_changed": type_changed,
        "mode_changed": mode_changed,
    }


def is_text(b: bytes) -> bool:
    """True if bytes decode as UTF-8 with no NUL byte."""
    if b"\x00" in b:
        return False
    try:
        b.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


def added_lines(old_bytes, new_bytes: bytes) -> list:
    """Return [(line_no_in_new, text)] for added lines in a unified diff."""
    # Normalise line endings
    def _norm(b):
        if b is None:
            return []
        return b.decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n").splitlines(keepends=True)

    old_lines = _norm(old_bytes)
    new_lines = _norm(new_bytes)

    result = []
    # Use unified_diff with n=0 to get only changed hunks
    diff = list(difflib.unified_diff(old_lines, new_lines, n=0))
    # Parse hunk headers to track new-file line numbers
    new_line_no = 0
    for line in diff:
        if line.startswith("@@"):
            # @@ -a,b +c,d @@
            m = re.search(r"\+(\d+)", line)
            if m:
                new_line_no = int(m.group(1))
        elif line.startswith("+") and not line.startswith("+++"):
            text = line[1:]
            result.append((new_line_no, text))
            new_line_no += 1
        elif not line.startswith("-") and not line.startswith("---"):
            new_line_no += 1

    return result


def audit(base: dict, final: dict, rules: list, config: dict,
          content_base, content_final) -> tuple:
    """Run the final-state audit. Returns (findings, unsupported, errors).

    content_base / content_final: callable(sha256) -> bytes | None.
    """
    from stickler.util import redact as _redact

    changes = diff_inventories(base, final)
    engine_owned = config.get("engine_owned_globs", [".stickler/**"])
    control_globs = list(config.get("control_globs", [])) + list(engine_owned)
    deadline = config.get("limits", {}).get("audit_regex_deadline_ms", 20000) / 1000

    def _is_control(p):
        return p is not None and any_match(control_globs, p)

    # Collect all changed paths (for path-kind rules)
    changed_paths = set(
        changes["added"] + changes["modified"] + changes["deleted"] +
        changes["type_changed"] + changes["mode_changed"]
    )
    for frm, to in changes["renamed"]:
        changed_paths.add(frm)
        changed_paths.add(to)

    findings = []
    unsupported = []
    errors = []

    for rule in rules:
        rid = rule.get("id", "")
        check = rule.get("check") or {}
        kind = check.get("kind")
        if not kind:
            continue

        is_builtin = rid.startswith("builtin:")

        if kind == "deny_path":
            globs = check.get("globs", [])
            for p in sorted(changed_paths):
                if not is_builtin and _is_control(p):
                    continue
                if any_match(globs, p):
                    findings.append({"rule_id": rid, "kind": kind,
                                     "paths": [p], "message": rule.get("text", ""), "line": None})

        elif kind == "allow_paths_only":
            globs = check.get("globs", [])
            for p in sorted(changed_paths):
                if not is_builtin and _is_control(p):
                    continue
                if not any_match(globs, p):
                    findings.append({"rule_id": rid, "kind": kind,
                                     "paths": [p], "message": rule.get("text", ""), "line": None})

        elif kind == "forbid_file_deletion":
            globs = check.get("globs", [])
            delete_paths = list(changes["deleted"])
            for frm, _ in changes["renamed"]:
                delete_paths.append(frm)
            for p in sorted(set(delete_paths)):
                if not is_builtin and _is_control(p):
                    continue
                if any_match(globs, p):
                    findings.append({"rule_id": rid, "kind": kind,
                                     "paths": [p], "message": rule.get("text", ""), "line": None})

        elif kind == "require_paired_change":
            when_globs = check.get("when_changed", [])
            req_globs = check.get("require_changed", [])
            triggers = [p for p in sorted(changed_paths) if any_match(when_globs, p)]
            if triggers:
                satisfied = any(any_match(req_globs, p) for p in changed_paths)
                if not satisfied:
                    findings.append({"rule_id": rid, "kind": kind,
                                     "paths": sorted(triggers),
                                     "message": rule.get("text", ""), "line": None})

        elif kind == "deny_diff_pattern":
            globs = check.get("globs", [])
            patterns = check.get("patterns", [])
            candidate_paths = [p for p in (changes["added"] + changes["modified"])
                               if any_match(globs, p)]
            for p in candidate_paths:
                final_entry = final.get("files", {}).get(p)
                if final_entry is None:
                    continue
                sha = final_entry.get("sha256")
                new_bytes = content_final(sha) if sha else None
                if new_bytes is None:
                    unsupported.append({"rule_id": rid, "path": p,
                                        "reason": "content_unavailable"})
                    continue
                if not is_text(new_bytes):
                    unsupported.append({"rule_id": rid, "path": p, "reason": "binary"})
                    continue
                # Get old bytes for diff
                base_entry = base.get("files", {}).get(p)
                old_bytes = None
                if base_entry and base_entry.get("sha256"):
                    old_bytes = content_base(base_entry["sha256"])
                lines = added_lines(old_bytes, new_bytes)
                if not lines:
                    continue
                texts = [t for _, t in lines]
                line_nos = [n for n, _ in lines]
                pattern_list = [(rid, pat) for pat in patterns]
                hits, err = run_patterns(pattern_list, texts, deadline)
                if err:
                    errors.append(f"{p}: {err}")
                    continue
                for _, text_idx in hits:
                    line_no = line_nos[text_idx]
                    text = _redact(texts[text_idx])
                    text_str = text if isinstance(text, str) else str(text)
                    findings.append({
                        "rule_id": rid, "kind": kind,
                        "paths": [p],
                        "message": f"line {line_no}: {text_str[:200]}",
                        "line": line_no,
                    })

    return findings, unsupported, errors


def control_integrity(base: dict, final: dict, config: dict,
                      pinned: dict, root: str) -> dict:
    """Check control-file and engine integrity."""
    from stickler.util import sha256_file, digest_engine
    import os

    control_globs = list(config.get("control_globs", [])) + list(config.get("engine_owned_globs", []))
    changes = diff_inventories(base, final)
    all_changed = set(
        changes["added"] + changes["modified"] + changes["deleted"] +
        changes["type_changed"] + changes["mode_changed"]
    )
    for frm, to in changes["renamed"]:
        all_changed.add(frm)
        all_changed.add(to)

    changed_control = sorted(p for p in all_changed if any_match(control_globs, p))

    # Check engine digests against pinned pointer
    engine_ok = True
    try:
        engine_dir = os.path.join(root, ".stickler", "engine", "stickler")
        if os.path.isdir(engine_dir):
            current_engine_sha = digest_engine(engine_dir)
            if current_engine_sha != pinned.get("engine_sha256"):
                engine_ok = False
    except Exception:
        engine_ok = False

    return {"changed": changed_control, "engine_ok": engine_ok}

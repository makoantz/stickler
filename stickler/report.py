"""Report rendering (guide §5.9)."""


def render_stop_md(report: dict) -> str:
    """Render a stop report dict to Markdown."""
    lines = []
    sid = report.get("session", "?")
    stop = report.get("stop", "?")
    status = report.get("status", "?")
    incomplete_reason = report.get("incomplete_reason")

    lines.append(f"# Stickler stop report: session {sid}, stop {stop}")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"**Status:** {status}" +
                 (f" ({incomplete_reason})" if incomplete_reason else ""))
    lines.append(f"**Policy SHA-256:** `{report.get('policy_sha256', '?')}`")
    lines.append(f"**Baseline commit:** `{report.get('baseline_head', '?')}`")
    lines.append(f"**Final commit:** `{report.get('final_head', '?')}`")
    commits = report.get("commits", [])
    if commits:
        lines.append("")
        lines.append("**Commits during session:**")
        for c in commits:
            lines.append(f"- `{c}`")

    lines.append("")
    lines.append("## Findings")
    lines.append("")
    findings = report.get("findings", [])
    if findings:
        for f in findings:
            p = ", ".join(f.get("paths", []))
            msg = f.get("message", "")
            lines.append(f"- **{f['rule_id']}** `{p}`: {msg}")
    else:
        lines.append("No findings.")

    lines.append("")
    lines.append("## Unsupported")
    lines.append("")
    unsupported = report.get("unsupported", [])
    if unsupported:
        for u in unsupported:
            lines.append(f"- `{u['path']}` ({u['reason']}) — {u['rule_id']}")
    else:
        lines.append("None.")

    lines.append("")
    lines.append("## Control integrity")
    lines.append("")
    ci = report.get("control_integrity", {})
    changed = ci.get("changed", [])
    if changed:
        lines.append(f"**Changed control paths:** {', '.join(f'`{p}`' for p in changed)}")
    else:
        lines.append("No control-path changes.")
    lines.append(f"**Engine digest match:** {'yes' if ci.get('engine_ok') else 'no'}")

    lines.append("")
    lines.append("## Changes")
    lines.append("")
    changes = report.get("changes", {})
    for category in ("added", "modified", "deleted", "renamed", "type_changed", "mode_changed"):
        items = changes.get(category, [])
        if items:
            lines.append(f"**{category.capitalize()}:**")
            for item in items:
                if isinstance(item, list):
                    lines.append(f"- `{item[0]}` → `{item[1]}`")
                else:
                    lines.append(f"- `{item}`")

    lines.append("")
    lines.append("## Limits")
    lines.append("")
    lines.append(report.get("limits", ""))
    lines.append("")
    return "\n".join(lines)


def summary_lines(active_count: int, policy_sha: str, blocks: list,
                  reports: list, pin_sha: str, first: bool = False) -> list:
    """Build the summary lines printed at SessionStart / UserPromptSubmit (§3.12)."""
    out = []
    if first:
        sha_short = policy_sha[:8] if policy_sha else "?"
        out.append(f"[Stickler] {active_count} rules active (policy {sha_short})."
                   " Blocked actions and audit findings are reported here.")

    if blocks:
        n = len(blocks)
        noun = "action was" if n == 1 else "actions were"
        out.append(f"[Stickler] Since your last prompt, {n} {noun} blocked:")
        for b in blocks:
            rule_id = b.get("rule_id", "?")
            tool = b.get("tool", "?")
            path = b.get("path", "")
            text = b.get("text", "")
            line = f"- {tool}"
            if path:
                line += f" {path}"
            line += f": rule {rule_id}"
            if text:
                line += f" \"{text}\""
            out.append(line)

    for name, rep in reports:
        sid = rep.get("session", "?")
        stop = rep.get("stop", "?")
        rep_sha = rep.get("policy_sha256", "")
        rep_findings = rep.get("findings", [])
        n = len(rep_findings)
        stale = " (stale: different policy)" if rep_sha and rep_sha != pin_sha else ""
        report_path = rep.get("_report_path", "?")
        out.append(
            f"[Stickler] Audit of session {sid} stop {stop}: "
            f"{n} finding{'s' if n != 1 else ''} (report {report_path}){stale}:"
        )
        for f in rep_findings[:20]:
            p = ", ".join(f.get("paths", []))
            msg = f.get("message", "")
            out.append(f"- {f['rule_id']} {p}: {msg}")

    # Cap at 20 lines
    if len(out) > 20:
        extra = len(out) - 19
        out = out[:19] + [f"... and {extra} more"]

    return out


def render_rules_report(doc: dict, validation: dict, active: list) -> str:
    """Render stickler/REPORT.md from the rules doc and validation results."""
    lines = []
    lines.append("# Stickler rules report")
    lines.append("")

    rules = doc.get("rules", [])
    active_ids = set(active)

    for bucket in ("block", "audit"):
        bucket_rules = [r for r in rules if r.get("bucket") == bucket]
        if not bucket_rules:
            continue
        lines.append(f"## {bucket.capitalize()} rules")
        lines.append("")
        lines.append("| ID | Source | Text | Schema | Cases | Routes | Installed |")
        lines.append("|---|---|---|---|---|---|---|")
        for rule in bucket_rules:
            rid = rule["id"]
            src = rule.get("source", {})
            src_str = f"{src.get('path','?')}:{src.get('start_line','?')}"
            text = rule.get("text", "")
            val = validation.get("rules", {}).get(rid, {})
            schema_ok = "✓" if val.get("schema_valid") else "✗"
            cases = val.get("generated_tests", {})
            cur = cases.get("current", {})
            case_str = f"{cur.get('passed',0)}p/{cur.get('failed',0)}f"
            routes = val.get("routes", "not yet measured")
            installed = "✓" if rid in active_ids else "✗"
            lines.append(f"| `{rid}` | `{src_str}` | {text} | {schema_ok} | {case_str} | {routes} | {installed} |")
        lines.append("")

    # Judgment rules
    judgment_rules = [r for r in rules if r.get("bucket") == "judgment"]
    if judgment_rules:
        lines.append("## Judgment rules")
        lines.append("")
        for rule in judgment_rules:
            rid = rule["id"]
            jr = rule.get("judgment_reason", "?")
            text = rule.get("text", "")
            rationale = rule.get("rationale", "")
            lines.append(f"- `{rid}` ({jr}): {text}  \n  _{rationale}_")
        lines.append("")

    lines.append("## Limits")
    lines.append("")
    lines.append(_LIMITS_TEXT)
    lines.append("")
    lines.append("## Note on deny_command")
    lines.append("")
    lines.append(
        "Command matching is lexical, not shell-interpreted. "
        "Quoting, variables, aliases, `sh -c` wrappers and scripts can defeat it."
    )
    lines.append("")
    return "\n".join(lines)


_LIMITS_TEXT = (
    "The audit sees final state only. A forbidden change that was later reverted is invisible. "
    "An unchanged tree does not show that no forbidden action was attempted. "
    "Attempts are known only from the PreToolUse log, and only on supported routes."
)

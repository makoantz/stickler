#!/usr/bin/env python3
"""Summarise a task-0 probe run into results/hook-surface.json and .md.

Usage: python3 probe/analyze.py <probe run folder> [--out results]
Automatic verdicts come from the hook logs and the file system. E5 and E6 depend
on Bob's replies and are left as OWNER fields to fill from the transcript.
"""

import argparse
import json
import os
import sys

DOC = "https://bob.ibm.com/docs/ide/configuration/lifecycle-hooks (checked 2026-09-27)"


def load(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def verdict(status, evidence):
    return {"status": status, "evidence": evidence}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("--out", default="results")
    args = ap.parse_args()
    run = os.path.abspath(args.run)
    events = load(os.path.join(run, ".probe", "events.jsonl"))
    control = load(os.path.join(run, ".probe", "control.jsonl"))
    exists = lambda rel: os.path.lexists(os.path.join(run, rel))
    by_event = {}
    for e in events:
        by_event.setdefault(e.get("event") or "<unparsed>", []).append(e)

    tools = {}
    for e in by_event.get("PreToolUse", []):
        name = e.get("tool") or "<none>"
        entry = tools.setdefault(name, {"count": 0, "input_keys": set(), "samples": []})
        entry["count"] += 1
        inp = e.get("payload", {}).get("input")
        if isinstance(inp, dict):
            entry["input_keys"].update(inp)
        if len(entry["samples"]) < 3:
            entry["samples"].append(inp)
    for entry in tools.values():
        entry["input_keys"] = sorted(entry["input_keys"])

    E = {}
    pre = by_event.get("PreToolUse", [])
    need = {"event", "session_id", "tool", "input"}
    if not pre:
        E["E1"] = verdict("untested", "no PreToolUse events logged")
    else:
        missing = sorted({t for e in pre for t in need - set(e.get("top_keys") or [])})
        E["E1"] = verdict("conform" if not missing else "deviate",
                          {"events": len(pre), "missing_fields": missing,
                           "top_keys_seen": sorted({k for e in pre for k in e.get("top_keys") or []})})
    post = by_event.get("PostToolUse", [])
    if not post:
        E["E2"] = verdict("untested", "no PostToolUse events logged")
    else:
        with_output = sum(1 for e in post if "output" in (e.get("top_keys") or []))
        shapes = sorted({type(e.get("payload", {}).get("output")).__name__ for e in post})
        exitish = sorted({k for e in post for k in e.get("top_keys") or [] if "exit" in k.lower() or "code" in k.lower()})
        E["E2"] = verdict("conform" if with_output == len(post) else "deviate",
                          {"events": len(post), "with_output": with_output,
                           "output_types": shapes, "exit_code_like_keys": exitish})
    for eid, name in (("E3a", "SessionStart"), ("E3b", "Stop")):
        evs = by_event.get(name, [])
        if not evs:
            E[eid] = verdict("untested", f"no {name} events logged")
            continue
        keys = sorted({k for e in evs for k in e.get("top_keys") or []})
        ok = {"event", "session_id"} <= set(keys)
        E[eid] = verdict("conform" if ok and set(keys) == {"event", "session_id"} else
                         ("conform_with_extra_fields" if ok else "deviate"),
                         {"events": len(evs), "keys": keys})

    blocks = [c for c in control if c.get("case") == "block"]
    for eid, rel in (("E4_file", "fixture/probe_block_file.txt"), ("E4_cmd", "fixture/probe_block_cmd.txt")):
        stem = os.path.basename(rel).split(".")[0]
        hits = [c for c in blocks if any(m.startswith(stem) for m in c.get("markers") or [])]
        if not hits:
            E[eid] = verdict("untested", f"no controlled block case for {rel} reached a hook")
        else:
            E[eid] = verdict("deviate" if exists(rel) else "conform",
                             {"target": rel, "exists_after_run": exists(rel),
                              "block_hook_calls": [(c.get("role"), c.get("tool")) for c in hits]})
    E["E5"] = verdict("OWNER", "Did Bob quote STICKLER-REASON-4K7 (Prompt 1 steps 9-10, Prompt 2 b)? "
                               "conform = reason reached Bob; deviate = not; untested = step not reached")
    E["E6"] = verdict("OWNER", "Did Bob quote STICKLER-PROBE-MARKER-7Q (step 13, Prompt 2 a)? "
                               "conform / deviate / untested")
    cwds = sorted({os.path.realpath(e.get("cwd") or "") for e in events})
    if not cwds:
        E["E7_cwd"] = verdict("untested", "no events logged")
    else:
        E["E7_cwd"] = verdict("conform" if cwds == [os.path.realpath(run)] else "deviate",
                              {"run_root": run, "cwds_seen": cwds})
    sleep_start = [c for c in control if c.get("case") == "sleep" and c.get("phase") == "start"]
    sleep_done = [c for c in control if c.get("case") == "sleep" and c.get("phase") == "done"]
    if not sleep_start:
        E["E7_timeout"] = verdict("untested", "sleep case never started")
    else:
        E["E7_timeout"] = verdict("empirical", {
            "configured_timeout_s": 3, "hook_sleep_s": 8,
            "start_markers": len(sleep_start), "done_markers": len(sleep_done),
            "tool_ran (file exists)": exists("fixture/probe_sleep_file.txt"),
            "note": "The docs set the timeout but do not state the outcome; this is an observation, "
                    "not conformance. A missing done marker means the hook was killed or is unknown."})
    exit1 = [c for c in control if c.get("case") == "exit1"]
    if not exit1:
        E["E8"] = verdict("untested", "exit-1 case never reached a hook")
    else:
        ran = exists("fixture/probe_exit1_file.txt")
        E["E8"] = verdict("conform" if ran else "deviate", {"tool_ran (file exists)": ran})
    matched = [c for c in control if c.get("role") == "control"]
    if not matched:
        E["E9"] = verdict("untested", "the matcher-scoped control hook never ran")
    else:
        names = sorted({c.get("tool") or "<none>" for c in matched})
        E["E9"] = verdict("conform" if set(names) <= {"write_file", "execute_command"} else "deviate",
                          {"tools_reaching_matcher_hooks": names})

    fixture = sorted(os.listdir(os.path.join(run, "fixture"))) if os.path.isdir(os.path.join(run, "fixture")) else []
    result = {"run": run, "doc": DOC, "event_counts": {k: len(v) for k, v in sorted(by_event.items())},
              "tools": tools, "expectations": E, "fixture_after_run": fixture,
              "session_ids": sorted({(e.get("payload") or {}).get("session_id", "") for e in events})}
    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "hook-surface.json"), "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2, sort_keys=True, default=str)
        fh.write("\n")
    lines = ["# Hook-surface probe results", "", f"Run folder: `{run}`  ", f"Reference: {DOC}", "",
             "| ID | Status | Evidence |", "|---|---|---|"]
    for eid, v in E.items():
        ev = v["evidence"] if isinstance(v["evidence"], str) else json.dumps(v["evidence"], default=str)
        lines.append(f"| {eid} | {v['status']} | {ev.replace('|', '/')} |")
    lines += ["", "## Tools seen in PreToolUse", "", "| Tool | Calls | Input keys |", "|---|---|---|"]
    for name, t in sorted(tools.items()):
        lines.append(f"| `{name}` | {t['count']} | {', '.join(t['input_keys'])} |")
    lines += ["", f"Fixture after run: {', '.join(fixture)}", "",
              "OWNER: replace the two OWNER rows using Bob's replies, then record the v1 narrowing "
              "(guide §5a) below.", "", "## v1 narrowing", "", "(to be filled)"]
    with open(os.path.join(args.out, "hook-surface.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"wrote {args.out}/hook-surface.json and hook-surface.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())

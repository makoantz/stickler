## 3. Shared contracts

These are normative. `stickler/SCHEMA.md` (stage 5b-3) is a copy of this section.

### 3.1 Globs

Implemented in `stickler/globs.py` [B]; read its docstring. The mode file `02-spec-format.md` states the same rules for Bob-the-compiler. The same functions are used everywhere; never use `fnmatch` or `pathlib.match`.

### 3.2 Paths

Implemented in `stickler/paths.py` [B]:
- `find_root(cwd)`;
- `repo_paths(raw, cwd, root)`, which returns `(lexical, resolved)`;
- `safe_session_id(raw)`.

Rules applied to every path-bearing operation:
- `deny_path` and `forbid_file_deletion` match if **either** the lexical or the resolved path matches.
- `allow_paths_only` passes only if **both** are non-None **and** both match.
- A rename is a delete of `from` plus a create of `to`.
- **Control paths** are `config.control_globs` plus `config.engine_owned_globs`. They are exempt from user rules. The built-in rule `builtin:control-files` (governed mode only) is a `deny_path` over them, and is excluded from all metrics.

### 3.3 `stickler/adapters.json`

```json
{
  "adapter_version": 1,
  "confirmed_by_probe": "probe-1",
  "tools": {
    "<tool name exactly as seen>": {
      "operation": "read | write | create | delete | rename | execute | other",
      "paths": ["<field path>", "..."],
      "from": "<field path>",
      "to": "<field path>",
      "command": "<field path>",
      "cwd": "<field path>"
    }
  }
}
```

- **Field paths:** `a.b` for nested keys; `a[].b` to collect `b` from every element of list `a`. A resolved value can be a string or a list of strings.
- **Which keys apply:**
  - `paths` for write, create and delete;
  - `from` and `to` for rename;
  - `command` for execute;
  - `cwd` is optional for any operation.
- **Supported versus malformed:**
  - A mutating tool with `"paths": []`, or with `from`/`to` missing, is an **unsupported route**. It is allowed and logged as `coverage: unsupported_route`.
  - A tool whose adapter names a field, but whose payload lacks it or has a non-string value there, is **malformed**. It is blocked when `config.missing_path_field == "block"`.
  - A tool not listed is `coverage: unknown_tool` and allowed.
- **Contents:** only tools observed in the probe, with fields observed in the probe. Record anything uncertain in the v1-narrowing section of `results/hook-surface.md`, not in the JSON.

### 3.4 Kind buckets and the route matrix (`routes.py`)

For each adapter tool, the route relevance per kind:

| operation | deny_path, allow_paths_only | forbid_file_deletion | deny_command |
|---|---|---|---|
| write, create | supported if `paths` non-empty, else unsupported | â€” | â€” |
| delete | supported if `paths` non-empty, else unsupported | supported if `paths` non-empty | â€” |
| rename | supported if `from` and `to` set | supported if `from` set | â€” |
| execute | unsupported: "shell effects are not interpreted; final-state audit only" | same | supported if `command` set, else unsupported |
| read, other | â€” | â€” | â€” |

The buckets follow from the table:
- `deny_path` and `allow_paths_only` are `block` if any route is supported, else `audit`.
- `forbid_file_deletion` is `block` if any delete or rename route is supported, else `audit`.
- `deny_command` is `block` if any execute route is supported, else `"unsupported"`.
- `require_paired_change` and `deny_diff_pattern` are always `audit`.

Output files:
- `stickler/kind-buckets.json`: `{"kind_buckets": {<kind>: "block|audit|unsupported"}, "adapters_sha256": "<hex>"}`.
- `results/route-matrix.json`: `{"adapters_sha256": ..., "matrix": {<kind>: {<tool>: {"status": "supported|unsupported", "reason": "..."}}}}`. Tools that are irrelevant to a kind are omitted.

### 3.5 Specs (`stickler/rules.json`)

- **Format:** exactly as in `stickler/mode/rules-stickler/02-spec-format.md` [B], which is normative for Bob-the-compiler. The same file defines the extract format and the case formats.
- **The validator's schema rules** (each violation is a `schema_errors` string on that rule):
  - `id` is unique and matches `^[a-z0-9-]+:[0-9]+:[0-9]+$`.
  - `source.path` exists under the root. `1 â‰¤ start_line â‰¤ end_line â‰¤` the file's line count. `quote`, whitespace-collapsed, occurs in the whitespace-collapsed text of those lines.
  - `bucket` âˆˆ {block, audit, judgment}.
  - For judgment: `judgment_reason` âˆˆ {human, mechanical_unsupported, duplicate, conflict}, `check` is null, and `cases` is empty.
  - For block or audit: `judgment_reason` is null, and `check.kind` is one of the six kinds, with exactly its parameters. Each is a non-empty list of strings: every glob accepted by `glob_to_regex`, every pattern accepted by Â§3.6. Also `bucket == kind_buckets[kind]`.
  - `duplicate_of` names an existing rule that is not itself a duplicate. `conflicts_with` entries exist and are symmetric.
  - Block rules have at least 3 `pre_tool` cases, with at least one `allow` and one `block`. Audit rules have at least 3 `final_state` cases, with at least one `clean` and one `finding`. Every case `tool` is an adapter tool.

### 3.6 Pattern screening (validator only; runtime bounding is `regexrun.py`)

A pattern is rejected if any of these holds:
- it is longer than `limits.max_pattern_len`;
- `re.compile` fails;
- it contains a backreference (`\1`â€“`\9`, `(?P=`);
- it contains a lookaround (`(?=`, `(?!`, `(?<=`, `(?<!`);
- it contains a group that has a quantifier inside and is itself followed by `*`, `+`, `?` or `{`. Detect this by scanning with a stack of "group contains quantifier" flags; it need not be perfect.
- It fails `run_patterns([(id, p)], [STRESS...], limits.screen_deadline_ms/1000)`. `STRESS` is `["a"*5000+"!", "/"*5000, " "*5000+"x", "ab"*2500]`.

More than `limits.max_patterns` patterns across the active policy is a validation error on the rule that crosses the limit.

### 3.7 Config (`.stickler/config.json`)

This is `stickler/config.default.json` [B] plus `"mode": "compile" | "observe" | "governed"`, which `install.py` adds. Meanings:
- `on_error` (allow or block): the verdict whenever the engine cannot decide. This covers an exception, a missing or mismatched snapshot, `regex_timeout`, `regex_error`, or an over-long command while `deny_command` rules are active.
- `missing_path_field`: see Â§3.3.
- `audit.include_ignored`: ignored files that are nevertheless in the audit universe.
- `audit.blob_max_bytes`: content retention limit.
- `limits.*`: as named.

### 3.8 Active policy and pinning

- **Snapshot** `.stickler/active/rules.<sha>.json`: `{"rules": [<activated rule objects>], "builtin": [<builtin rules>]}`, serialised canonically (`json.dumps(obj, sort_keys=True, separators=(",", ":"))`). `<sha>` is the SHA-256 of those bytes.
- **Pointer** `.stickler/active.json`:
  - `rules_sha256`;
  - `engine_sha256`: see `util.digest_engine`;
  - `adapters_sha256`, `kind_buckets_sha256`, `config_sha256`: the SHA-256 of each file's bytes;
  - `activated`: a list of IDs;
  - `excluded`: a list of `{id, reason}`;
  - `activated_at`.

  It is written to `active.json.tmp`, then `os.replace`d.
- **Verification** on load: every digest must match the files on disk. Any mismatch gives `coverage: error` with reason `digest_mismatch:<which>`.
- **Pin** `state/<sid>/pinned.json` is created with `O_EXCL` at a session's first event, and holds a copy of the pointer. The hook always evaluates the pinned `rules_sha256` snapshot. If the current pointer's `rules_sha256` differs from the pin, log `policy_changed_mid_session` once per session.
- **Built-in rule** (governed mode only): `{"id": "builtin:control-files", "bucket": "block", "check": {"kind": "deny_path", "globs": control_globs + engine_owned_globs}}`.
- **Observe mode:** the policy is empty and there are no built-in rules. It logs events, records the baseline, runs the audit at Stop, and prints nothing.

### 3.9 Event log (`state/<sid>/events.jsonl`)

One JSON object per line, written with a single `os.write` on an `O_APPEND` descriptor (`util.append_jsonl`):

```json
{"ts": "...", "event": "PreToolUse", "session": "<sid>", "tool": "write_file",
 "ops": [{"operation": "write", "targets": [["src/a.py", "src/a.py"]], "command": null}],
 "decision": "allow|block|none", "rule_ids": [], "coverage": "ok|unknown_tool|unsupported_route|malformed|error",
 "error": null, "elapsed_ms": 12, "policy_sha256": "..."}
```

**Redaction:**
- Every string longer than 200 characters, commands included, is replaced by `{"len": n, "sha256": hex}`.
- `PostToolUse` records only `output_len` and `output_sha256`.
- File contents in tool input are never logged. Only the adapter-named fields are logged.

### 3.10 Inventory (`baseline.json`, `final-<n>.json`)

```json
{"taken_at": "...", "head": "<commit or null>", "universe": "tracked+untracked+include_ignored",
 "excluded_ignored_count": 3,
 "files": {"<path>": {"type": "file", "size": 10, "sha256": "...", "exec": false, "cat": "tracked|untracked|ignored_included",
                     "blob": true}},
 "errors": []}
```

- Symlinks: `{"type": "symlink", "target": "<readlink>"}`. Other file types: `{"type": "other"}`.
- `blob` is true when `blobs/<sha256>` holds the bytes (size â‰¤ `blob_max_bytes`).
- The universe is built with `git ls-files -z`: `--cached`, then `--others --exclude-standard`, then `--others --ignored --exclude-standard`. The last list is filtered by `include_ignored`; the rest of it is counted, not listed.
- Paths under `.git/`, and paths matching `engine_owned_globs`, are dropped.
- Cached paths that no longer exist on disk are skipped.

### 3.11 Stop report (`reports/<sid>/stop-<n>.json` and a rendered `.md`)

```json
{"session": "<sid>", "stop": 1, "status": "complete | incomplete", "incomplete_reason": null,
 "policy_sha256": "...", "baseline_head": "...", "final_head": "...", "commits": ["<sha> <subject>"],
 "changes": {"added": [], "modified": [], "deleted": [], "renamed": [["from", "to"]], "type_changed": [], "mode_changed": []},
 "findings": [{"rule_id": "...", "kind": "...", "paths": ["..."], "message": "...", "line": null}],
 "unsupported": [{"rule_id": "...", "path": "...", "reason": "content_unavailable | binary"}],
 "control_integrity": {"changed": ["<control path>"], "engine_ok": true},
 "excluded_ignored_count": 3, "shared_worktree": false, "errors": [],
 "limits": "<fixed text from SOW Â§4.1E, final bullet>"}
```

- `replay-stop-<n>.json` sits next to the state. It names the baseline, the final inventory, the blob directory, the snapshot file and all pointer digests, so that `replay.py` can re-run the audit.
- The outbox marker is `outbox/<sid>--stop-<n>.json` with `{"report": "<relative path>", "policy_sha256": ...}`.

### 3.12 Summary text (stdout at `SessionStart` and `UserPromptSubmit`; governed mode only)

```
[Stickler] 9 rules active (policy 1a2b3c4d5e6f). Blocked actions and audit findings are reported here.
[Stickler] Since your last prompt, 1 action was blocked:
- write_file .env: rule 01-project-rules:3:1 "Never edit or delete .env."
[Stickler] Audit of session ses_x stop 1: 2 findings (report .stickler/reports/ses_x/stop-1.md):
- 01-project-rules:9:1 src/shelfkeep/loans.py: added line matches a forbidden pattern
```

- The first line appears at `SessionStart` only.
- Output is capped at 20 lines, with `... and N more` at the end.
- A report whose `policy_sha256` differs from the session's pin gets the suffix `(stale: different policy)`.
- After printing, markers move to `outbox/delivered/`, and `blocks_pending.jsonl` is renamed to `blocks_delivered-<ts>.jsonl`.

### 3.13 Block message (stderr, `PreToolUse` exit 2)

```
Stickler blocked this write_file call: rule 01-project-rules:3:1 (.bob/rules/01-project-rules.md line 3): "Never edit or delete .env."
```

For errors under `on_error: block`, the message is `Stickler blocked this <tool> call: it could not evaluate the call (<reason>).` It is one line per blocking rule, at most 5 lines.

### 3.14 Evaluation files (hidden until stage 5d; formats needed now for the scorer)

- `corpus/<set>/reference.json`:
  ```json
  {"set": "authored",
   "rules": [{"ref_id": "A01",
              "source": {"path": "...", "start_line": 3, "end_line": 3, "quote": "..."},
              "text": "...", "duplicate_group": null, "conflict_with": [], "ambiguous": false,
              "label": {"bucket": "block", "judgment_reason": null, "kind": "deny_path",
                        "status": "resolved"}}]}
  ```
- `corpus/<set>/labels_model.json` and `labels_human.json`: `{"annotator": "...", "labels": {"A01": {"bucket": ..., "judgment_reason": ..., "kind": ...}}}`.
- `corpus/<set>/matching.json`: `{"pairs": [{"ref_id": "A01", "bob_id": "...", "verdict": "match|no_match|pending", "note": ""}]}`.
- `eval/<set>/cases.json`:
  ```json
  {"cases": [{"id": "IC001", "type": "pre_tool", "tool": "...", "input": {...},
              "expected": {"decision": "block", "rule_ids": ["A01"]},
              "per_rule": {"A01": "block", "A04": "allow"}},
             {"id": "IC040", "type": "final_state", "baseline": {...}, "final": {...},
              "expected": {"findings": ["A07"]}, "per_rule": {"A07": "finding"}}]}
  ```
- `eval/attempts.json`:
  ```json
  {"attempts": [{"attempt_id": "X01", "ref_rule_ids": ["A01"], "prompt": "...",
                 "supported_routes": ["write_file"],
                 "effect": {"type": "file_changed|file_created|file_deleted|remote_refs_changed",
                            "path": "..."},
                 "control": {"shell": "printf 'X=1\\n' >> .env"}}]}
  ```

### 3.15 Effect snapshots and records (`results/raw/<run>/effects/`)

- **`<attempt>-before.json` and `-after.json`:**
  - an inventory without blobs (Â§3.10);
  - `remote_refs` (`git --git-dir <remote> show-ref` lines);
  - `event_offsets`: the byte size of every `events.jsonl`;
  - `ts`.
- **`<attempt>-record.json`:**
  - `attempt_id`;
  - `observed_calls`: the `PreToolUse` events appended after the before-offsets, as `{tool, ops, decision, rule_ids, coverage}`;
  - `changed_paths`;
  - `remote_refs_changed`;
  - `errors`;
  - `owner_note: ""`.
- **Outcome classification** (SOW Â§8.3) happens in `score.py`, not here, because it needs the matching.


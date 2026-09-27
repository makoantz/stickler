# Stickler spec format

## Doc slug and rule IDs

- Doc slug: the file name without extension, lower-cased, with every run of
  characters outside `a-z0-9` replaced by `-`. If two sources share a slug, prefix
  the parent folder's slug and `-`.
- Rule ID: `<doc-slug>:<start_line>:<n>`, where `n` counts rules starting on that
  line (1, 2, ...). Lines are 1-based.

## Extract file: `stickler/extract/<doc-slug>.json`

    {"source": "<path from repo root>", "doc_slug": "<slug>",
     "rules": [{"id": "<id>", "start_line": 5, "end_line": 5,
                "quote": "<verbatim text from those lines>",
                "text": "<the single rule, restated in one sentence>"}]}

An atomic rule is one obligation or one prohibition. A sentence that states two
("never do X, and never do Y") is two rules with the same span. Headings, context
and explanations are not rules. `quote` must appear verbatim within the span.

## `stickler/rules.json`

    {"schema_version": 1,
     "sources": ["<path>", ...],
     "rules": [{
       "id": "...", "source": {"path": "...", "start_line": 5, "end_line": 5, "quote": "..."},
       "text": "...",
       "bucket": "block" | "audit" | "judgment",
       "judgment_reason": null | "human" | "mechanical_unsupported" | "duplicate" | "conflict",
       "rationale": "<one line>",
       "duplicate_of": null | "<id of the first rule, in source order, with the same meaning>",
       "conflicts_with": [],
       "check": null | {"kind": "...", ...},
       "cases": []}]}

A duplicate or conflicting rule gets `bucket: "judgment"`, the matching
`judgment_reason`, `check: null` and no cases. The rule it duplicates is classified
normally.

## Decision procedure (one bucket per rule)

1. Could one of the six kinds below express the rule **exactly**, with globs or
   patterns taken from the rule's own words? If yes, `bucket` is
   `kind-buckets.json[kind]`. If that value is `"unsupported"`, use `judgment` with
   `mechanical_unsupported`.
2. If a program could in principle check the rule, but no kind expresses it exactly
   (only approximately, or not at all), use `judgment` with `mechanical_unsupported`.
   Put the missing capability in `rationale`.
3. Otherwise, use `judgment` with `human`.

Never invent paths, globs or patterns that the rule text does not imply.

## Check kinds

| kind | parameters | meaning |
|---|---|---|
| `deny_path` | `globs` | No file matching a glob may be created, written, deleted or renamed (either end). |
| `allow_paths_only` | `globs` | Every created, written, deleted or renamed file must match a glob. |
| `deny_command` | `patterns` | No command string may contain a match for a pattern (Python `re.search`). |
| `forbid_file_deletion` | `globs` | No file matching a glob may be deleted (a rename counts as deleting its source). |
| `require_paired_change` | `when_changed`, `require_changed` | If a file matching `when_changed` changed, a file matching `require_changed` must also change. |
| `deny_diff_pattern` | `globs`, `patterns` | No line added to a matching text file may contain a match for a pattern. |

Globs are POSIX paths relative to the repository root and are case-sensitive.
`*` matches within one path segment, `?` one character, `**` any number of whole
segments. `dir/**` matches everything below `dir`. A glob with no `/` matches at the
root only: `.env` does not match `app/.env`; use `**/.env` for any depth.

Patterns: at most 200 characters, no backreferences, no lookarounds, and no
quantified group containing a quantifier (for example `(a+)+`).

## Cases

    {"name": "...", "type": "pre_tool", "tool": "<adapter tool name>",
     "input": {<fields named in adapters.json>}, "expect": "allow" | "block"}

    {"name": "...", "type": "final_state",
     "baseline": {"<path>": "<text content>", ...},
     "final": {"<path>": "<text content>", ...},
     "expect": "clean" | "finding"}

Paths in cases are relative to the repository root. In `final_state` cases a file
missing from `final` was deleted. Block rules need `pre_tool` cases; audit rules
need `final_state` cases. The engine tests each case against that rule alone.

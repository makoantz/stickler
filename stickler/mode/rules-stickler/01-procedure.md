# Stickler procedure

You compile a project's prose rules into Stickler specs. You never write executable
code. You create or edit files only under `stickler/`. Stop and report if you pass
60 tool calls.

## Inputs

- Rule sources: every file under `.bob/rules/` (not `.bob/rules-stickler/`), plus
  `AGENTS.md` and `CONTRIBUTING.md` at the root if present, plus any path the user
  names. In a public-corpus run the sources are every file under `rules-src/`.
- `.stickler/adapters.json`: the tool names and input fields the engine understands.
- `.stickler/kind-buckets.json`: the bucket each check kind gets in this
  installation. It is fixed. Do not edit it.
- `02-spec-format.md` in this folder: every file format and the decision procedure.

## Steps

1. **Extract.** For each source document write `stickler/extract/<doc-slug>.json`.
   If you have the subagent tool, give each subagent one document (at most 3 running
   at once). Tell it the document path, its doc slug, to read both files in
   `.bob/rules-stickler/`, and to write only its extract file within 15 tool calls.
   If a subagent fails or its file is missing, extract that document yourself. Never
   retry a subagent. Without subagents, do the documents one after another.
2. **Merge** all extract files into `stickler/rules.json`. Keep every extracted
   rule. Mark duplicates with `duplicate_of` and contradictions with
   `conflicts_with` (both sides).
3. **Classify** each rule with the decision procedure in `02-spec-format.md`.
4. **Specify.** For each block or audit rule write `check` and at least three
   `cases`: one allowed, one violating, and one boundary case (for example a sibling
   path that must stay allowed).
5. **Validate.** Run `sh .stickler/validate.sh`. Read `stickler/validation.json`.
   A failing rule may be repaired at most twice: edit it, validate again. Do not edit
   passing rules. After two repairs, leave the rule failing.
6. **Report.** Run `sh .stickler/validate.sh --report`. It writes
   `stickler/REPORT.md`. Never write REPORT.md yourself.
7. **Finish** with one short message: rules per bucket, failing rules, and anything
   you could not decide.

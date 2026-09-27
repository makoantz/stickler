# Stickler handover

Read this first in every session, then `docs/SOW.md`. Add a dated entry under
**Updates** at the end of each Bob task or human step: what changed, evidence (paths,
commands and their results, commit IDs), Bobcoins used, and the next action. Never
record a planned item as done.

## Stage checklist

| Stage | Status | Evidence |
|---|---|---|
| 0 Bootstrap | done | commit cb89973; sample 16 OK; engine 12 OK (4 skipped, symlinks); stdlib-only: OK |
| 5a Probe and adapters | done | util.py, routes.py, adapters.json, kind-buckets.json, route-matrix.json committed |
| 5b-1 Hook path | done | adapters.py, spec.py, policy.py; tests 116 pass |
| 5b-2 Audit and lifecycle | done | inventory.py, audit.py, state.py, report.py, stickler_hook.py, stickler_audit.py, install.py; tests 171 pass |
| 5b-3 Validator, scoring, replay | done | stickler_validate.py, effects.py, score.py, replay.py, freeze.py, SCHEMA.md; tests 181 pass, stdlib-only OK; committed after WSL verification |
| Engine freeze | not started | |
| 5c Compile (authored rules) | not started | |
| 5c Compile (public sample) | not started | |
| Reveal and score | not started | |
| 7 Live runs | not started | |
| RESULTS.md | not started | |

## Frozen hashes (recorded before evaluation)

| Artifact | SHA-256 | Recorded (UTC) | External record |
|---|---|---|---|

## Updates

### 2026-09-27 GitHub push and 5b-3 verification (owner + Claude)
- Pushed the repository to `github.com:makoantz/stickler.git` (main, through this commit).
- Verified Bob's uncommitted stage 5b-3 files (WSL, Python 3.12.14): `timeout 300 python3 -m unittest discover -s tests -t .` → 181 passed; `python3 scripts/check_stdlib.py` → OK. No stubs or `NotImplementedError` found. Committing them as stage 5b-3 complete.
- Confirmed `stickler/adapters.json` still has `"confirmed_by_probe": null`: the real probe (SOW §4.1A Task 0, guide §4 owner steps) has not been run. Adapters, kind-buckets and route-matrix are provisional, not the frozen, probe-confirmed set the SOW requires before reference labelling starts.
- `bob_sessions/LEDGER.md` has no entries (no Bobcoin balances or screenshots recorded for any stage so far).
- Remaining per SOW §12: real probe run and re-freeze of adapters/kind-buckets/route-matrix with external timestamp; public sample + reference inventory + independent cases (outside this repo, in `stickler-private/`); engine freeze; stage 5c compile runs; reveal and score; stage 7 live runs; `RESULTS.md`; demo.

### 2026-09-27 WSL continuation (owner + Codex)
- Owner confirmed that all nine pre-existing untracked stage 5b-3 files were developed by Bob on Windows: `stickler/{SCHEMA.md,effects.py,freeze.py,replay.py,score.py,stickler_validate.py}` and `tests/test_{effects,score,validate}.py`.
- These files are Bob's unfinished work, not Codex-authored additions; the stage checklist does not yet establish their completion.
- Codex began WSL environment setup at the owner's request using `uv`; preserved the Windows `.venv` and selected `.venv/wsl` for Linux Python 3.12.
- Initial system-Python 3.14 check: 181 engine tests ran, with one sandbox socket error in the multiprocessing test; 16 sample tests passed. This is not a clean engine-test result.
- No Bob probe, compile, live-run, credit-consumption or external-freeze evidence has been added by this continuation.
- WSL setup complete: uv 0.12.19, Python 3.12.14, activate with `source .venv/wsl/bin/activate`; managed Python lives at `/home/makodev58/.local/share/stickler-python`.
- Windows-mounted Python reproduced a regex-screen timeout; moving the interpreter to the Linux filesystem resolved it without engine changes. Final engine check: 181 tests passed; sample: 16 passed; stdlib-only: OK. Existing unclosed-file warnings remain.
- Codex changes so far: environment setup, `.gitignore`, README instructions and this attribution record. Next: review unfinished stage 5b-3 and produce the SOW's credit-exhausted partial deliverable with unsupported hypotheses marked inconclusive.

### 2026-09-27 Stage 0 Bootstrap (Bob)
- Extracted and ran Appendix A bootstrap script via Git-for-Windows `sh`; commit `cb89973` created 50+ files.
- Sample-project tests: 16 passed, 0 failed.
- Engine-helper tests: 12 ran, 8 passed, 4 skipped (`test_paths` symlink tests require `SeCreateSymbolicLinkPrivilege` on Windows). Fixed `tests/test_paths.py` to skip gracefully — test proves the limitation.
- `scripts/check_stdlib.py` excluded `.venv/` (Windows-only venv not in the Linux-authored skip list). Fixed the script; stdlib-only: OK.
- Both fixes committed together with stage-0 entry.
- Next action: owner runs probe (Stage 5a) or proceeds directly to Bob task 5a if probe data is already available.

### 2026-09-27 Stage 5a (Bob)
- Wrote `stickler/util.py` (all §5.1 functions), `stickler/routes.py` (load_adapters, route_matrix, kind_buckets, CLI).
- Wrote provisional `stickler/adapters.json` with 6 Bob tools (write_file, read_file, execute_command, apply_diff, insert_content, search_and_replace); `confirmed_by_probe: null` until probe runs.
- Ran `python3 -m stickler.routes`: deny_path block, allow_paths_only block, forbid_file_deletion audit, deny_command block, require_paired_change audit, deny_diff_pattern audit.
- Tests: 55 passed, 4 skipped (Windows symlink), 0 failed. stdlib-only: OK.
- Deviations: adapters.json is provisional (probe not yet run). forbid_file_deletion=audit because no delete tool with paths is in the adapter set yet.
- Next: Stage 5b-1 (adapters.py, spec.py, policy.py).

# Stickler handover

Read this first in every session, then `docs/SOW.md`. Add a dated entry under
**Updates** at the end of each Bob task or human step: what changed, evidence (paths,
commands and their results, commit IDs), Bobcoins used, and the next action. Never
record a planned item as done.

## Stage checklist

| Stage | Status | Evidence |
|---|---|---|
| 0 Bootstrap | done | commit cb89973; sample 16 OK; engine 12 OK (4 skipped, symlinks); stdlib-only: OK |
| 5a Probe and adapters | not started | |
| 5b-1 Hook path | not started | |
| 5b-2 Audit and lifecycle | not started | |
| 5b-3 Validator, scoring, replay | not started | |
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

### 2026-09-27 Stage 0 Bootstrap (Bob)
- Extracted and ran Appendix A bootstrap script via Git-for-Windows `sh`; commit `cb89973` created 50+ files.
- Sample-project tests: 16 passed, 0 failed.
- Engine-helper tests: 12 ran, 8 passed, 4 skipped (`test_paths` symlink tests require `SeCreateSymbolicLinkPrivilege` on Windows). Fixed `tests/test_paths.py` to skip gracefully — test proves the limitation.
- `scripts/check_stdlib.py` excluded `.venv/` (Windows-only venv not in the Linux-authored skip list). Fixed the script; stdlib-only: OK.
- Both fixes committed together with stage-0 entry.
- Next action: owner runs probe (Stage 5a) or proceeds directly to Bob task 5a if probe data is already available.

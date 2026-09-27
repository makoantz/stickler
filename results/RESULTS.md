# Stickler results

**Status: partial deliverable, credit-exhausted (SOW §10).** Bob's Bobcoin balance
was exhausted during the build (stage 5b-3, engine work); no probe, compile, or
live-run Bob session has taken place. Every hypothesis below is reported as
**inconclusive**, with its denominator and the reason, per SOW §3 ("a denominator
below the stated minimum makes the outcome inconclusive... a zero denominator is
reported as 'n = 0', never as 0% or 100%"). This is a negative-by-omission result,
not a favourable one, and it is published as such.

As of commit `ebd4217` (2026-09-27), branch `main`.

## 1. What exists

| Deliverable (SOW §9) | State |
|---|---|
| D1 Probe kit, results, adapters, kind buckets, route matrix | Probe kit present (`probe/`), **never run**. `stickler/adapters.json` has `"confirmed_by_probe": null` — it is Bob's stage-5a provisional guess, not the frozen probe output. `stickler/kind-buckets.json` and `results/route-matrix.json` are derived from that provisional file, not from an observed hook surface. `results/hook-surface.json`/`.md` do not exist. |
| D2 Stickler custom mode and procedure files | Present (`stickler/mode/`), from the bootstrap; never exercised by a Bob compile session. |
| D3 Engine, adapters, validator, audit, lifecycle, effects, scorer, replay, with unit tests | Complete. `stickler/` implements all modules through stage 5b-3 (`util`, `routes`, `adapters`, `spec`, `policy`, `inventory`, `audit`, `state`, `report`, `stickler_hook`, `stickler_audit`, `install`, `stickler_validate`, `effects`, `score`, `replay`, `freeze`). `timeout 300 python3 -m unittest discover -s tests -t .` → 181 passed, 0 failed. `python3 scripts/check_stdlib.py` → OK. Engine freeze (`freeze.py --label ...`, a `git tag`) has not been run, so there is no recorded engine manifest hash. |
| D4 `stickler/SCHEMA.md` | Present, a copy of guide §3. |
| D5 Sample project (shelfkeep) | Present (`sample-project/`), with 16 prose rules across `.bob/rules/01-project-rules.md` (12) and `AGENTS.md` (7). |
| D6 Public sample, reference inventory, annotation sets, matching | **Not started.** `corpus/` is empty. No reference inventory was drafted, so there is nothing for Bob's output to be scored against even if a compile run existed. |
| D7 Independent cases and attempt list | **Not started.** `eval/` is empty. |
| D8 Results, raw evidence, replay manifests, hashes | This file. `results/raw/` holds no run data (`.gitkeep` only). |
| D9 Consumption screenshots and Bobcoin ledger | `bob_sessions/LEDGER.md` exists but has **no entries** — no balances, no per-stage screenshots. The owner has screen recordings from the Bob build sessions (stages 0 through 5b-3) that have not been placed in `bob_sessions/`; there is **no recording of Stickler in use** (no probe, compile, or live-run footage), because credits ran out before any of those sessions were attempted. |
| D10 README, demo | README describes the design; `demo/` is empty (`.gitkeep` only). |

## 2. Hypotheses (SOW §3)

| ID | Hypothesis | Result | n / denominator | Reason |
|---|---|---|---|---|
| H1 | Block+Audit ≥ 30% of atomic rules | **Inconclusive** | n = 0 resolved reference rules | No reference inventory was built (D6 not started); the 30% share cannot be computed against anything reference-labelled. |
| H2 | Bob's extraction/classification matches the reference inventory | **Inconclusive** | n = 0 reference rules, n = 0 credited pairs | No compile run was ever executed, so Bob produced no `rules.json` for shelfkeep or the public sample to match against a reference set that itself does not exist. |
| H3a | Bob's specs pass Bob's own generated cases | **Inconclusive** | n = 0 Block/Audit rules with generated cases | Same cause: no compile run, so no Bob-authored specs or cases exist to validate. |
| H3b | Bob's specs give correct whole-policy verdicts on frozen independent cases | **Inconclusive** | n = 0 reference Block/Audit rules | No independent cases exist (D7 not started) and no activated Bob policy exists to evaluate them against. |
| H4 | Every observed violating tool call on a supported route is prevented | **Inconclusive** | Eligible = 0 | No live session (plain, governed-natural, or governed-attempt) was ever run. Zero tool calls were observed under any Stickler policy, so there are zero eligible attempts, matching the SOW's explicit "Eligible = 0 → inconclusive" condition. |
| H5 | Bob's hook surface behaves as IBM documents it (E1–E9) | **Inconclusive** | 0 of 9 items tested | The probe (Task 0) was never run. All nine items (E1–E9) are untested, well under the "fewer than 5 items tested" inconclusive threshold. |

No hypothesis is reported as supported or not supported. None of H1–H5 has any evidence pointing either way — the gap is entirely a missing-data gap, not a negative finding about Bob's behaviour or the engine's correctness.

## 3. Acceptance criteria (SOW §11)

| # | Criterion | Status | Note |
|---|---|---|---|
| A1 | Unit tests pass; stdlib only | **Met** | 181 passed, 0 failed; `check_stdlib.py` OK. |
| A2 | Validator fields reproduce (`--check`) | **Not applicable** | No compile run exists to have produced `validation.json` in the first place. |
| A2′ | Live fields match evidence | **Not applicable** | No live run exists. |
| A3 | Every rule traceable (`--trace`) | **Not applicable** | No `rules.json` for any run exists to trace. |
| A4 | Replay reproduces published numbers | **Not applicable** | `results/raw/` holds no runs; there is nothing to replay. |
| A5 | Frozen inputs predate evaluation | **Not met** | The "Frozen hashes" table in `HANDOVER.md` is empty. `adapters.json` is still provisional, not probe-confirmed, and no external timestamped record was made. |
| A6 | Probe ran; every E item has an observation or "untested" | **Not met** | The probe was never run. This document records all nine E items as untested (§2, H5), which satisfies the letter of "has an observation or 'untested'" but the probe itself is outstanding. |
| A7 | At least one prevention, or `RESULTS.md` records why not | **Met, as a negative/inconclusive result** | This document is that record: zero attempts were made because no Bob credits remained to run any session. |
| A8 | `RESULTS.md` gives an outcome for H1–H5 with counts, denominators, links | **Met** | §2, above. |
| A9 | No overclaiming ("enforced" describes nothing; planned work labelled as planned) | **Met** | `grep -rni enforced` across the repository's Markdown matches only the SOW's own wording rule and its `EnforcedHooks` (IBM's product name, out of scope) references — nothing here or elsewhere calls a Stickler rule "enforced". Every unfinished deliverable above is labelled "not started" or "not applicable", not implied complete. |
| A10 | Screenshots and ledger present | **Not met** | `bob_sessions/LEDGER.md` has no entries; no screenshots have been filed. Build-session recordings exist outside the repository but were not captured as the SOW's per-stage screenshots, and no usage recording exists at all. |

## 4. What would close the gap

In SOW order, all of this needs Bob credits and is otherwise unblocked:
1. Run the Task 0 probe (`probe/PROMPT.md`, cheapest stage at 2.5 Bobcoins per §10), then rewrite `stickler/adapters.json` from the real observation and refreeze `adapters.json` / `kind-buckets.json` / `results/route-matrix.json` with an external timestamp.
2. Build the reference inventory and independent cases (Claude + owner, outside this repository, per §6.2 and §7) — needs no Bob credits, only Claude/owner time, and can happen in parallel with (1) once the probe output is frozen.
3. Run the engine freeze (`python3 -m stickler.freeze --label engine-1`, tag `engine-1`) — needs no Bob credits, can happen now.
4. Run the stage 5c compile sessions (authored rules, then public sample) in the Stickler mode.
5. Reveal and score (§6.3, §7) against the reference inventory and cases from step 2.
6. Run the stage 7 live sessions (plain natural, governed natural, governed attempts) and record effects per §8.3.
7. Re-run `stickler.score run` and `stickler.replay` and republish this file with real numbers.

## 5. Redaction manifest

Not applicable: no event logs, effect records, or other redacted evidence exist yet (no session has produced any).

# Stickler

Stickler is an IBM Bob custom mode plus a small, fixed, standard-library engine. Bob
reads a project's prose rules for coding agents, splits them into atomic rules, and
classifies each one as **block** (refused before the tool runs, on supported tool
routes), **audit** (detected afterwards from final file state), or **judgment**
(needs a person, or needs a check the engine does not have). Bob writes declarative
JSON specs and test cases; the engine evaluates them. Stickler then measures how
well all of this worked, and publishes the result whether it is good or bad.

**Status:** under construction. This README describes only completed work; each
section below is filled in when its stage finishes. The plan is in `docs/SOW.md`
and the build instructions are in `docs/IMPLEMENTATION_GUIDE.md`.

## Results

Not yet available. See `results/RESULTS.md` when it exists.

## Replay (offline, no Bob needed)

Not yet available.

## Replication (needs Bob and Bobcoins)

Not yet available.

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

## WSL development environment

The Windows environment remains in `.venv`; the Linux environment created with
`uv venv --python 3.12 .venv/wsl` is separate. From the repository root:

```sh
source .venv/wsl/bin/activate
python --version
timeout 300 python -m unittest discover -s tests -t .
python scripts/check_stdlib.py
(cd sample-project && python -m unittest discover -s tests -t .)
```

The current WSL environment uses Python 3.12.14. A local `uv` executable is at
`.venv/tools/uv`. No third-party Python dependencies are required. Environment
files are local and are not part of the repository deliverable.
The managed interpreter lives on WSL's Linux filesystem at
`~/.local/share/stickler-python`; placing it on `/mnt/c` caused the 100 ms regex
screening test to time out. To recreate the WSL environment using that interpreter:

```sh
UV_PYTHON_INSTALL_DIR="$HOME/.local/share/stickler-python" \
  .venv/tools/uv venv --python 3.12 .venv/wsl
```

Bob developed the committed implementation and the existing unfinished stage
5b-3 files on Windows. The owner confirmed that attribution before Codex began
the WSL continuation. The bootstrap scaffold came from Claude's implementation
guide; running it is distinct from authoring it. Subsequent contributions and
verification are recorded in `HANDOVER.md`.

## Replay (offline, no Bob needed)

Not yet available.

## Replication (needs Bob and Bobcoins)

Not yet available.

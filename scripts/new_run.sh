#!/bin/sh
# Create a fresh, isolated run folder for one Bob session (one session per folder).
# plain = observe mode (logs and baseline, prints nothing, never blocks); governed = the
# policy activated from a compile run.
# Usage: scripts/new_run.sh <run-id> <probe|compile|compile-public|plain|governed> [compile-run-id]
# Runs live in $STICKLER_RUNS (default: a stickler-runs folder next to this repository).
set -eu
REPO=$(cd "$(dirname "$0")/.." && pwd)
RUNS=${STICKLER_RUNS:-$(dirname "$REPO")/stickler-runs}
mkdir -p "$RUNS"; RUNS=$(cd "$RUNS" && pwd)
[ $# -ge 2 ] || { echo "usage: $0 <run-id> <kind> [compile-run-id]" >&2; exit 64; }
id=$1; kind=$2; from=${3:-}
case $id in *[!A-Za-z0-9._-]*|"") echo "bad run id: $id" >&2; exit 64 ;; esac
dest=$RUNS/$id
[ ! -e "$dest" ] || { echo "already exists: $dest" >&2; exit 1; }
mkdir -p "$RUNS" "$dest"
trap 'echo "new_run failed; removing $dest" >&2; rm -rf "$dest" "$RUNS/$id.remote.git"' EXIT
GIT="git -C $dest -c user.name=stickler-run -c user.email=run@stickler.invalid"

case $kind in
  probe)
    cp -R "$REPO/probe/fixture" "$dest/fixture"
    mkdir -p "$dest/probe" "$dest/.bob"
    cp "$REPO/probe/probe_hook.py" "$dest/probe/"
    sed "s#__RUN_ROOT__#$dest#g" "$REPO/probe/settings.template.json" > "$dest/.bob/settings.json"
    ;;
  compile|plain|governed)
    cp -R "$REPO/sample-project/." "$dest/"
    mv "$dest/env.synthetic" "$dest/.env"
    find "$dest" -name __pycache__ -type d -prune -exec rm -r {} +
    ;;
  compile-public)
    [ -d "$REPO/corpus/public" ] || { echo "missing corpus/public" >&2; exit 1; }
    mkdir -p "$dest/rules-src"
    cp -R "$REPO/corpus/public/." "$dest/rules-src/"
    ;;
  *) echo "unknown kind: $kind" >&2; exit 64 ;;
esac

git init -q -b main "$dest"
printf '.stickler/\n.probe/\n' >> "$dest/.git/info/exclude"

case $kind in
  compile|compile-public)
    PYTHONPATH=$REPO python3 -m stickler.install --target "$dest" --mode compile ;;
  plain)
    PYTHONPATH=$REPO python3 -m stickler.install --target "$dest" --mode observe ;;
  governed)
    [ -n "$from" ] || { echo "governed needs a compile-run-id" >&2; exit 64; }
    PYTHONPATH=$REPO python3 -m stickler.install --target "$dest" --mode governed \
      --spec-dir "$RUNS/$from/stickler" ;;
esac

$GIT add -A
$GIT commit -q -m "run $id: baseline ($kind)"
git init -q --bare "$RUNS/$id.remote.git"
$GIT remote add origin "$RUNS/$id.remote.git"
$GIT push -q origin main
start=$(git -C "$dest" rev-parse HEAD)
cat > "$RUNS/$id.run.json" <<JSON
{"run_id": "$id", "kind": "$kind", "from_compile_run": "$from", "path": "$dest",
 "remote": "$RUNS/$id.remote.git", "start_commit": "$start",
 "created_utc": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
 "stickler_repo_commit": "$(git -C "$REPO" rev-parse --verify -q HEAD || echo none)"}
JSON
trap - EXIT
echo "run folder: $dest"
echo "open this folder in Bob IDE, start ONE new task, and follow the stage prompt."

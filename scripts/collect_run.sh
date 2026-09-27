#!/bin/sh
# Copy one run's evidence into results/raw/<run-id>/ and write SHA256SUMS.
# Usage: scripts/collect_run.sh <run-id>
set -eu
REPO=$(cd "$(dirname "$0")/.." && pwd)
RUNS=${STICKLER_RUNS:-$(dirname "$REPO")/stickler-runs}
RUNS=$(cd "$RUNS" && pwd)
id=$1; src=$RUNS/$id; out=$REPO/results/raw/$id
[ -d "$src" ] || { echo "no run folder: $src" >&2; exit 1; }
mkdir -p "$out"
cp "$RUNS/$id.run.json" "$out/run.json"
for d in .probe .stickler stickler; do
  if [ -e "$src/$d" ]; then cp -R "$src/$d" "$out/$d"; fi
done
git -C "$src" bundle create "$out/repo.bundle" --all 2>/dev/null
git -C "$src" status --porcelain=v1 --untracked-files=all --ignored > "$out/git-status.txt"
git -C "$src" log --format='%H %s' > "$out/git-log.txt"
git --git-dir "$RUNS/$id.remote.git" show-ref > "$out/remote-refs.txt" 2>/dev/null || true
(cd "$out" && find . -type f ! -name SHA256SUMS | LC_ALL=C sort | xargs sha256sum > SHA256SUMS)
echo "collected into $out"
echo "Now copy $out somewhere outside this workspace and note: sha256 of $out/SHA256SUMS = $(sha256sum "$out/SHA256SUMS" | cut -d' ' -f1)"

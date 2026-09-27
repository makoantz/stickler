"""Session state management (guide §5.8)."""

import json
import os

from stickler.util import (
    append_jsonl,
    excl_create,
    lock,
    now_utc,
    read_json,
    write_json_atomic,
)
from stickler.paths import safe_session_id


class Session:
    def __init__(self, root: str, raw_session_id: str):
        self.sid = safe_session_id(raw_session_id)
        self._root = root
        stickler_dir = os.path.join(root, ".stickler")
        self.dir = os.path.join(stickler_dir, "state", self.sid)
        self.reports_dir = os.path.join(stickler_dir, "reports", self.sid)
        self.outbox = os.path.join(stickler_dir, "outbox")
        os.makedirs(self.dir, exist_ok=True)
        os.makedirs(self.reports_dir, exist_ok=True)
        os.makedirs(self.outbox, exist_ok=True)

    def _pin_path(self):
        return os.path.join(self.dir, "pinned.json")

    def ensure_pinned(self, pointer: dict) -> dict:
        """Create pinned.json with O_EXCL; return existing pin if already created."""
        import json
        data = json.dumps(pointer, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False).encode() + b"\n"
        if excl_create(self._pin_path(), data):
            return pointer
        return read_json(self._pin_path())

    def ensure_baseline(self, config: dict) -> bool:
        """Create baseline.json under a lock if missing. Returns True if created."""
        from stickler.inventory import take_inventory
        lock_path = os.path.join(self.dir, "baseline.lock")
        baseline_path = os.path.join(self.dir, "baseline.json")
        blob_dir = os.path.join(self.dir, "blobs")
        os.makedirs(blob_dir, exist_ok=True)

        with lock(lock_path):
            if os.path.exists(baseline_path):
                return False
            # Check for shared worktree (other session dirs)
            state_dir = os.path.dirname(self.dir)
            shared = any(
                e != self.sid and os.path.isdir(os.path.join(state_dir, e))
                for e in os.listdir(state_dir)
            )
            inv = take_inventory(self._root, config, blob_dir=blob_dir)
            inv["shared_worktree"] = shared
            write_json_atomic(baseline_path, inv)
            return True

    def next_stop_number(self) -> int:
        """Claim the next stop number using O_EXCL."""
        n = 1
        while True:
            claim = os.path.join(self.dir, f"stop-{n}.claim")
            if excl_create(claim):
                return n
            n += 1

    def _blocks_path(self):
        return os.path.join(self.dir, "blocks_pending.jsonl")

    def queue_block(self, record: dict):
        append_jsonl(self._blocks_path(), record)

    def pending_blocks(self) -> list:
        path = self._blocks_path()
        if not os.path.exists(path):
            return []
        result = []
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        result.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        return result

    def mark_blocks_delivered(self):
        path = self._blocks_path()
        if not os.path.exists(path):
            return
        ts = now_utc().replace(":", "-").replace(".", "-")
        delivered = os.path.join(self.dir, f"blocks_delivered-{ts}.jsonl")
        try:
            os.rename(path, delivered)
        except OSError:
            pass

    def outbox_add(self, n: int, report_rel: str, policy_sha: str):
        marker = os.path.join(self.outbox, f"{self.sid}--stop-{n}.json")
        data = {"report": report_rel, "policy_sha256": policy_sha}
        excl_create(marker, json.dumps(data, separators=(",", ":")).encode() + b"\n")

    def undelivered(self) -> list:
        """Return all undelivered outbox markers across the repository."""
        result = []
        if not os.path.isdir(self.outbox):
            return result
        for name in sorted(os.listdir(self.outbox)):
            if name.endswith(".json"):
                path = os.path.join(self.outbox, name)
                try:
                    result.append((name, read_json(path)))
                except Exception:
                    pass
        return result

    def mark_delivered(self, markers: list):
        """Move marker files to outbox/delivered/."""
        delivered_dir = os.path.join(self.outbox, "delivered")
        os.makedirs(delivered_dir, exist_ok=True)
        for name in markers:
            src = os.path.join(self.outbox, name)
            dst = os.path.join(delivered_dir, name)
            try:
                os.rename(src, dst)
            except OSError:
                pass

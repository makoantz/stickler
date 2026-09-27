"""Tests for stickler.score (guide §6, score bullets)."""

import json
import os
import tempfile
import unittest

from stickler.score import _propose, _score_set


def _write(d, path, obj):
    full = os.path.join(d, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w") as f:
        json.dump(obj, f)
    return full


def _mini_corpus():
    """Build a mini corpus: 6 reference rules, 7 Bob rules covering all credit categories."""
    ref_rules = [
        # A01: credited pair
        {"ref_id": "A01", "source": {"path": "rules.md", "start_line": 1, "end_line": 1, "quote": "r1"},
         "text": "R1", "duplicate_group": None, "conflict_with": [], "ambiguous": False,
         "label": {"bucket": "block", "judgment_reason": None, "kind": "deny_path", "status": "resolved"}},
        # A02: split (two bob rules match)
        {"ref_id": "A02", "source": {"path": "rules.md", "start_line": 2, "end_line": 2, "quote": "r2"},
         "text": "R2", "duplicate_group": None, "conflict_with": [], "ambiguous": False,
         "label": {"bucket": "audit", "judgment_reason": None, "kind": "require_paired_change", "status": "resolved"}},
        # A03: merge (one bob rule matches two ref rules)
        {"ref_id": "A03", "source": {"path": "rules.md", "start_line": 3, "end_line": 3, "quote": "r3"},
         "text": "R3", "duplicate_group": None, "conflict_with": [], "ambiguous": False,
         "label": {"bucket": "block", "judgment_reason": None, "kind": "deny_path", "status": "resolved"}},
        # A04: omitted (no matching bob rule)
        {"ref_id": "A04", "source": {"path": "rules.md", "start_line": 4, "end_line": 4, "quote": "r4"},
         "text": "R4", "duplicate_group": None, "conflict_with": [], "ambiguous": False,
         "label": {"bucket": "block", "judgment_reason": None, "kind": "deny_path", "status": "resolved"}},
        # A05: duplicate group
        {"ref_id": "A05", "source": {"path": "rules.md", "start_line": 5, "end_line": 5, "quote": "r5"},
         "text": "R5", "duplicate_group": "G1", "conflict_with": [], "ambiguous": False,
         "label": {"bucket": "block", "judgment_reason": None, "kind": "deny_path", "status": "resolved"}},
        # A06: unresolved
        {"ref_id": "A06", "source": {"path": "rules.md", "start_line": 6, "end_line": 6, "quote": "r6"},
         "text": "R6", "duplicate_group": None, "conflict_with": [], "ambiguous": False,
         "label": {"bucket": "block", "judgment_reason": None, "kind": "deny_path", "status": "unresolved"}},
    ]

    # Bob rules: B01 (matches A01), B02a+B02b (split A02), B03 (merge A02+A03), B04 (extra)
    bob_rules = [
        {"id": "B01", "source": {"path": "rules.md", "start_line": 1, "end_line": 1},
         "bucket": "block"},
        {"id": "B02a", "source": {"path": "rules.md", "start_line": 2, "end_line": 2},
         "bucket": "audit"},
        {"id": "B02b", "source": {"path": "rules.md", "start_line": 2, "end_line": 2},
         "bucket": "audit"},
        {"id": "B03", "source": {"path": "rules.md", "start_line": 3, "end_line": 3},
         "bucket": "block"},
        {"id": "B05", "source": {"path": "rules.md", "start_line": 5, "end_line": 5},
         "bucket": "block"},
        {"id": "B_extra", "source": {"path": "rules.md", "start_line": 9, "end_line": 9},
         "bucket": "block"},
        {"id": "B_extra2", "source": {"path": "rules.md", "start_line": 10, "end_line": 10},
         "bucket": "block"},
    ]

    pairs = [
        {"ref_id": "A01", "bob_id": "B01", "verdict": "match", "note": ""},
        {"ref_id": "A02", "bob_id": "B02a", "verdict": "match", "note": ""},
        {"ref_id": "A02", "bob_id": "B02b", "verdict": "match", "note": "split"},
        {"ref_id": "A03", "bob_id": "B03", "verdict": "match", "note": "merge with A02"},
        {"ref_id": "A05", "bob_id": "B05", "verdict": "match", "note": ""},
    ]

    return ref_rules, bob_rules, pairs


class TestPropose(unittest.TestCase):
    def test_propose_creates_pairs(self):
        with tempfile.TemporaryDirectory() as d:
            ref = [{"ref_id": "A01",
                    "source": {"path": "r.md", "start_line": 1, "end_line": 2}}]
            bob = {"rules": [{"id": "B01",
                              "source": {"path": "r.md", "start_line": 1, "end_line": 1}}]}
            ref_path = _write(d, "ref.json", {"rules": ref})
            bob_path = _write(d, "bob.json", bob)
            out_path = os.path.join(d, "matching.json")
            _propose(ref_path, bob_path, out_path)
            with open(out_path) as f:
                m = json.load(f)
            self.assertEqual(len(m["pairs"]), 1)
            self.assertEqual(m["pairs"][0]["verdict"], "pending")

    def test_propose_keeps_existing_verdict(self):
        with tempfile.TemporaryDirectory() as d:
            ref = [{"ref_id": "A01",
                    "source": {"path": "r.md", "start_line": 1, "end_line": 1}}]
            bob = {"rules": [{"id": "B01",
                              "source": {"path": "r.md", "start_line": 1, "end_line": 1}}]}
            existing = {"pairs": [{"ref_id": "A01", "bob_id": "B01", "verdict": "match", "note": ""}]}
            ref_path = _write(d, "ref.json", {"rules": ref})
            bob_path = _write(d, "bob.json", bob)
            out_path = _write(d, "matching.json", existing)
            _propose(ref_path, bob_path, out_path)
            with open(out_path) as f:
                m = json.load(f)
            self.assertEqual(m["pairs"][0]["verdict"], "match")


class TestScoreH1H2(unittest.TestCase):
    def _run(self):
        ref_rules, bob_rules, pairs = _mini_corpus()
        with tempfile.TemporaryDirectory() as d:
            ref_path = _write(d, "ref.json", {"rules": ref_rules})
            bob_path = _write(d, "bob.json", {"rules": bob_rules})
            matching_path = _write(d, "matching.json", {"pairs": pairs})
            labels_m = _write(d, "labels_model.json", {})
            labels_h = _write(d, "labels_human.json", {})
            set_cfg = {
                "name": "test",
                "reference": ref_path,
                "bob": bob_path,
                "matching": matching_path,
                "labels_model": labels_m,
                "labels_human": labels_h,
                "bob_run": "",
                "cases": "",
            }
            return _score_set(set_cfg, "")

    def test_h1_counts(self):
        scores = self._run()
        h1 = scores["h1"]
        # 5 resolved (A06 is unresolved), dedup: no groups except G1 has A05 only
        # A01(block), A02(audit), A03(block), A04(block), A05(block) = 5 resolved
        # Wait: A05 is in group G1, and A05 is the only member → counts once
        self.assertEqual(h1["n_resolved"], 5)
        self.assertEqual(h1["block"], 4)
        self.assertEqual(h1["audit"], 1)

    def test_h2_recall_and_extra(self):
        scores = self._run()
        h2 = scores["h2"]
        # Credited: A01→B01, A02→B02a, A03→B03, A05→B05 = 4
        # Resolved: A01, A02, A03, A04, A05 = 5
        # Recall = 4/5 = 0.8
        self.assertAlmostEqual(h2["recall"], 0.8, places=2)
        # Extra: B_extra, B_extra2 not credited → 2
        self.assertEqual(h2["extra"], 2)


if __name__ == "__main__":
    unittest.main()

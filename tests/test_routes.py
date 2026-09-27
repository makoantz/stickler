"""Tests for stickler.routes (guide §5.2, §3.4)."""

import json
import os
import tempfile
import unittest

from stickler.routes import kind_buckets, load_adapters, route_matrix
from stickler.util import write_json


def _write_adapters(d, tools):
    path = os.path.join(d, "adapters.json")
    write_json(path, {"adapter_version": 1, "confirmed_by_probe": None, "tools": tools})
    return path


class TestLoadAdapters(unittest.TestCase):
    def test_valid(self):
        with tempfile.TemporaryDirectory() as d:
            p = _write_adapters(d, {
                "write_file": {"operation": "write", "paths": ["path"]},
            })
            doc = load_adapters(p)
            self.assertIn("write_file", doc["tools"])

    def test_unknown_operation(self):
        with tempfile.TemporaryDirectory() as d:
            p = _write_adapters(d, {"t": {"operation": "fly", "paths": ["p"]}})
            with self.assertRaises(ValueError) as cm:
                load_adapters(p)
            self.assertIn("unknown operation", str(cm.exception))

    def test_bad_field_path(self):
        with tempfile.TemporaryDirectory() as d:
            p = _write_adapters(d, {"t": {"operation": "write", "paths": ["bad path!"]}})
            with self.assertRaises(ValueError) as cm:
                load_adapters(p)
            self.assertIn("field path", str(cm.exception))

    def test_bad_nested_field_path(self):
        with tempfile.TemporaryDirectory() as d:
            p = _write_adapters(d, {"t": {"operation": "execute", "command": "!bad"}})
            with self.assertRaises(ValueError):
                load_adapters(p)

    def test_valid_nested_and_array_field_paths(self):
        with tempfile.TemporaryDirectory() as d:
            p = _write_adapters(d, {
                "t": {"operation": "write", "paths": ["a.b", "items[].path"]},
            })
            doc = load_adapters(p)
            self.assertEqual(doc["tools"]["t"]["paths"], ["a.b", "items[].path"])


class TestRouteMatrix(unittest.TestCase):
    def _adapters(self, tools):
        return {"adapter_version": 1, "confirmed_by_probe": None, "tools": tools}

    def test_write_with_paths_supported(self):
        a = self._adapters({"wf": {"operation": "write", "paths": ["path"]}})
        m = route_matrix(a)
        self.assertEqual(m["deny_path"]["wf"]["status"], "supported")
        self.assertEqual(m["allow_paths_only"]["wf"]["status"], "supported")
        self.assertNotIn("wf", m["forbid_file_deletion"])
        self.assertNotIn("wf", m["deny_command"])

    def test_write_without_paths_unsupported(self):
        a = self._adapters({"wf": {"operation": "write", "paths": []}})
        m = route_matrix(a)
        self.assertEqual(m["deny_path"]["wf"]["status"], "unsupported")

    def test_delete_with_paths_supported_for_deletion(self):
        a = self._adapters({"del": {"operation": "delete", "paths": ["path"]}})
        m = route_matrix(a)
        self.assertEqual(m["deny_path"]["del"]["status"], "supported")
        self.assertEqual(m["forbid_file_deletion"]["del"]["status"], "supported")

    def test_delete_without_paths_unsupported(self):
        a = self._adapters({"del": {"operation": "delete", "paths": []}})
        m = route_matrix(a)
        self.assertEqual(m["forbid_file_deletion"]["del"]["status"], "unsupported")

    def test_rename_with_from_to_supported(self):
        a = self._adapters({"mv": {"operation": "rename", "from": "src", "to": "dst"}})
        m = route_matrix(a)
        self.assertEqual(m["deny_path"]["mv"]["status"], "supported")
        self.assertEqual(m["forbid_file_deletion"]["mv"]["status"], "supported")

    def test_rename_missing_to_unsupported_for_path(self):
        a = self._adapters({"mv": {"operation": "rename", "from": "src"}})
        m = route_matrix(a)
        self.assertEqual(m["deny_path"]["mv"]["status"], "unsupported")

    def test_rename_missing_from_unsupported_for_deletion(self):
        a = self._adapters({"mv": {"operation": "rename", "to": "dst"}})
        m = route_matrix(a)
        self.assertEqual(m["forbid_file_deletion"]["mv"]["status"], "unsupported")

    def test_execute_with_command_supported(self):
        a = self._adapters({"exec": {"operation": "execute", "command": "cmd"}})
        m = route_matrix(a)
        self.assertEqual(m["deny_command"]["exec"]["status"], "supported")

    def test_execute_without_command_unsupported(self):
        a = self._adapters({"exec": {"operation": "execute"}})
        m = route_matrix(a)
        self.assertEqual(m["deny_command"]["exec"]["status"], "unsupported")

    def test_no_command_field_deny_command_unsupported(self):
        a = self._adapters({"wf": {"operation": "write", "paths": ["path"]}})
        m = route_matrix(a)
        self.assertNotIn("wf", m["deny_command"])

    def test_read_ignored(self):
        a = self._adapters({"rf": {"operation": "read", "paths": ["path"]}})
        m = route_matrix(a)
        self.assertNotIn("rf", m["deny_path"])
        self.assertNotIn("rf", m["deny_command"])

    def test_no_path_fields_gives_audit_buckets(self):
        a = self._adapters({"wf": {"operation": "write", "paths": []}})
        m = route_matrix(a)
        b = kind_buckets(m)
        self.assertEqual(b["deny_path"], "audit")
        self.assertEqual(b["allow_paths_only"], "audit")


class TestKindBuckets(unittest.TestCase):
    def _from_tools(self, tools):
        a = {"adapter_version": 1, "confirmed_by_probe": None, "tools": tools}
        return kind_buckets(route_matrix(a))

    def test_write_gives_block(self):
        b = self._from_tools({"wf": {"operation": "write", "paths": ["path"]}})
        self.assertEqual(b["deny_path"], "block")
        self.assertEqual(b["allow_paths_only"], "block")

    def test_delete_gives_block_for_deletion(self):
        b = self._from_tools({"del": {"operation": "delete", "paths": ["path"]}})
        self.assertEqual(b["forbid_file_deletion"], "block")

    def test_no_delete_gives_audit_for_deletion(self):
        b = self._from_tools({"wf": {"operation": "write", "paths": ["path"]}})
        self.assertEqual(b["forbid_file_deletion"], "audit")

    def test_execute_with_command_gives_block(self):
        b = self._from_tools({"exec": {"operation": "execute", "command": "cmd"}})
        self.assertEqual(b["deny_command"], "block")

    def test_no_command_gives_unsupported(self):
        b = self._from_tools({"wf": {"operation": "write", "paths": ["path"]}})
        self.assertEqual(b["deny_command"], "unsupported")

    def test_require_paired_change_always_audit(self):
        b = self._from_tools({})
        self.assertEqual(b["require_paired_change"], "audit")

    def test_deny_diff_pattern_always_audit(self):
        b = self._from_tools({})
        self.assertEqual(b["deny_diff_pattern"], "audit")

    def test_empty_adapters_all_audit_or_unsupported(self):
        b = self._from_tools({})
        self.assertEqual(b["deny_path"], "audit")
        self.assertEqual(b["allow_paths_only"], "audit")
        self.assertEqual(b["forbid_file_deletion"], "audit")
        self.assertEqual(b["deny_command"], "unsupported")


if __name__ == "__main__":
    unittest.main()

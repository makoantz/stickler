"""Tests for stickler.adapters (guide §6, adapters bullets)."""

import unittest

from stickler.adapters import extract_ops, resolve_field

_ADAPTERS = {
    "adapter_version": 1,
    "confirmed_by_probe": None,
    "tools": {
        "write_file": {"operation": "write", "paths": ["path"]},
        "read_file": {"operation": "read", "paths": ["path"]},
        "execute_command": {"operation": "execute", "command": "command", "cwd": "cwd"},
        "rename_tool": {"operation": "rename", "from": "src", "to": "dst"},
        "delete_tool": {"operation": "delete", "paths": ["path"]},
        "nested_tool": {"operation": "write", "paths": ["a.b"]},
        "array_tool": {"operation": "write", "paths": ["items[].path"]},
    },
}


class TestResolveField(unittest.TestCase):
    def test_simple(self):
        self.assertEqual(resolve_field({"path": "x.py"}, "path"), ["x.py"])

    def test_nested(self):
        self.assertEqual(resolve_field({"a": {"b": "val"}}, "a.b"), ["val"])

    def test_array(self):
        obj = {"items": [{"path": "a.py"}, {"path": "b.py"}]}
        self.assertEqual(resolve_field(obj, "items[].path"), ["a.py", "b.py"])

    def test_missing_field_returns_none(self):
        self.assertIsNone(resolve_field({}, "missing"))

    def test_non_string_value_returns_none(self):
        self.assertIsNone(resolve_field({"path": 123}, "path"))

    def test_empty_list_returns_none(self):
        self.assertIsNone(resolve_field({"items": []}, "items[].path"))


class TestExtractOps(unittest.TestCase):
    def test_write_file_ok(self):
        ops, cov, err = extract_ops("write_file", {"path": "src/a.py"}, _ADAPTERS)
        self.assertEqual(cov, "ok")
        self.assertIsNone(err)
        self.assertEqual(ops[0]["paths"], ["src/a.py"])

    def test_unknown_tool(self):
        ops, cov, err = extract_ops("unknown_tool", {}, _ADAPTERS)
        self.assertEqual(cov, "unknown_tool")
        self.assertIsNone(err)
        self.assertEqual(ops[0]["operation"], "other")

    def test_unsupported_route_missing_path(self):
        ops, cov, err = extract_ops("write_file", {}, _ADAPTERS)
        self.assertEqual(cov, "malformed")

    def test_read_tool_ok(self):
        ops, cov, err = extract_ops("read_file", {"path": "README.md"}, _ADAPTERS)
        self.assertEqual(cov, "ok")
        self.assertEqual(ops[0]["operation"], "read")

    def test_unsupported_route_no_paths_field(self):
        adapters = {
            "adapter_version": 1, "confirmed_by_probe": None,
            "tools": {"t": {"operation": "write", "paths": []}},
        }
        ops, cov, err = extract_ops("t", {"x": "y"}, adapters)
        self.assertEqual(cov, "unsupported_route")

    def test_malformed_non_string(self):
        ops, cov, err = extract_ops("write_file", {"path": 42}, _ADAPTERS)
        self.assertEqual(cov, "malformed")
        self.assertIsNotNone(err)

    def test_rename_ok(self):
        ops, cov, err = extract_ops("rename_tool", {"src": "old.py", "dst": "new.py"}, _ADAPTERS)
        self.assertEqual(cov, "ok")
        self.assertEqual(ops[0]["from"], "old.py")
        self.assertEqual(ops[0]["to"], "new.py")

    def test_nested_field_path(self):
        ops, cov, err = extract_ops("nested_tool", {"a": {"b": "lib/x.py"}}, _ADAPTERS)
        self.assertEqual(cov, "ok")
        self.assertEqual(ops[0]["paths"], ["lib/x.py"])

    def test_array_field_path(self):
        obj = {"items": [{"path": "a.py"}, {"path": "b.py"}]}
        ops, cov, err = extract_ops("array_tool", obj, _ADAPTERS)
        self.assertEqual(cov, "ok")
        self.assertEqual(ops[0]["paths"], ["a.py", "b.py"])

    def test_execute_with_cwd(self):
        ops, cov, err = extract_ops(
            "execute_command",
            {"command": "echo hi", "cwd": "/tmp"},
            _ADAPTERS,
        )
        self.assertEqual(cov, "ok")
        self.assertEqual(ops[0]["command"], "echo hi")
        self.assertEqual(ops[0]["cwd"], "/tmp")


if __name__ == "__main__":
    unittest.main()

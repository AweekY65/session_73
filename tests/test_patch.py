import unittest

from jsondiffpatch import PatchError, apply, diff, invert, rollback


class TestApplyValidation(unittest.TestCase):
    def test_unknown_op(self):
        with self.assertRaisesRegex(PatchError, "illegal op"):
            apply({"a": 1}, [{"op": "move", "path": "/a", "value": 2}])

    def test_missing_path_key(self):
        with self.assertRaisesRegex(PatchError, "path does not exist"):
            apply({"a": 1}, [{"op": "remove", "path": "/nope"}])

    def test_missing_nested_path(self):
        with self.assertRaisesRegex(PatchError, "path does not exist"):
            apply({"a": {"b": 1}},
                  [{"op": "replace", "path": "/a/x/y", "value": 1}])

    def test_numeric_token_on_object_is_missing_key(self):
        # Object keys are strings, so "/a/0" is a missing key, not an index.
        with self.assertRaises(PatchError):
            apply({"a": {"b": 1}},
                  [{"op": "replace", "path": "/a/0", "value": 1}])

    def test_type_mismatch_key_into_array(self):
        with self.assertRaisesRegex(PatchError, "type mismatch"):
            apply({"a": [1, 2]},
                  [{"op": "replace", "path": "/a/b", "value": 1}])

    def test_type_mismatch_descend_into_scalar(self):
        with self.assertRaisesRegex(PatchError, "type mismatch"):
            apply({"a": 5}, [{"op": "replace", "path": "/a/b", "value": 1}])

    def test_index_out_of_range(self):
        with self.assertRaisesRegex(PatchError, "out of range"):
            apply([1, 2], [{"op": "replace", "path": "/5", "value": 9}])

    def test_add_index_out_of_range(self):
        with self.assertRaisesRegex(PatchError, "out of range"):
            apply([1, 2], [{"op": "add", "path": "/5", "value": 9}])

    def test_negative_index_rejected(self):
        with self.assertRaisesRegex(PatchError, "invalid array index"):
            apply([1, 2], [{"op": "replace", "path": "/-1", "value": 9}])

    def test_dash_append_only_for_add(self):
        doc = apply([1, 2], [{"op": "add", "path": "/-", "value": 3}])
        self.assertEqual(doc, [1, 2, 3])
        with self.assertRaises(PatchError):
            apply([1, 2], [{"op": "replace", "path": "/-", "value": 3}])

    def test_malformed_path(self):
        with self.assertRaisesRegex(PatchError, "start with '/'"):
            apply({"a": 1}, [{"op": "remove", "path": "a"}])

    def test_bad_escape(self):
        with self.assertRaises(PatchError):
            apply({"a": 1}, [{"op": "remove", "path": "/a~2b"}])

    def test_missing_value_field(self):
        with self.assertRaisesRegex(PatchError, "requires 'value'"):
            apply({"a": 1}, [{"op": "replace", "path": "/a"}])

    def test_missing_path_field(self):
        with self.assertRaisesRegex(PatchError, "missing 'path'"):
            apply({"a": 1}, [{"op": "remove"}])

    def test_patch_not_a_list(self):
        with self.assertRaisesRegex(PatchError, "list"):
            apply({"a": 1}, {"op": "remove", "path": "/a"})

    def test_old_mismatch_detected(self):
        with self.assertRaisesRegex(PatchError, "'old' mismatch"):
            apply({"a": 2}, [{"op": "replace", "path": "/a",
                              "value": 3, "old": 1}])

    def test_remove_root_rejected(self):
        with self.assertRaisesRegex(PatchError, "root"):
            apply({"a": 1}, [{"op": "remove", "path": ""}])

    def test_apply_does_not_mutate_input(self):
        a = {"x": [1, 2]}
        apply(a, [{"op": "add", "path": "/x/-", "value": 3}])
        self.assertEqual(a, {"x": [1, 2]})


class TestInvertRollback(unittest.TestCase):
    def test_invert_roundtrip(self):
        a = {"name": "app", "tags": ["a", "b", "c"],
             "cfg": {"debug": False, "limits": {"cpu": 4}}}
        b = {"name": "app2", "tags": ["b", "c", "d"],
             "cfg": {"debug": True, "limits": {"cpu": 8, "mem": 16}},
             "extra": None}
        patch = diff(a, b)
        self.assertEqual(apply(b, invert(patch)), a)
        self.assertEqual(rollback(apply(a, patch), patch), a)

    def test_invert_remove_requires_old(self):
        with self.assertRaisesRegex(PatchError, "cannot invert"):
            invert([{"op": "remove", "path": "/a"}])

    def test_rollback_array_insert(self):
        a = [1, 2, 3]
        patch = diff(a, [0, 1, 2, 3, 4])
        self.assertEqual(rollback(apply(a, patch), patch), a)


if __name__ == "__main__":
    unittest.main()

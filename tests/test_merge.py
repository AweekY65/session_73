import unittest

from jsondiffpatch import merge


class TestMergeClean(unittest.TestCase):
    def test_both_unchanged(self):
        result = merge({"a": 1}, {"a": 1}, {"a": 1})
        self.assertTrue(result.clean)
        self.assertEqual(result.merged, {"a": 1})

    def test_only_one_side_changed(self):
        base = {"a": 1, "b": 2}
        self.assertEqual(merge(base, {"a": 9, "b": 2}, base).merged,
                         {"a": 9, "b": 2})
        self.assertEqual(merge(base, base, {"a": 1, "b": 9}).merged,
                         {"a": 1, "b": 9})

    def test_disjoint_paths_auto_merge(self):
        base = {"ui": {"theme": "dark", "lang": "en"}, "net": {"retry": 3}}
        left = {"ui": {"theme": "light", "lang": "en"}, "net": {"retry": 3}}
        right = {"ui": {"theme": "dark", "lang": "en"}, "net": {"retry": 5}}
        result = merge(base, left, right)
        self.assertTrue(result.clean)
        self.assertEqual(result.merged,
                         {"ui": {"theme": "light", "lang": "en"},
                          "net": {"retry": 5}})

    def test_add_on_different_keys(self):
        base = {"a": 1}
        result = merge(base, {"a": 1, "x": 1}, {"a": 1, "y": 2})
        self.assertTrue(result.clean)
        self.assertEqual(result.merged, {"a": 1, "x": 1, "y": 2})

    def test_same_addition_on_both_sides(self):
        base = {"a": 1}
        result = merge(base, {"a": 1, "x": 5}, {"a": 1, "x": 5})
        self.assertTrue(result.clean)
        self.assertEqual(result.merged, {"a": 1, "x": 5})

    def test_delete_vs_untouched(self):
        base = {"a": 1, "b": 2}
        result = merge(base, {"a": 1}, {"a": 1, "b": 2})
        self.assertTrue(result.clean)
        self.assertEqual(result.merged, {"a": 1})

    def test_delete_on_both_sides(self):
        base = {"a": 1, "b": 2}
        result = merge(base, {"a": 1}, {"a": 1})
        self.assertTrue(result.clean)
        self.assertEqual(result.merged, {"a": 1})

    def test_array_disjoint_indexes(self):
        base = [1, 2, 3]
        result = merge(base, [9, 2, 3], [1, 2, 8])
        self.assertTrue(result.clean)
        self.assertEqual(result.merged, [9, 2, 8])

    def test_array_one_side_changed(self):
        base = [1, 2, 3]
        result = merge(base, [1, 9, 2, 3], base)
        self.assertTrue(result.clean)
        self.assertEqual(result.merged, [1, 9, 2, 3])

    def test_key_order_irrelevant(self):
        base = {"x": 1, "y": 2}
        left = {"y": 2, "x": 1, "z": 3}
        right = {"x": 1, "y": 2}
        result = merge(base, left, right)
        self.assertTrue(result.clean)
        self.assertEqual(result.merged, {"x": 1, "y": 2, "z": 3})


class TestMergeConflicts(unittest.TestCase):
    def test_same_path_different_values(self):
        result = merge({"a": 1}, {"a": 2}, {"a": 3})
        self.assertFalse(result.clean)
        self.assertEqual(len(result.conflicts), 1)
        conflict = result.conflicts[0]
        self.assertEqual(conflict.path, "/a")
        self.assertEqual(conflict.base, 1)
        self.assertEqual(conflict.left, 2)
        self.assertEqual(conflict.right, 3)

    def test_nested_conflict_path(self):
        base = {"srv": {"port": 80}}
        result = merge(base, {"srv": {"port": 8080}}, {"srv": {"port": 9090}})
        self.assertEqual([c.path for c in result.conflicts], ["/srv/port"])

    def test_modify_vs_delete(self):
        base = {"a": {"v": 1}}
        left = {"a": {"v": 2}}
        right = {}
        result = merge(base, left, right)
        self.assertFalse(result.clean)
        self.assertEqual(result.conflicts[0].path, "/a")
        self.assertIn("deleted", result.conflicts[0].reason)

    def test_add_same_key_different_values(self):
        result = merge({}, {"x": 1}, {"x": 2})
        self.assertFalse(result.clean)
        self.assertEqual(result.conflicts[0].path, "/x")

    def test_array_same_index_conflict(self):
        result = merge([1, 2], [1, 9], [1, 8])
        self.assertFalse(result.clean)
        self.assertEqual(result.conflicts[0].path, "/1")

    def test_array_both_lengths_changed(self):
        result = merge([1, 2, 3], [1, 2], [1, 2, 3, 4])
        self.assertFalse(result.clean)
        self.assertEqual(result.conflicts[0].path, "/")

    def test_type_change_conflict(self):
        result = merge({"a": [1]}, {"a": {"x": 1}}, {"a": "str"})
        self.assertFalse(result.clean)

    def test_conflict_keeps_left_deterministically(self):
        result = merge({"a": 1}, {"a": 2}, {"a": 3})
        self.assertEqual(result.merged, {"a": 2})

    def test_mixed_clean_and_conflicted(self):
        base = {"keep": 0, "fight": 1}
        left = {"keep": 10, "fight": 2}
        right = {"keep": 10, "fight": 3}
        result = merge(base, left, right)
        self.assertFalse(result.clean)
        self.assertEqual(result.merged["keep"], 10)
        self.assertEqual(len(result.conflicts), 1)


if __name__ == "__main__":
    unittest.main()

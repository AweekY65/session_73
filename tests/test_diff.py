import unittest

from jsondiffpatch import apply, diff


class TestDiffApply(unittest.TestCase):
    def roundtrip(self, a, b):
        patch = diff(a, b)
        self.assertEqual(apply(a, patch), b,
                         "round-trip failed; patch=%r" % (patch,))
        return patch

    def test_no_change(self):
        self.assertEqual(diff({"a": 1}, {"a": 1}), [])

    def test_object_add_remove_replace(self):
        a = {"keep": 1, "drop": 2, "change": "old"}
        b = {"keep": 1, "new": 3, "change": "new"}
        patch = self.roundtrip(a, b)
        ops = {(op["op"], op["path"]) for op in patch}
        self.assertIn(("remove", "/drop"), ops)
        self.assertIn(("add", "/new"), ops)
        self.assertIn(("replace", "/change"), ops)

    def test_nested_objects(self):
        a = {"user": {"name": "ann", "addr": {"city": "BJ", "zip": "100"}}}
        b = {"user": {"name": "ann", "addr": {"city": "SH", "zip": "100"}}}
        patch = self.roundtrip(a, b)
        self.assertEqual(len(patch), 1)
        self.assertEqual(patch[0]["path"], "/user/addr/city")

    def test_key_order_is_ignored(self):
        a = {"x": 1, "y": 2, "z": {"p": 1, "q": 2}}
        b = {"z": {"q": 2, "p": 1}, "y": 2, "x": 1}
        self.assertEqual(diff(a, b), [])

    def test_type_change(self):
        self.roundtrip({"a": [1, 2]}, {"a": {"0": 1}})
        self.roundtrip({"a": 1}, {"a": None})
        self.roundtrip([1, 2], {"x": 1})
        self.roundtrip({"x": 1}, [1, 2])

    def test_root_replace(self):
        patch = self.roundtrip({"a": 1}, [1, 2, 3])
        self.assertEqual(patch[0]["path"], "")

    def test_array_insert(self):
        patch = self.roundtrip([1, 2, 3], [1, 9, 2, 3])
        self.assertEqual(patch, [{"op": "add", "path": "/1", "value": 9}])

    def test_array_delete(self):
        patch = self.roundtrip([1, 9, 2, 3], [1, 2, 3])
        self.assertEqual(patch, [{"op": "remove", "path": "/1", "old": 9}])

    def test_array_modify_element(self):
        patch = self.roundtrip([1, 2, 3], [1, 5, 3])
        self.assertEqual(patch, [{"op": "replace", "path": "/1",
                                  "value": 5, "old": 2}])

    def test_array_nested_object_edit(self):
        a = [{"id": 1, "v": "a"}, {"id": 2, "v": "b"}]
        b = [{"id": 1, "v": "a"}, {"id": 2, "v": "B"}]
        patch = self.roundtrip(a, b)
        self.assertEqual(patch, [{"op": "replace", "path": "/1/v",
                                  "value": "B", "old": "b"}])

    def test_array_reorder_produces_diff(self):
        # Array order is significant: reordering must produce ops.
        patch = diff([1, 2, 3], [3, 2, 1])
        self.assertNotEqual(patch, [])
        self.assertEqual(apply([1, 2, 3], patch), [3, 2, 1])

    def test_array_grow_and_shrink(self):
        self.roundtrip([1, 2], [1, 2, 3, 4])
        self.roundtrip([1, 2, 3, 4], [2, 3])
        self.roundtrip([], [1, {"a": [True, None]}])
        self.roundtrip([1, {"a": [True, None]}], [])

    def test_deeply_nested_mixed(self):
        a = {"a": [{"b": [1, 2, {"c": 3}]}, "x"], "d": {"e": []}}
        b = {"a": [{"b": [1, 2, {"c": 4, "n": 5}]}, "x", "y"], "d": {"e": [0]}}
        self.roundtrip(a, b)

    def test_special_characters_in_keys(self):
        a = {"a/b": 1, "t~x": {"": 1}}
        b = {"a/b": 2, "t~x": {"": 2, "new/key": True}}
        self.roundtrip(a, b)

    def test_random_roundtrips(self):
        import random
        rng = random.Random(20261003)

        def rand_value(depth):
            if depth <= 0:
                return rng.choice([1, "s", True, None, 2.5])
            kind = rng.randrange(4)
            if kind == 0:
                return {rng.choice("abcd") + str(i): rand_value(depth - 1)
                        for i in range(rng.randrange(4))}
            if kind == 1:
                return [rand_value(depth - 1)
                        for _ in range(rng.randrange(5))]
            return rng.choice([1, "s", False, None, 3.14])

        for _ in range(200):
            a, b = rand_value(3), rand_value(3)
            self.assertEqual(apply(a, diff(a, b)), b)


if __name__ == "__main__":
    unittest.main()

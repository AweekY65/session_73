"""Structural diff: diff(a, b) -> patch ops such that apply(a, patch) == b.

Patch ops are JSON-Patch-like dicts:

    {"op": "add",     "path": "/a/0", "value": <new>}
    {"op": "remove",  "path": "/a/0", "old": <removed>}
    {"op": "replace", "path": "/a/0", "value": <new>, "old": <previous>}

``old`` fields carry rollback information so every patch produced here can
be inverted with :func:`jsondiffpatch.invert`.

Diff strategy
-------------
* Objects are compared by key, so key *order* never produces a diff.
* Scalars of different type or value produce a single ``replace``.
* Arrays are aligned with an LCS (via difflib.SequenceMatcher) over a
  canonical serialization of each element. Matching elements are compared
  pairwise (recursing into objects/arrays); non-matching regions become
  ``add``/``remove`` runs. Array order is significant: reordering elements
  produces remove+add ops.
"""

import difflib
import json

from .paths import format_pointer


def diff(a, b):
    """Return a list of patch ops transforming document ``a`` into ``b``."""
    ops = []
    _diff(a, b, [], ops)
    return ops


def _diff(a, b, path, ops):
    if a == b:
        return
    if isinstance(a, dict) and isinstance(b, dict):
        _diff_object(a, b, path, ops)
        return
    if isinstance(a, list) and isinstance(b, list):
        ops.extend(_diff_array(a, b, path))
        return
    ops.append({"op": "replace", "path": format_pointer(path),
                "value": b, "old": a})


def _diff_object(a, b, path, ops):
    for key in a:
        if key not in b:
            ops.append({"op": "remove", "path": format_pointer(path + [key]),
                        "old": a[key]})
    for key in b:
        if key not in a:
            ops.append({"op": "add", "path": format_pointer(path + [key]),
                        "value": b[key]})
        else:
            _diff(a[key], b[key], path + [key], ops)


def _canon(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _diff_array(a, b, path):
    """Diff two arrays, returning ops in application order.

    Opcodes from the LCS matcher are processed right-to-left and appended,
    so ops at higher indexes are applied first and never invalidate the
    indexes of pending (lower-indexed) edits.
    """
    keys_a = [_canon(v) for v in a]
    keys_b = [_canon(v) for v in b]
    matcher = difflib.SequenceMatcher(a=keys_a, b=keys_b, autojunk=False)

    result = []
    for tag, i1, i2, j1, j2 in reversed(matcher.get_opcodes()):
        block = []
        if tag == "equal":
            continue
        if tag == "delete":
            # Removing repeatedly at i1 works because elements shift down.
            for k in range(i1, i2):
                block.append({"op": "remove",
                              "path": format_pointer(path + [i1]),
                              "old": a[k]})
        elif tag == "insert":
            for k in range(j1, j2):
                block.append({"op": "add",
                              "path": format_pointer(path + [i1 + (k - j1)]),
                              "value": b[k]})
        else:  # replace
            common = min(i2 - i1, j2 - j1)
            for k in range(common):
                _diff(a[i1 + k], b[j1 + k], path + [i1 + k], block)
            if i2 - i1 > common:
                for k in range(i1 + common, i2):
                    block.append({"op": "remove",
                                  "path": format_pointer(path + [i1 + common]),
                                  "old": a[k]})
            elif j2 - j1 > common:
                for k in range(j1 + common, j2):
                    block.append({"op": "add",
                                  "path": format_pointer(
                                      path + [i1 + common + (k - j1 - common)]),
                                  "value": b[k]})
        result.extend(block)
    return result

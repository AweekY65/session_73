"""Three-way merge: merge(base, left, right) -> MergeResult.

Rules
-----
* If both sides are equal, take that value.
* If only one side changed relative to base, take the changed side.
* Objects merge key by key (key order is irrelevant):
    - key changed on both sides -> recurse
    - key deleted on one side, untouched on the other -> deleted
    - key deleted on one side, modified on the other -> conflict
    - key added on both sides with different values -> conflict
* Arrays: if all three lengths are equal, elements merge index by index.
  Otherwise (both sides changed the length differently) -> conflict.
* Anything else where both sides changed incompatibly -> conflict.

Conflicts never raise; they are collected into MergeResult.conflicts with
the path, reason and all three values. On conflict the merged document
keeps the left value (documented, deterministic resolution).
"""

import copy
from dataclasses import dataclass, field
from typing import Any, List

from .paths import format_pointer


@dataclass
class Conflict:
    path: str
    reason: str
    base: Any
    left: Any
    right: Any

    def to_dict(self):
        return {"path": self.path, "reason": self.reason,
                "base": self.base, "left": self.left, "right": self.right}


@dataclass
class MergeResult:
    merged: Any
    conflicts: List[Conflict] = field(default_factory=list)

    @property
    def clean(self):
        return not self.conflicts


def merge(base, left, right):
    """Three-way merge of JSON documents. Returns a MergeResult."""
    conflicts = []
    merged = _merge(base, left, right, [], conflicts)
    return MergeResult(merged, conflicts)


def _conflict(path, reason, base, left, right, conflicts):
    conflicts.append(Conflict(format_pointer(path) or "/", reason,
                              copy.deepcopy(base), copy.deepcopy(left),
                              copy.deepcopy(right)))
    return copy.deepcopy(left)  # deterministic resolution: left wins


def _merge(base, left, right, path, conflicts):
    if left == right:
        return copy.deepcopy(left)
    if base == left:
        return copy.deepcopy(right)
    if base == right:
        return copy.deepcopy(left)

    if isinstance(base, dict) and isinstance(left, dict) \
            and isinstance(right, dict):
        return _merge_object(base, left, right, path, conflicts)

    if isinstance(base, list) and isinstance(left, list) \
            and isinstance(right, list):
        if len(base) == len(left) == len(right):
            return [_merge(b, l, r, path + [i], conflicts)
                    for i, (b, l, r) in enumerate(zip(base, left, right))]
        return _conflict(path, "array edited on both sides with different "
                         "lengths", base, left, right, conflicts)

    return _conflict(path, "incompatible changes on both sides",
                     base, left, right, conflicts)


def _merge_object(base, left, right, path, conflicts):
    result = {}
    keys = list(dict.fromkeys(list(base) + list(left) + list(right)))
    for key in keys:
        in_base, in_left, in_right = key in base, key in left, key in right
        child_path = path + [key]

        if in_base:
            if in_left and in_right:
                result[key] = _merge(base[key], left[key], right[key],
                                     child_path, conflicts)
            elif in_left:  # deleted on the right
                if left[key] == base[key]:
                    continue  # only right changed it -> deletion wins
                _conflict(child_path, "modified on left, deleted on right",
                          base[key], left[key], None, conflicts)
                result[key] = copy.deepcopy(left[key])
            elif in_right:  # deleted on the left
                if right[key] == base[key]:
                    continue
                _conflict(child_path, "modified on right, deleted on left",
                          base[key], None, right[key], conflicts)
                result[key] = copy.deepcopy(right[key])
            # else: deleted on both sides -> omitted
        else:
            if in_left and in_right:
                if left[key] == right[key]:
                    result[key] = copy.deepcopy(left[key])
                else:
                    _conflict(child_path, "added on both sides with "
                              "different values", None, left[key],
                              right[key], conflicts)
                    result[key] = copy.deepcopy(left[key])
            elif in_left:
                result[key] = copy.deepcopy(left[key])
            else:
                result[key] = copy.deepcopy(right[key])
    return result

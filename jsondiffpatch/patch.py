"""Patch application, validation, inversion and rollback.

apply() never mutates its input; it returns a patched deep copy.
Every problem (missing path, type mismatch, illegal op, stale ``old``
value) raises PatchError with an explicit message.
"""

import copy

from .errors import PatchError
from .paths import parse_pointer

_OPS = ("add", "remove", "replace")


def apply(doc, patch, *, validate_old=True):
    """Apply ``patch`` (a list of ops) to ``doc``; return a new document.

    Raises PatchError on any invalid op or path. If ``validate_old`` is
    true (default), ``old`` fields on remove/replace ops must match the
    current document, which catches patches applied to the wrong base.
    """
    if not isinstance(patch, list):
        raise PatchError("patch must be a list of operations, got %r"
                         % type(patch).__name__)
    result = copy.deepcopy(doc)
    for index, op in enumerate(patch):
        result = _apply_op(result, op, index, validate_old)
    return result


def invert(patch):
    """Return the inverse patch: apply(apply(a, p), invert(p)) == a.

    Requires remove/replace ops to carry ``old`` values (diff() always
    emits them). Ops are reversed so array index shifts cancel out.
    """
    if not isinstance(patch, list):
        raise PatchError("patch must be a list of operations")
    inverse = []
    for op in reversed(patch):
        kind = op.get("op") if isinstance(op, dict) else None
        if kind == "add":
            inverse.append({"op": "remove", "path": op["path"],
                            "old": copy.deepcopy(op["value"])})
        elif kind == "remove":
            if "old" not in op:
                raise PatchError(
                    "cannot invert remove op without 'old': %r" % (op,))
            inverse.append({"op": "add", "path": op["path"],
                            "value": copy.deepcopy(op["old"])})
        elif kind == "replace":
            if "old" not in op:
                raise PatchError(
                    "cannot invert replace op without 'old': %r" % (op,))
            inverse.append({"op": "replace", "path": op["path"],
                            "value": copy.deepcopy(op["old"]),
                            "old": copy.deepcopy(op["value"])})
        else:
            raise PatchError("cannot invert unknown op: %r" % (op,))
    return inverse


def rollback(doc, patch):
    """Undo a previously applied patch: rollback(apply(a, p), p) == a."""
    return apply(doc, invert(patch))


def _apply_op(doc, op, index, validate_old=True):
    if not isinstance(op, dict):
        raise PatchError("op #%d must be an object, got %r"
                         % (index, type(op).__name__))
    kind = op.get("op")
    if kind not in _OPS:
        raise PatchError("op #%d: illegal op %r (expected one of %s)"
                         % (index, kind, ", ".join(_OPS)))
    if "path" not in op:
        raise PatchError("op #%d: missing 'path'" % index)
    tokens = parse_pointer(op["path"])

    if not tokens:
        # Root-level operation.
        if kind == "remove":
            raise PatchError("op #%d: cannot remove the document root" % index)
        if "value" not in op:
            raise PatchError("op #%d: %s op requires 'value'" % (index, kind))
        if kind == "replace" and validate_old and "old" in op \
                and op["old"] != doc:
            raise PatchError("op #%d: 'old' mismatch at root" % index)
        return copy.deepcopy(op["value"])

    parent = _resolve_parent(doc, tokens, index)
    token = tokens[-1]

    if kind == "add":
        if "value" not in op:
            raise PatchError("op #%d: add op requires 'value'" % index)
        _add_child(parent, token, op["value"], index)
    elif kind == "remove":
        old = _get_child(parent, token, index)
        if validate_old and "old" in op and op["old"] != old:
            raise PatchError(
                "op #%d: 'old' mismatch at %r: expected %r, found %r"
                % (index, op["path"], op["old"], old))
        _del_child(parent, token, index)
    else:  # replace
        if "value" not in op:
            raise PatchError("op #%d: replace op requires 'value'" % index)
        old = _get_child(parent, token, index)
        if validate_old and "old" in op and op["old"] != old:
            raise PatchError(
                "op #%d: 'old' mismatch at %r: expected %r, found %r"
                % (index, op["path"], op["old"], old))
        _set_child(parent, token, op["value"], index)
    return doc


def _resolve_parent(doc, tokens, index):
    node = doc
    for depth, token in enumerate(tokens[:-1]):
        node = _descend(node, token, index, tokens[:depth + 1])
    return node


def _descend(node, token, index, tokens_so_far):
    from .paths import format_pointer
    where = format_pointer(tokens_so_far) or "/"
    if isinstance(node, dict):
        if token not in node:
            raise PatchError("op #%d: path does not exist at %r (key %r)"
                             % (index, where, token))
        return node[token]
    if isinstance(node, list):
        idx = _to_index(token, index, where)
        if idx >= len(node):
            raise PatchError("op #%d: index %d out of range at %r (len %d)"
                             % (index, idx, where, len(node)))
        return node[idx]
    raise PatchError("op #%d: type mismatch at %r: cannot descend into %r"
                     % (index, where, type(node).__name__))


def _to_index(token, index, where):
    if token == "-":
        raise PatchError("op #%d: '-' is only valid as the last token "
                         "of an add path (at %r)" % (index, where))
    try:
        idx = int(token)
    except (TypeError, ValueError):
        raise PatchError(
            "op #%d: type mismatch at %r: %r is not an array index"
            % (index, where, token)) from None
    if idx < 0 or str(idx) != str(token):
        raise PatchError("op #%d: invalid array index %r at %r"
                         % (index, token, where))
    return idx


def _add_child(parent, token, value, index):
    if isinstance(parent, dict):
        parent[token] = copy.deepcopy(value)
        return
    if isinstance(parent, list):
        if token == "-":
            parent.append(copy.deepcopy(value))
            return
        idx = _to_index(token, index, "add target")
        if idx > len(parent):
            raise PatchError("op #%d: add index %d out of range (len %d)"
                             % (index, idx, len(parent)))
        parent.insert(idx, copy.deepcopy(value))
        return
    raise PatchError("op #%d: type mismatch: cannot add into %r"
                     % (index, type(parent).__name__))


def _get_child(parent, token, index):
    if isinstance(parent, dict):
        if token not in parent:
            raise PatchError("op #%d: path does not exist: key %r"
                             % (index, token))
        return parent[token]
    if isinstance(parent, list):
        idx = _to_index(token, index, "target")
        if idx >= len(parent):
            raise PatchError("op #%d: index %d out of range (len %d)"
                             % (index, idx, len(parent)))
        return parent[idx]
    raise PatchError("op #%d: type mismatch: cannot index into %r"
                     % (index, type(parent).__name__))


def _del_child(parent, token, index):
    if isinstance(parent, dict):
        del parent[token]
        return
    if isinstance(parent, list):
        del parent[_to_index(token, index, "target")]
        return
    raise PatchError("op #%d: type mismatch: cannot remove from %r"
                     % (index, type(parent).__name__))


def _set_child(parent, token, value, index):
    if isinstance(parent, dict):
        parent[token] = copy.deepcopy(value)
        return
    if isinstance(parent, list):
        parent[_to_index(token, index, "target")] = copy.deepcopy(value)
        return
    raise PatchError("op #%d: type mismatch: cannot replace into %r"
                     % (index, type(parent).__name__))

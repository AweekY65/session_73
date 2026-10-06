import { clone, deepEqual, isPlainObject, joinPointer } from './jsonpatch.js';

const MISSING = Symbol('missing');

function eq(x, y) {
  if (x === MISSING || y === MISSING) return x === y;
  return deepEqual(x, y);
}

function present(v) {
  return v === MISSING ? undefined : clone(v);
}

/**
 * Three-way merge. Returns { doc, conflicts }.
 *
 * Rules:
 * - Only one side changed a value (or both changed it identically):
 *   the change is taken automatically.
 * - Objects merge key by key; keys deleted on one side and untouched on
 *   the other are deleted; delete-vs-modify is a conflict.
 * - Arrays of equal length (base/left/right all the same length) merge
 *   element by element. If both sides changed an array and the lengths
 *   differ, the whole array is a conflict (array structure conflict).
 * - Anything else changed on both sides differently is a conflict.
 * - On conflict the merged document keeps the base value (or the left
 *   value when the path does not exist in base), and a conflict record
 *   { path, reason, base, left, right } is emitted.
 */
export function merge(base, left, right) {
  const conflicts = [];
  const doc = mergeValue(base, left, right, '', conflicts);
  return { doc: doc === MISSING ? undefined : doc, conflicts };
}

function mergeValue(base, left, right, path, conflicts) {
  if (eq(left, right)) return left === MISSING ? MISSING : clone(left);
  if (eq(base, left)) return right === MISSING ? MISSING : clone(right);
  if (eq(base, right)) return left === MISSING ? MISSING : clone(left);

  const conflict = (reason) => {
    conflicts.push({
      path,
      reason,
      base: present(base),
      left: present(left),
      right: present(right),
    });
    // Deterministic resolution: keep base, fall back to left if no base.
    return base === MISSING ? clone(left) : clone(base);
  };

  if (base === MISSING) {
    // Both sides created the same path with different values.
    return conflict('create-vs-create');
  }
  if (left === MISSING || right === MISSING) {
    // One side deleted, the other modified.
    return conflict('delete-vs-modify');
  }

  if (isPlainObject(base) && isPlainObject(left) && isPlainObject(right)) {
    const keys = new Set([...Object.keys(base), ...Object.keys(left), ...Object.keys(right)]);
    const out = {};
    for (const key of [...keys].sort()) {
      const bv = Object.prototype.hasOwnProperty.call(base, key) ? base[key] : MISSING;
      const lv = Object.prototype.hasOwnProperty.call(left, key) ? left[key] : MISSING;
      const rv = Object.prototype.hasOwnProperty.call(right, key) ? right[key] : MISSING;
      const merged = mergeValue(bv, lv, rv, joinPointer(path, key), conflicts);
      if (merged !== MISSING) out[key] = merged;
    }
    return out;
  }

  if (
    Array.isArray(base) &&
    Array.isArray(left) &&
    Array.isArray(right) &&
    base.length === left.length &&
    left.length === right.length
  ) {
    return left.map((_, i) => mergeValue(base[i], left[i], right[i], joinPointer(path, i), conflicts));
  }

  if (Array.isArray(base) && Array.isArray(left) && Array.isArray(right)) {
    return conflict('array-structure-conflict');
  }
  return conflict('incompatible-modification');
}

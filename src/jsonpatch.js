/**
 * JSON Pointer (RFC 6901) utilities + patch apply / invert.
 * Patch format is JSON-Patch-like:
 *   { op: "add",     path: "/a/0", value: <any> }
 *   { op: "remove",  path: "/a/0", prev: <any> }   // prev recorded for rollback
 *   { op: "replace", path: "/a/0", value: <any>, prev: <any> }
 */

export class PatchError extends Error {
  constructor(code, message) {
    super(message);
    this.name = 'PatchError';
    this.code = code; // PATH_NOT_FOUND | TYPE_MISMATCH | INVALID_OP
  }
}

export function escapeSegment(seg) {
  return String(seg).replace(/~/g, '~0').replace(/\//g, '~1');
}

export function unescapeSegment(seg) {
  return seg.replace(/~1/g, '/').replace(/~0/g, '~');
}

/** "/a/0/b" -> ["a","0","b"]; "" -> [] */
export function parsePointer(path) {
  if (path === '' || path === undefined) return [];
  if (typeof path !== 'string' || !path.startsWith('/')) {
    throw new PatchError('INVALID_OP', `invalid JSON pointer: ${JSON.stringify(path)}`);
  }
  return path.slice(1).split('/').map(unescapeSegment);
}

/** ["a","0"] -> "/a/0"; [] -> "" */
export function toPointer(segments) {
  return segments.map(escapeSegment).map((s) => '/' + s).join('');
}

export function joinPointer(path, seg) {
  return path + '/' + escapeSegment(seg);
}

export function clone(value) {
  return value === undefined ? undefined : structuredClone(value);
}

export function deepEqual(x, y) {
  if (x === y) return true;
  if (typeof x !== typeof y) return false;
  if (x && y && typeof x === 'object') {
    const xa = Array.isArray(x);
    const ya = Array.isArray(y);
    if (xa !== ya) return false;
    if (xa) {
      if (x.length !== y.length) return false;
      for (let i = 0; i < x.length; i++) if (!deepEqual(x[i], y[i])) return false;
      return true;
    }
    const kx = Object.keys(x);
    const ky = Object.keys(y);
    if (kx.length !== ky.length) return false;
    return kx.every(
      (k) => Object.prototype.hasOwnProperty.call(y, k) && deepEqual(x[k], y[k])
    );
  }
  return false;
}

export function isPlainObject(v) {
  return v !== null && typeof v === 'object' && !Array.isArray(v);
}

const ARRAY_INDEX = /^(0|[1-9]\d*)$/;

function parseArrayIndex(seg, path) {
  if (!ARRAY_INDEX.test(seg)) {
    throw new PatchError(
      'TYPE_MISMATCH',
      `expected array index at ${JSON.stringify(path)}, got ${JSON.stringify(seg)}`
    );
  }
  return Number(seg);
}

/** Walk to the parent of the target, validating container types. */
function resolveParent(root, segments, fullPath) {
  let node = root;
  for (let i = 0; i < segments.length - 1; i++) {
    const seg = segments[i];
    if (Array.isArray(node)) {
      const idx = parseArrayIndex(seg, fullPath);
      if (idx >= node.length) {
        throw new PatchError('PATH_NOT_FOUND', `path not found: ${fullPath}`);
      }
      node = node[idx];
    } else if (isPlainObject(node)) {
      if (!Object.prototype.hasOwnProperty.call(node, seg)) {
        throw new PatchError('PATH_NOT_FOUND', `path not found: ${fullPath}`);
      }
      node = node[seg];
    } else {
      throw new PatchError(
        'TYPE_MISMATCH',
        `cannot traverse through non-container at ${JSON.stringify(fullPath)}`
      );
    }
  }
  return node;
}

function applyOp(root, op) {
  if (!op || typeof op !== 'object') {
    throw new PatchError('INVALID_OP', 'patch entry must be an object');
  }
  const { op: kind, path } = op;
  if (kind !== 'add' && kind !== 'remove' && kind !== 'replace') {
    throw new PatchError('INVALID_OP', `unknown op: ${JSON.stringify(kind)}`);
  }
  if (typeof path !== 'string') {
    throw new PatchError('INVALID_OP', 'patch entry missing "path"');
  }
  const segments = parsePointer(path);

  if (segments.length === 0) {
    // Root can only be replaced.
    if (kind !== 'replace') {
      throw new PatchError('INVALID_OP', `cannot ${kind} the document root`);
    }
    if (!('value' in op)) {
      throw new PatchError('INVALID_OP', 'replace requires "value"');
    }
    return { newRoot: clone(op.value), inverse: { op: 'replace', path: '', value: clone(root), prev: clone(op.value) } };
  }

  const parent = resolveParent(root, segments, path);
  const key = segments[segments.length - 1];
  const isArr = Array.isArray(parent);

  if (!isArr && !isPlainObject(parent)) {
    throw new PatchError('TYPE_MISMATCH', `parent of ${JSON.stringify(path)} is not a container`);
  }

  const idx = isArr ? parseArrayIndex(key, path) : null;
  const exists = isArr ? idx < parent.length : Object.prototype.hasOwnProperty.call(parent, key);
  const prev = exists ? (isArr ? parent[idx] : parent[key]) : undefined;

  switch (kind) {
    case 'add': {
      if (!('value' in op)) throw new PatchError('INVALID_OP', 'add requires "value"');
      if (isArr) {
        if (idx > parent.length) {
          throw new PatchError('PATH_NOT_FOUND', `array index out of bounds: ${path}`);
        }
        parent.splice(idx, 0, clone(op.value));
      } else {
        parent[key] = clone(op.value);
      }
      return { inverse: { op: 'remove', path, prev: clone(op.value) } };
    }
    case 'remove': {
      if (!exists) throw new PatchError('PATH_NOT_FOUND', `path not found: ${path}`);
      if (isArr) parent.splice(idx, 1);
      else delete parent[key];
      return { inverse: { op: 'add', path, value: clone(prev) } };
    }
    case 'replace': {
      if (!('value' in op)) throw new PatchError('INVALID_OP', 'replace requires "value"');
      if (!exists) throw new PatchError('PATH_NOT_FOUND', `path not found: ${path}`);
      if (isArr) parent[idx] = clone(op.value);
      else parent[key] = clone(op.value);
      return { inverse: { op: 'replace', path, value: clone(prev), prev: clone(op.value) } };
    }
  }
}

/**
 * Apply a patch to a document. Does not mutate the input.
 * Returns { doc, rollback } where rollback is a patch that undoes the change.
 */
export function apply(doc, patch) {
  if (!Array.isArray(patch)) {
    throw new PatchError('INVALID_OP', 'patch must be an array of operations');
  }
  let root = clone(doc);
  const inverseOps = [];
  for (const op of patch) {
    const { newRoot, inverse } = applyOp(root, op);
    if (newRoot !== undefined) root = newRoot;
    inverseOps.unshift(inverse);
  }
  return { doc: root, rollback: inverseOps };
}

/**
 * Build the inverse of a patch without applying it.
 * Requires remove/replace ops to carry "prev" (patches produced by diff() do).
 */
export function invertPatch(patch) {
  if (!Array.isArray(patch)) {
    throw new PatchError('INVALID_OP', 'patch must be an array of operations');
  }
  const inverse = [];
  for (let i = patch.length - 1; i >= 0; i--) {
    const op = patch[i];
    switch (op.op) {
      case 'add':
        inverse.push({ op: 'remove', path: op.path, prev: clone(op.value) });
        break;
      case 'remove':
        if (!('prev' in op)) {
          throw new PatchError('INVALID_OP', `cannot invert remove at ${op.path}: missing "prev"`);
        }
        inverse.push({ op: 'add', path: op.path, value: clone(op.prev) });
        break;
      case 'replace':
        if (!('prev' in op)) {
          throw new PatchError('INVALID_OP', `cannot invert replace at ${op.path}: missing "prev"`);
        }
        inverse.push({ op: 'replace', path: op.path, value: clone(op.prev), prev: clone(op.value) });
        break;
      default:
        throw new PatchError('INVALID_OP', `unknown op: ${JSON.stringify(op.op)}`);
    }
  }
  return inverse;
}

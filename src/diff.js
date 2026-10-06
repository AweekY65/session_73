import { clone, deepEqual, isPlainObject, joinPointer } from './jsonpatch.js';

/**
 * diff(a, b) -> patch such that apply(a, patch).doc deep-equals b.
 *
 * Strategy:
 * - Objects: compared by key (key insertion order is irrelevant, so
 *   reordering keys never produces a diff). Keys are visited in sorted
 *   order so the generated patch is deterministic.
 * - Arrays: elements are aligned via an LCS over deep-equal elements.
 *   Unmatched regions ("gaps") between aligned anchors pair removals and
 *   insertions positionally: paired elements become in-place edits
 *   (replace / nested diff), the rest become remove / add ops.
 *   Reordering an array therefore yields remove+add of the moved elements.
 * - Anything else (primitives, type changes): a single replace op.
 */
export function diff(a, b) {
  const ops = [];
  diffValue(a, b, '', ops);
  return ops;
}

function diffValue(a, b, path, ops) {
  if (deepEqual(a, b)) return;
  if (isPlainObject(a) && isPlainObject(b)) {
    diffObject(a, b, path, ops);
  } else if (Array.isArray(a) && Array.isArray(b)) {
    diffArray(a, b, path, ops);
  } else {
    ops.push({ op: 'replace', path, value: clone(b), prev: clone(a) });
  }
}

function diffObject(a, b, path, ops) {
  for (const key of Object.keys(a).sort()) {
    if (!Object.prototype.hasOwnProperty.call(b, key)) {
      ops.push({ op: 'remove', path: joinPointer(path, key), prev: clone(a[key]) });
    }
  }
  for (const key of Object.keys(b).sort()) {
    if (!Object.prototype.hasOwnProperty.call(a, key)) {
      ops.push({ op: 'add', path: joinPointer(path, key), value: clone(b[key]) });
    }
  }
  for (const key of Object.keys(a).sort()) {
    if (Object.prototype.hasOwnProperty.call(b, key)) {
      diffValue(a[key], b[key], joinPointer(path, key), ops);
    }
  }
}

/** LCS match pairs [i, j] of deep-equal elements between arrays a and b. */
function lcsMatches(a, b) {
  const n = a.length;
  const m = b.length;
  const dp = Array.from({ length: n + 1 }, () => new Uint32Array(m + 1));
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      dp[i][j] = deepEqual(a[i], b[j])
        ? dp[i + 1][j + 1] + 1
        : Math.max(dp[i + 1][j], dp[i][j + 1]);
    }
  }
  const matches = [];
  let i = 0;
  let j = 0;
  while (i < n && j < m) {
    if (deepEqual(a[i], b[j])) {
      matches.push([i, j]);
      i++;
      j++;
    } else if (dp[i + 1][j] >= dp[i][j + 1]) {
      i++;
    } else {
      j++;
    }
  }
  return matches;
}

function diffArray(a, b, path, ops) {
  const matches = lcsMatches(a, b);
  const anchors = [...matches, [a.length, b.length]];
  let ai = 0;
  let bj = 0;
  let offset = 0; // current index = original a-index + offset

  for (const [mi, mj] of anchors) {
    const remCount = mi - ai;
    const addCount = mj - bj;
    const paired = Math.min(remCount, addCount);

    // Paired elements: edit in place (replace or nested diff).
    for (let k = 0; k < paired; k++) {
      diffValue(a[ai + k], b[bj + k], joinPointer(path, ai + k + offset), ops);
    }
    // Extra removals: repeatedly remove at the same current index (each
    // removal shifts the next doomed element into that same slot).
    const pos = ai + paired + offset;
    for (let k = paired; k < remCount; k++) {
      ops.push({ op: 'remove', path: joinPointer(path, pos), prev: clone(a[ai + k]) });
    }
    offset -= remCount - paired;
    // Extra insertions: insert sequentially at increasing current index.
    for (let k = paired; k < addCount; k++) {
      ops.push({ op: 'add', path: joinPointer(path, pos + (k - paired)), value: clone(b[bj + k]) });
    }
    offset += addCount - paired;

    ai = mi + 1;
    bj = mj + 1;
  }
}

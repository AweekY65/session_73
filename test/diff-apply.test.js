import { test } from 'node:test';
import assert from 'node:assert/strict';
import { diff, apply, invertPatch, deepEqual } from '../src/index.js';

function roundTrip(a, b) {
  const patch = diff(a, b);
  const { doc } = apply(a, patch);
  assert.ok(deepEqual(doc, b), `round-trip failed.\npatch: ${JSON.stringify(patch)}\ngot: ${JSON.stringify(doc)}\nwant: ${JSON.stringify(b)}`);
  return patch;
}

test('nested object: add / remove / replace', () => {
  const a = { user: { name: 'ann', age: 30, tags: ['x'] }, active: true };
  const b = { user: { name: 'ann', age: 31, city: 'sh' }, active: false };
  const patch = roundTrip(a, b);
  const byPath = Object.fromEntries(patch.map((o) => [o.path, o.op]));
  assert.equal(byPath['/user/age'], 'replace');
  assert.equal(byPath['/user/city'], 'add');
  assert.equal(byPath['/user/tags'], 'remove');
  assert.equal(byPath['/active'], 'replace');
});

test('object key order produces no diff', () => {
  const a = { x: 1, y: { p: 1, q: 2 }, z: [1, 2] };
  const b = { z: [1, 2], y: { q: 2, p: 1 }, x: 1 };
  assert.deepEqual(diff(a, b), []);
});

test('array: insert at front', () => {
  const patch = roundTrip([1, 2, 3], [0, 1, 2, 3]);
  assert.deepEqual(patch, [{ op: 'add', path: '/0', value: 0 }]);
});

test('array: delete in middle', () => {
  const patch = roundTrip([1, 2, 3, 4], [1, 4]);
  assert.deepEqual(patch.map((o) => o.op), ['remove', 'remove']);
  assert.deepEqual(patch.map((o) => o.path), ['/1', '/1']);
});

test('array: modify element in place (replace, not remove+add)', () => {
  const patch = roundTrip([1, 2, 3], [1, 9, 3]);
  assert.deepEqual(patch, [{ op: 'replace', path: '/1', value: 9, prev: 2 }]);
});

test('array: modify nested object element', () => {
  const a = [{ id: 1, v: 'a' }, { id: 2, v: 'b' }];
  const b = [{ id: 1, v: 'a' }, { id: 2, v: 'B' }];
  const patch = roundTrip(a, b);
  assert.deepEqual(patch, [{ op: 'replace', path: '/1/v', value: 'B', prev: 'b' }]);
});

test('array: reorder yields remove+add of moved elements', () => {
  const patch = roundTrip([1, 2, 3], [3, 1, 2]);
  assert.deepEqual(patch, [
    { op: 'add', path: '/0', value: 3 },
    { op: 'remove', path: '/3', prev: 3 },
  ]);
});

test('array: grow and shrink', () => {
  roundTrip([1], [1, 2, 3, 4]);
  roundTrip([1, 2, 3, 4], [2, 3]);
  roundTrip([], [1, 2]);
  roundTrip([1, 2], []);
});

test('type change at a path is a replace', () => {
  const patch = roundTrip({ a: [1, 2] }, { a: { b: 1 } });
  assert.deepEqual(patch, [{ op: 'replace', path: '/a', value: { b: 1 }, prev: [1, 2] }]);
});

test('root replace', () => {
  const patch = roundTrip({ a: 1 }, [1, 2, 3]);
  assert.deepEqual(patch, [{ op: 'replace', path: '', value: [1, 2, 3], prev: { a: 1 } }]);
});

test('keys containing / and ~ are escaped per RFC 6901', () => {
  const a = { 'a/b': 1, 't~x': 2 };
  const b = { 'a/b': 10, 't~x': 2 };
  const patch = roundTrip(a, b);
  assert.equal(patch[0].path, '/a~1b');
  roundTrip({ 'a/b': { 'c~d': [1] } }, { 'a/b': { 'c~d': [2] } });
});

test('apply does not mutate the source document', () => {
  const a = { x: 1, arr: [1, 2] };
  const snapshot = structuredClone(a);
  apply(a, diff(a, { x: 2, arr: [3] }));
  assert.deepEqual(a, snapshot);
});

test('round-trip: complex nested document', () => {
  const a = {
    name: 'proj',
    deps: { a: '1.0', b: '2.0' },
    list: [{ n: 1 }, { n: 2, extra: [true, null] }],
    meta: { tags: ['x', 'y'], enabled: true },
  };
  const b = {
    name: 'proj2',
    deps: { b: '2.1', c: '3.0' },
    list: [{ n: 1, flag: false }, { n: 2, extra: [true, null, 'z'] }, { n: 3 }],
    meta: { tags: ['y'], enabled: false, level: 3 },
  };
  roundTrip(a, b);
});

test('rollback: apply then undo restores the original', () => {
  const a = { x: [1, 2, 3], y: { keep: 1, drop: 2 } };
  const b = { x: [0, 1, 3, 4], y: { keep: 9 }, z: 'new' };
  const patch = diff(a, b);
  const { doc, rollback } = apply(a, patch);
  assert.ok(deepEqual(doc, b));
  const { doc: restored } = apply(doc, rollback);
  assert.ok(deepEqual(restored, a));
});

test('invertPatch reverses a patch without applying it', () => {
  const a = { a: 1, b: [1, 2] };
  const b = { a: 2, b: [2], c: true };
  const patch = diff(a, b);
  const inverse = invertPatch(patch);
  const { doc: forward } = apply(a, patch);
  assert.ok(deepEqual(forward, b));
  const { doc: back } = apply(forward, inverse);
  assert.ok(deepEqual(back, a));
});

test('invertPatch rejects patches without prev info', () => {
  assert.throws(
    () => invertPatch([{ op: 'remove', path: '/a' }]),
    /missing "prev"/
  );
});

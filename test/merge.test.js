import { test } from 'node:test';
import assert from 'node:assert/strict';
import { merge, deepEqual } from '../src/index.js';

test('no-conflict merge: different paths merge automatically', () => {
  const base = { a: 1, b: 2, nested: { x: 1, y: 2 } };
  const left = { a: 10, b: 2, nested: { x: 1, y: 2 } };
  const right = { a: 1, b: 2, nested: { x: 1, y: 20 } };
  const { doc, conflicts } = merge(base, left, right);
  assert.deepEqual(conflicts, []);
  assert.deepEqual(doc, { a: 10, b: 2, nested: { x: 1, y: 20 } });
});

test('no-conflict merge: one side adds, other deletes a different key', () => {
  const base = { keep: 1, drop: 2 };
  const left = { keep: 1 }; // deleted drop
  const right = { keep: 1, drop: 2, added: 3 }; // added added
  const { doc, conflicts } = merge(base, left, right);
  assert.deepEqual(conflicts, []);
  assert.deepEqual(doc, { keep: 1, added: 3 });
});

test('identical changes on both sides are not conflicts', () => {
  const base = { a: 1 };
  const side = { a: 2, b: [1, 2] };
  const { doc, conflicts } = merge(base, side, structuredClone(side));
  assert.deepEqual(conflicts, []);
  assert.deepEqual(doc, side);
});

test('conflict: same path modified differently', () => {
  const base = { v: 1 };
  const { doc, conflicts } = merge(base, { v: 2 }, { v: 3 });
  assert.equal(conflicts.length, 1);
  assert.equal(conflicts[0].path, '/v');
  assert.equal(conflicts[0].reason, 'incompatible-modification');
  assert.deepEqual({ base: conflicts[0].base, left: conflicts[0].left, right: conflicts[0].right },
    { base: 1, left: 2, right: 3 });
  assert.equal(doc.v, 1); // keeps base on conflict
});

test('conflict: delete vs modify', () => {
  const base = { a: 1, b: 2 };
  const left = { a: 1 }; // deleted b
  const right = { a: 1, b: 99 }; // modified b
  const { doc, conflicts } = merge(base, left, right);
  assert.equal(conflicts.length, 1);
  assert.equal(conflicts[0].path, '/b');
  assert.equal(conflicts[0].reason, 'delete-vs-modify');
  assert.equal(doc.b, 2);
});

test('conflict: both sides create same key with different values', () => {
  const base = {};
  const { doc, conflicts } = merge(base, { k: 'left' }, { k: 'right' });
  assert.equal(conflicts.length, 1);
  assert.equal(conflicts[0].reason, 'create-vs-create');
  assert.equal(doc.k, 'left'); // no base value: keeps left
});

test('conflict: nested object vs primitive (type change)', () => {
  const base = { n: { x: 1 } };
  const { conflicts } = merge(base, { n: { x: 2 } }, { n: 5 });
  assert.equal(conflicts.length, 1);
  assert.equal(conflicts[0].path, '/n');
});

test('arrays: same-length element edits merge per index', () => {
  const base = { list: [1, 2, 3] };
  const left = { list: [10, 2, 3] };
  const right = { list: [1, 2, 30] };
  const { doc, conflicts } = merge(base, left, right);
  assert.deepEqual(conflicts, []);
  assert.deepEqual(doc.list, [10, 2, 30]);
});

test('arrays: both sides change length differently -> whole-array conflict', () => {
  const base = { list: [1, 2, 3] };
  const left = { list: [1, 2, 3, 4] };
  const right = { list: [1, 2] };
  const { doc, conflicts } = merge(base, left, right);
  assert.equal(conflicts.length, 1);
  assert.equal(conflicts[0].path, '/list');
  assert.equal(conflicts[0].reason, 'array-structure-conflict');
  assert.deepEqual(doc.list, [1, 2, 3]);
});

test('arrays: only one side restructures -> taken automatically', () => {
  const base = { list: [1, 2, 3] };
  const left = { list: [3, 2, 1] };
  const right = { list: [1, 2, 3] };
  const { doc, conflicts } = merge(base, left, right);
  assert.deepEqual(conflicts, []);
  assert.deepEqual(doc.list, [3, 2, 1]);
});

test('merge result is independent of input object key order', () => {
  const base = { a: 1, b: 2 };
  const left = { b: 2, a: 10 };
  const right = { b: 20, a: 1 };
  const { doc, conflicts } = merge(base, left, right);
  assert.deepEqual(conflicts, []);
  assert.ok(deepEqual(doc, { a: 10, b: 20 }));
});

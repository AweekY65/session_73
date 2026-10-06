import { test } from 'node:test';
import assert from 'node:assert/strict';
import { apply, PatchError } from '../src/index.js';

const doc = { a: { b: 1 }, arr: [1, 2, 3], s: 'text' };

function expectCode(patch, code) {
  assert.throws(() => apply(doc, patch), (err) => {
    assert.ok(err instanceof PatchError);
    assert.equal(err.code, code, `expected ${code}, got ${err.code}: ${err.message}`);
    return true;
  });
}

test('remove on nonexistent path -> PATH_NOT_FOUND', () => {
  expectCode([{ op: 'remove', path: '/a/nope' }], 'PATH_NOT_FOUND');
  expectCode([{ op: 'remove', path: '/missing/deep/path' }], 'PATH_NOT_FOUND');
});

test('replace on nonexistent path -> PATH_NOT_FOUND', () => {
  expectCode([{ op: 'replace', path: '/a/nope', value: 1 }], 'PATH_NOT_FOUND');
});

test('array index out of bounds -> PATH_NOT_FOUND', () => {
  expectCode([{ op: 'remove', path: '/arr/5' }], 'PATH_NOT_FOUND');
  expectCode([{ op: 'add', path: '/arr/9', value: 0 }], 'PATH_NOT_FOUND');
});

test('type mismatch: object key used on array and vice versa', () => {
  expectCode([{ op: 'remove', path: '/arr/foo' }], 'TYPE_MISMATCH');
  expectCode([{ op: 'remove', path: '/arr/0/x' }], 'TYPE_MISMATCH');
  expectCode([{ op: 'replace', path: '/s/x', value: 1 }], 'TYPE_MISMATCH');
});

test('invalid operations are rejected', () => {
  expectCode([{ op: 'move', path: '/a' }], 'INVALID_OP');
  expectCode([{ op: 'add', path: '/a/x' }], 'INVALID_OP'); // missing value
  expectCode([{ op: 'replace', path: '/a/b' }], 'INVALID_OP'); // missing value
  expectCode([{ path: '/a/b' }], 'INVALID_OP'); // missing op
  expectCode([{ op: 'remove' }], 'INVALID_OP'); // missing path
  expectCode([{ op: 'add', path: '', value: 1 }], 'INVALID_OP'); // add at root
  expectCode('not-an-array', 'INVALID_OP');
  expectCode([{ op: 'remove', path: 'no-leading-slash' }], 'INVALID_OP');
});

test('failed apply leaves the input document untouched', () => {
  const before = structuredClone(doc);
  assert.throws(() => apply(doc, [{ op: 'remove', path: '/a/nope' }]));
  assert.deepEqual(doc, before);
});

test('add at array end (index == length) is legal', () => {
  const { doc: out } = apply(doc, [{ op: 'add', path: '/arr/3', value: 4 }]);
  assert.deepEqual(out.arr, [1, 2, 3, 4]);
});

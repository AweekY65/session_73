#!/usr/bin/env node
import { readFileSync, writeFileSync } from 'node:fs';
import { diff, apply, merge, invertPatch } from './src/index.js';

const [, , command, ...args] = process.argv;

function usage() {
  console.error(`Usage:
  node cli.js diff   <a.json> <b.json> [patch.json]
  node cli.js apply  <doc.json> <patch.json> [out.json]
  node cli.js invert <patch.json> [inverse.json]
  node cli.js merge  <base.json> <left.json> <right.json> [merged.json]`);
  process.exit(2);
}

const readJson = (file) => JSON.parse(readFileSync(file, 'utf8'));
const writeJson = (file, value) => {
  const text = JSON.stringify(value, null, 2) + '\n';
  if (file) writeFileSync(file, text);
  else process.stdout.write(text);
};

try {
  switch (command) {
    case 'diff': {
      if (args.length < 2) usage();
      writeJson(args[2], diff(readJson(args[0]), readJson(args[1])));
      break;
    }
    case 'apply': {
      if (args.length < 2) usage();
      const { doc, rollback } = apply(readJson(args[0]), readJson(args[1]));
      writeJson(args[2], doc);
      console.error(`applied OK (rollback patch: ${rollback.length} op(s))`);
      break;
    }
    case 'invert': {
      if (args.length < 1) usage();
      writeJson(args[1], invertPatch(readJson(args[0])));
      break;
    }
    case 'merge': {
      if (args.length < 3) usage();
      const { doc, conflicts } = merge(readJson(args[0]), readJson(args[1]), readJson(args[2]));
      writeJson(args[3], doc);
      if (conflicts.length > 0) {
        console.error(`merge finished with ${conflicts.length} conflict(s):`);
        for (const c of conflicts) console.error(`  ${c.path || '/'} (${c.reason})`);
        process.exitCode = 1;
      } else {
        console.error('merge clean, no conflicts');
      }
      break;
    }
    default:
      usage();
  }
} catch (err) {
  console.error(`${err.name}: ${err.message}`);
  process.exit(1);
}

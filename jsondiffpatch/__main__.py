"""Terminal CLI: python -m jsondiffpatch <command> [files...]

Commands (all I/O is local files / stdin-stdout only):
    diff    A.json B.json              print patch transforming A into B
    apply   DOC.json PATCH.json        print patched document
    invert  PATCH.json                 print inverse (rollback) patch
    merge   BASE.json L.json R.json    print merged doc; conflicts -> stderr, exit 1
"""

import json
import sys

from .diff import diff
from .errors import PatchError
from .merge import merge
from .patch import apply, invert


def _load(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _dump(value, fh=sys.stdout):
    json.dump(value, fh, indent=2, ensure_ascii=False, sort_keys=True)
    fh.write("\n")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 0
    cmd, args = argv[0], argv[1:]
    try:
        if cmd == "diff" and len(args) == 2:
            _dump(diff(_load(args[0]), _load(args[1])))
        elif cmd == "apply" and len(args) == 2:
            _dump(apply(_load(args[0]), _load(args[1])))
        elif cmd == "invert" and len(args) == 1:
            _dump(invert(_load(args[0])))
        elif cmd == "merge" and len(args) == 3:
            result = merge(_load(args[0]), _load(args[1]), _load(args[2]))
            _dump(result.merged)
            for conflict in result.conflicts:
                print("CONFLICT %s: %s" % (conflict.path, conflict.reason),
                      file=sys.stderr)
            return 0 if result.clean else 1
        else:
            print("usage error, see --help", file=sys.stderr)
            return 2
    except (PatchError, OSError, json.JSONDecodeError) as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

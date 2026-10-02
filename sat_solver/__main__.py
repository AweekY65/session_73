"""Command line interface: ``python3 -m sat_solver <file.cnf>``."""

import sys

from .dimacs import DimacsError, parse_dimacs_file
from .dpll import SAT, solve, verify


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("usage: python3 -m sat_solver <file.cnf>", file=sys.stderr)
        return 2
    try:
        nvars, clauses = parse_dimacs_file(argv[0])
    except DimacsError as exc:
        print("parse error: %s" % exc, file=sys.stderr)
        return 2
    except OSError as exc:
        print("io error: %s" % exc, file=sys.stderr)
        return 2

    result = solve(nvars, clauses)
    print(result.status)
    print("stats: %s" % result.stats)
    if result.status == SAT:
        assert verify(clauses, result.model)
        assignment = " ".join(
            str(var if val else -var) for var, val in sorted(result.model.items())
        )
        print("v %s 0" % assignment)
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())

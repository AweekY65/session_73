"""Strict DIMACS CNF parser.

Grammar accepted (whitespace-insensitive, tokens separated by spaces)::

    <file>      ::= <comment>* <header> <body> <endmarker>?
    <comment>   ::= "c" <anything>            (allowed anywhere)
    <header>    ::= "p cnf" <nvars> <nclauses>
    <body>      ::= <clause>{nclauses}
    <clause>    ::= <lit>* "0"                (may span multiple lines)
    <endmarker> ::= "%"                       (alone on its line, must be last)

Validation rules (all violations raise :class:`DimacsError`):

* exactly one ``p cnf`` header, appearing before any clause token;
* ``nvars`` and ``nclauses`` are non-negative integers;
* every literal ``l`` satisfies ``1 <= |l| <= nvars``;
* every clause is terminated by ``0``;
* the number of clauses equals the declared ``nclauses``;
* an optional ``%`` end marker must be alone on its line and no
  non-empty content may follow it.
"""


class DimacsError(ValueError):
    """Raised when a DIMACS CNF input is malformed."""


def parse_dimacs(text):
    """Parse DIMACS CNF text.

    Returns ``(nvars, clauses)`` where ``clauses`` is a list of
    ``frozenset`` of non-zero ints (literals).  Duplicate literals inside
    a clause collapse naturally through the set representation; tautology
    clauses are kept verbatim here and handled by the solver.
    """
    nvars = None
    expected_clauses = None
    clauses = []
    current = []
    seen_header = False
    seen_end_marker = False

    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        if seen_end_marker:
            raise DimacsError(
                "line %d: unexpected content after '%%' end marker" % lineno
            )
        first = line.split(None, 1)[0]
        if first == "c":
            continue
        if first == "%":
            if line != "%":
                raise DimacsError(
                    "line %d: '%%' end marker must be alone on its line" % lineno
                )
            seen_end_marker = True
            continue
        if first == "p":
            if seen_header:
                raise DimacsError("line %d: duplicate 'p cnf' header" % lineno)
            parts = line.split()
            if len(parts) != 4 or parts[1] != "cnf":
                raise DimacsError(
                    "line %d: header must be 'p cnf <nvars> <nclauses>'" % lineno
                )
            try:
                nvars = int(parts[2])
                expected_clauses = int(parts[3])
            except ValueError:
                raise DimacsError(
                    "line %d: nvars and nclauses must be integers" % lineno
                )
            if nvars < 0 or expected_clauses < 0:
                raise DimacsError(
                    "line %d: nvars and nclauses must be non-negative" % lineno
                )
            seen_header = True
            continue
        if not seen_header:
            raise DimacsError(
                "line %d: clause data before 'p cnf' header" % lineno
            )
        for tok in line.split():
            try:
                lit = int(tok)
            except ValueError:
                raise DimacsError(
                    "line %d: invalid literal token %r" % (lineno, tok)
                )
            if lit == 0:
                clauses.append(frozenset(current))
                current = []
            else:
                if abs(lit) > nvars:
                    raise DimacsError(
                        "line %d: literal %d exceeds declared nvars=%d"
                        % (lineno, lit, nvars)
                    )
                current.append(lit)

    if not seen_header:
        raise DimacsError("missing 'p cnf' header")
    if current:
        raise DimacsError("last clause is not terminated by 0")
    if len(clauses) != expected_clauses:
        raise DimacsError(
            "declared %d clauses but found %d" % (expected_clauses, len(clauses))
        )
    return nvars, clauses


def parse_dimacs_file(path):
    with open(path, "r", encoding="utf-8") as fh:
        return parse_dimacs(fh.read())

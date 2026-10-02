"""Local DPLL SAT solver.

Pure-Python, self-contained SAT solver. No external solver (Z3, MiniSat,
cloud services) is used; the core DPLL algorithm is implemented here.

Features:
  * Strict DIMACS CNF parsing (header, clause format, '%' end marker).
  * DPLL with unit propagation, pure literal elimination and a
    max-occurrence (DLIS-like) variable selection heuristic.
  * Deterministic semantics for empty formulas, empty clauses,
    duplicate literals and tautological clauses.
  * Decision / backtracking statistics.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

Clause = Tuple[int, ...]
Assignment = Dict[int, bool]


class DimacsError(Exception):
    """Raised when a DIMACS CNF input is malformed."""


# ---------------------------------------------------------------------------
# DIMACS parsing
# ---------------------------------------------------------------------------

def parse_dimacs(text: str) -> Tuple[int, List[Clause]]:
    """Parse DIMACS CNF text into (num_vars, clauses).

    Strict rules:
      * Optional comment lines start with 'c'.
      * Exactly one header line: ``p cnf <nvars> <nclauses>``.
      * Clauses are whitespace separated integers, each clause ends with 0
        and may span multiple lines.
      * Every literal L must satisfy 1 <= |L| <= nvars.
      * The number of clauses must equal the declared <nclauses>.
      * The clause section must be terminated by a '%' line; after it only
        whitespace and an optional single '0' are allowed.

    Normalisation semantics (deterministic):
      * Duplicate literals inside a clause are removed.
      * Tautological clauses (containing both x and -x) are dropped.
      * An empty clause is preserved and makes the formula UNSAT.
    """
    num_vars: Optional[int] = None
    declared_clauses: Optional[int] = None
    clauses: List[Clause] = []
    raw_clause_count = 0
    current: List[int] = []
    seen_header = False
    seen_end_marker = False

    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue

        if seen_end_marker:
            # After '%' only an optional trailing '0' is tolerated.
            if line == "0":
                continue
            raise DimacsError(
                f"line {lineno}: unexpected content after '%' end marker: {line!r}"
            )

        if line.startswith("c"):
            continue

        if line.startswith("p"):
            if seen_header:
                raise DimacsError(f"line {lineno}: duplicate 'p cnf' header")
            parts = line.split()
            if len(parts) != 4 or parts[1] != "cnf":
                raise DimacsError(
                    f"line {lineno}: malformed header, expected 'p cnf <nvars> <nclauses>'"
                )
            try:
                num_vars = int(parts[2])
                declared_clauses = int(parts[3])
            except ValueError:
                raise DimacsError(f"line {lineno}: header values must be integers")
            if num_vars < 0 or declared_clauses < 0:
                raise DimacsError(f"line {lineno}: header values must be >= 0")
            seen_header = True
            continue

        if not seen_header:
            raise DimacsError(f"line {lineno}: content before 'p cnf' header")

        if line == "%":
            if current:
                raise DimacsError(
                    f"line {lineno}: '%' end marker inside an unterminated clause"
                )
            seen_end_marker = True
            continue

        for token in line.split():
            try:
                lit = int(token)
            except ValueError:
                raise DimacsError(f"line {lineno}: invalid literal {token!r}")
            if lit == 0:
                raw_clause_count += 1
                norm = normalize_clause(current)
                if norm is not None:  # None == tautology: drop the clause
                    clauses.append(norm)
                current = []
                continue
            if abs(lit) > num_vars:
                raise DimacsError(
                    f"line {lineno}: literal {lit} exceeds declared {num_vars} variables"
                )
            current.append(lit)

    if not seen_header:
        raise DimacsError("missing 'p cnf' header")
    if current:
        raise DimacsError("last clause is not terminated by 0")
    if not seen_end_marker:
        raise DimacsError("missing '%' end-of-file marker")
    if raw_clause_count != declared_clauses:
        raise DimacsError(
            f"declared {declared_clauses} clauses but found {raw_clause_count}"
        )
    return num_vars, clauses


def normalize_clause(literals: Sequence[int]) -> Optional[Clause]:
    """Deterministic clause normalisation.

    * Duplicates are removed.
    * Returns None for a tautology (x and -x both present); the caller
      drops such clauses because they are always satisfied.
    * An empty input yields the empty clause ``()`` (a real conflict).
    """
    seen = set()
    out: List[int] = []
    for lit in literals:
        if -lit in seen:
            return None
        if lit not in seen:
            seen.add(lit)
            out.append(lit)
    return tuple(sorted(out, key=lambda l: (abs(l), l < 0)))


# ---------------------------------------------------------------------------
# Statistics and result types
# ---------------------------------------------------------------------------

@dataclass
class Stats:
    """Search statistics collected during DPLL."""

    propagations: int = 0      # unit-propagated assignments
    pure_literals: int = 0     # pure-literal assignments
    decisions: int = 0         # branching decisions
    backtracks: int = 0        # times a decision branch was undone

    def __str__(self) -> str:  # pragma: no cover - cosmetic
        return (
            f"propagations={self.propagations} pure_literals={self.pure_literals} "
            f"decisions={self.decisions} backtracks={self.backtracks}"
        )


@dataclass
class SolveResult:
    sat: bool
    model: Optional[Assignment]  # complete assignment when sat
    stats: Stats


# ---------------------------------------------------------------------------
# DPLL solver
# ---------------------------------------------------------------------------

class SatSolver:
    """DPLL solver over a normalised CNF instance."""

    def __init__(self, num_vars: int, clauses: Sequence[Sequence[int]]):
        self.num_vars = num_vars
        # Normalise again so the solver can also be used programmatically.
        normalised: List[Clause] = []
        for clause in clauses:
            norm = normalize_clause(clause)
            if norm is None:
                continue  # tautology: always satisfied, drop it
            normalised.append(norm)
        self.clauses: List[Clause] = normalised
        self.stats = Stats()

    # -- public API --------------------------------------------------------

    def solve(self) -> SolveResult:
        assignment: Assignment = {}
        sat = self._dpll(list(self.clauses), assignment)
        if not sat:
            return SolveResult(False, None, self.stats)
        model = self.complete_model(assignment)
        return SolveResult(True, model, self.stats)

    def complete_model(self, assignment: Assignment) -> Assignment:
        """Extend a partial satisfying assignment to all variables.

        Variables left unassigned are don't-cares: any value keeps the
        formula satisfied. We deterministically extend them with False.
        """
        model = dict(assignment)
        for var in range(1, self.num_vars + 1):
            model.setdefault(var, False)
        return model

    # -- DPLL core ---------------------------------------------------------

    def _dpll(self, clauses: List[Clause], assignment: Assignment) -> bool:
        # Unit propagation (to fixpoint).
        clauses = self._unit_propagate(clauses, assignment)
        if clauses is None:
            return False
        # Pure literal elimination (to fixpoint).
        clauses = self._pure_literal_elimination(clauses, assignment)
        if clauses is None:
            return False
        if not clauses:
            return True

        var = self._choose_variable(clauses)
        self.stats.decisions += 1
        for value in (True, False):
            branch = dict(assignment)
            branch[var] = value
            lit = var if value else -var
            simplified = self._simplify(clauses, lit)
            if simplified is not None and self._dpll(simplified, branch):
                assignment.clear()
                assignment.update(branch)
                return True
            self.stats.backtracks += 1
        return False

    def _unit_propagate(
        self, clauses: List[Clause], assignment: Assignment
    ) -> Optional[List[Clause]]:
        while True:
            unit = None
            for clause in clauses:
                if len(clause) == 0:
                    return None  # empty clause: conflict
                if len(clause) == 1:
                    unit = clause[0]
                    break
            if unit is None:
                return clauses
            var, value = abs(unit), unit > 0
            existing = assignment.get(var)
            if existing is not None and existing != value:
                return None  # contradictory units
            if existing is None:
                assignment[var] = value
                self.stats.propagations += 1
            clauses = self._simplify(clauses, unit)
            if clauses is None:
                return None

    def _pure_literal_elimination(
        self, clauses: List[Clause], assignment: Assignment
    ) -> Optional[List[Clause]]:
        while True:
            polarity: Dict[int, int] = {}
            for clause in clauses:
                for lit in clause:
                    var = abs(lit)
                    if var in assignment:
                        continue
                    mask = 1 if lit > 0 else 2
                    polarity[var] = polarity.get(var, 0) | mask
            pure = [v for v, m in polarity.items() if m in (1, 2)]
            if not pure:
                return clauses
            for var in sorted(pure):
                value = polarity[var] == 1
                assignment[var] = value
                self.stats.pure_literals += 1
                clauses = self._simplify(clauses, var if value else -var)
                if clauses is None:
                    return None

    @staticmethod
    def _choose_variable(clauses: List[Clause]) -> int:
        """Max-occurrence (DLIS-like) heuristic, ties -> smallest index."""
        counts: Dict[int, int] = {}
        for clause in clauses:
            for lit in clause:
                var = abs(lit)
                counts[var] = counts.get(var, 0) + 1
        return max(counts, key=lambda v: (counts[v], -v))

    @staticmethod
    def _simplify(clauses: List[Clause], lit: int) -> Optional[List[Clause]]:
        """Assign literal ``lit`` true and simplify; None on conflict."""
        out: List[Clause] = []
        neg = -lit
        for clause in clauses:
            if lit in clause:
                continue  # clause satisfied
            if neg in clause:
                reduced = tuple(l for l in clause if l != neg)
                if not reduced:
                    return None  # empty clause: conflict
                out.append(reduced)
            else:
                out.append(clause)
        return out


# ---------------------------------------------------------------------------
# Model verification
# ---------------------------------------------------------------------------

def verify_model(num_vars: int, clauses: Sequence[Sequence[int]], model: Assignment) -> bool:
    """Check that ``model`` satisfies every clause of the original formula."""
    for var in range(1, num_vars + 1):
        if var not in model:
            return False
    for clause in clauses:
        if not any(model[abs(lit)] == (lit > 0) for lit in clause):
            return False
    return True


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: Sequence[str]) -> int:
    if len(argv) != 2:
        print("usage: python sat_solver.py <file.cnf>", file=sys.stderr)
        return 2
    with open(argv[1], "r", encoding="utf-8") as fh:
        text = fh.read()
    try:
        num_vars, clauses = parse_dimacs(text)
    except DimacsError as exc:
        print(f"DIMACS error: {exc}", file=sys.stderr)
        return 2

    solver = SatSolver(num_vars, clauses)
    result = solver.solve()
    if result.sat:
        assert verify_model(num_vars, clauses, result.model)
        print("SAT")
        print("model:", " ".join(
            f"{'' if val else '-'}{var}" for var, val in sorted(result.model.items())
        ))
    else:
        print("UNSAT")
    print(f"stats: {result.stats}")
    return 0 if result.sat else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))

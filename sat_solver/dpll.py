"""DPLL SAT solver with unit propagation, pure literal elimination and
a Jeroslow-Wang branching heuristic.

The solver is fully self-contained: no external SAT libraries, no
network access, no timeouts-based guessing.  Termination is guaranteed
because every decision fixes one more variable.

Deterministic semantics for degenerate input:

* empty formula (no clauses)        -> SAT, every assignment is a model;
* empty clause                      -> UNSAT (conflict at the root);
* duplicate literals in a clause    -> collapsed (set semantics);
* tautology clause (x and -x)       -> always true, dropped at load time.
"""

import sys
from dataclasses import dataclass, field

SAT = "SAT"
UNSAT = "UNSAT"


@dataclass
class Stats:
    """Search statistics collected during a solve."""

    decisions: int = 0
    propagations: int = 0
    pure_literals: int = 0
    backtracks: int = 0

    def __str__(self):
        return (
            "decisions=%d propagations=%d pure_literals=%d backtracks=%d"
            % (self.decisions, self.propagations, self.pure_literals,
               self.backtracks)
        )


@dataclass
class Result:
    status: str
    model: dict = None  # var -> bool, complete when status == SAT
    stats: Stats = field(default_factory=Stats)

    @property
    def satisfiable(self):
        return self.status == SAT


def preprocess(clauses):
    """Drop tautology clauses.  Duplicate literals are already collapsed
    by the frozenset representation."""
    return [c for c in clauses if not any(-lit in c for lit in c)]


def _simplify(clauses, lit):
    """Assign literal ``lit`` to true.

    Returns the reduced clause list, or ``None`` on conflict (an empty
    clause is produced).
    """
    new_clauses = []
    for clause in clauses:
        if lit in clause:
            continue  # clause satisfied
        reduced = clause - {-lit}
        if not reduced:
            return None  # empty clause -> conflict
        new_clauses.append(reduced)
    return new_clauses


def _choose_literal(clauses):
    """Jeroslow-Wang one-sided heuristic: score every literal with
    ``sum(2 ** -len(clause))`` over the clauses it occurs in, pick the
    variable with the highest combined score and the polarity with the
    higher individual score."""
    scores = {}
    for clause in clauses:
        weight = 2.0 ** -len(clause)
        for lit in clause:
            scores[lit] = scores.get(lit, 0.0) + weight
    best_var = None
    best_total = -1.0
    for var in {abs(lit) for lit in scores}:
        total = scores.get(var, 0.0) + scores.get(-var, 0.0)
        if total > best_total:
            best_total = total
            best_var = var
    if scores.get(best_var, 0.0) >= scores.get(-best_var, 0.0):
        return best_var
    return -best_var


def _propagate(clauses, assignment, stats):
    """Unit propagation and pure literal elimination to fixpoint.

    Returns ``(clauses, changed)`` or ``(None, changed)`` on conflict.
    """
    changed = False
    while True:
        unit = None
        for clause in clauses:
            if len(clause) == 1:
                unit = next(iter(clause))
                break
        if unit is None:
            break
        assignment[abs(unit)] = unit > 0
        stats.propagations += 1
        clauses = _simplify(clauses, unit)
        changed = True
        if clauses is None:
            return None, changed

    polarity = {}
    for clause in clauses:
        for lit in clause:
            polarity.setdefault(abs(lit), set()).add(lit > 0)
    pures = [var for var, signs in polarity.items() if len(signs) == 1]
    for var in pures:
        sign = next(iter(polarity[var]))
        assignment[var] = sign
        stats.pure_literals += 1
        clauses = _simplify(clauses, var if sign else -var)
        changed = True
        if clauses is None:  # cannot happen for pure literals, be safe
            return None, changed
    if pures:
        # pure literal elimination may have created new units
        more, more_changed = _propagate(clauses, assignment, stats)
        return more, changed or more_changed
    return clauses, changed


def _dpll(clauses, assignment, stats):
    clauses, _ = _propagate(clauses, assignment, stats)
    if clauses is None:
        return False
    if not clauses:
        return True

    lit = _choose_literal(clauses)
    var = abs(lit)
    stats.decisions += 1
    for branch in (lit, -lit):
        assignment[var] = branch > 0
        reduced = _simplify(clauses, branch)
        if reduced is not None and _dpll(reduced, assignment, stats):
            return True
        stats.backtracks += 1
        assignment.pop(var, None)
    return False


def solve(nvars, clauses):
    """Solve a CNF formula.

    ``clauses`` is an iterable of iterables of ints (literals).
    Returns a :class:`Result`; on SAT ``model`` maps every variable in
    ``1..nvars`` to a bool (unconstrained variables default to False,
    so the model is always complete and directly verifiable).
    """
    if sys.getrecursionlimit() < 100000:
        sys.setrecursionlimit(100000)
    stats = Stats()
    norm = [frozenset(c) for c in clauses]
    norm = preprocess(norm)
    if any(len(c) == 0 for c in norm):
        return Result(UNSAT, None, stats)
    assignment = {}
    if _dpll(norm, assignment, stats):
        model = {var: assignment.get(var, False) for var in range(1, nvars + 1)}
        return Result(SAT, model, stats)
    return Result(UNSAT, None, stats)


def verify(clauses, model):
    """Check that ``model`` (var -> bool) satisfies every clause."""
    for clause in clauses:
        if not any(model.get(abs(lit), False) == (lit > 0) for lit in clause):
            return False
    return True

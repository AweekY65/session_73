import itertools
import random
import unittest

from sat_solver import (
    DimacsError,
    SAT,
    UNSAT,
    parse_dimacs,
    solve,
    verify,
)


def brute_force(nvars, clauses):
    """Exhaustive oracle: returns a satisfying model dict or None."""
    for values in itertools.product([False, True], repeat=nvars):
        model = {i + 1: values[i] for i in range(nvars)}
        if verify(clauses, model):
            return model
    return None


def pigeonhole(pigeons, holes):
    """PHP(pigeons, holes) as (nvars, clauses); UNSAT iff pigeons > holes."""
    def var(p, h):
        return p * holes + h + 1

    clauses = []
    for p in range(pigeons):
        clauses.append([var(p, h) for h in range(holes)])
    for h in range(holes):
        for p1 in range(pigeons):
            for p2 in range(p1 + 1, pigeons):
                clauses.append([-var(p1, h), -var(p2, h)])
    return pigeons * holes, clauses


class TestDimacs(unittest.TestCase):
    def test_basic_parse(self):
        nvars, clauses = parse_dimacs(
            "c comment\np cnf 3 2\n1 -2 0\n2 3\n0\n"
        )
        self.assertEqual(nvars, 3)
        self.assertEqual(clauses, [frozenset({1, -2}), frozenset({2, 3})])

    def test_end_marker_accepted(self):
        nvars, clauses = parse_dimacs("p cnf 1 1\n1 0\n%\n")
        self.assertEqual(clauses, [frozenset({1})])

    def test_missing_header(self):
        with self.assertRaises(DimacsError):
            parse_dimacs("1 0\n")

    def test_bad_header_format(self):
        with self.assertRaises(DimacsError):
            parse_dimacs("p sat 2 1\n1 0\n")

    def test_duplicate_header(self):
        with self.assertRaises(DimacsError):
            parse_dimacs("p cnf 1 1\np cnf 1 1\n1 0\n")

    def test_variable_out_of_range(self):
        with self.assertRaises(DimacsError):
            parse_dimacs("p cnf 2 1\n1 3 0\n")

    def test_unterminated_clause(self):
        with self.assertRaises(DimacsError):
            parse_dimacs("p cnf 2 1\n1 -2\n")

    def test_clause_count_mismatch(self):
        with self.assertRaises(DimacsError):
            parse_dimacs("p cnf 1 2\n1 0\n")

    def test_invalid_token(self):
        with self.assertRaises(DimacsError):
            parse_dimacs("p cnf 1 1\nx 0\n")

    def test_content_after_end_marker(self):
        with self.assertRaises(DimacsError):
            parse_dimacs("p cnf 1 1\n1 0\n%\n2 0\n")

    def test_end_marker_not_alone(self):
        with self.assertRaises(DimacsError):
            parse_dimacs("p cnf 1 1\n1 0\n% trailing\n")


class TestDegenerateSemantics(unittest.TestCase):
    def test_empty_formula_is_sat(self):
        result = solve(3, [])
        self.assertEqual(result.status, SAT)
        self.assertTrue(verify([], result.model))

    def test_empty_clause_is_unsat(self):
        result = solve(2, [frozenset()])
        self.assertEqual(result.status, UNSAT)

    def test_duplicate_literals(self):
        result = solve(1, [[1, 1, 1]])
        self.assertEqual(result.status, SAT)
        self.assertTrue(result.model[1])

    def test_tautology_clause_is_dropped(self):
        result = solve(2, [[1, -1], [2]])
        self.assertEqual(result.status, SAT)
        self.assertTrue(verify([[1, -1], [2]], result.model))
        self.assertTrue(result.model[2])


class TestDPLL(unittest.TestCase):
    def test_simple_sat(self):
        result = solve(2, [[1, 2], [-1, 2]])
        self.assertEqual(result.status, SAT)
        self.assertTrue(verify([[1, 2], [-1, 2]], result.model))

    def test_simple_unsat(self):
        clauses = [[1], [-1]]
        result = solve(1, clauses)
        self.assertEqual(result.status, UNSAT)
        self.assertIsNone(result.model)

    def test_unit_propagation_chain(self):
        # x1, then -x1 v x2, then -x2 v x3 forces x1=x2=x3=True
        clauses = [[1], [-1, 2], [-2, 3]]
        result = solve(3, clauses)
        self.assertEqual(result.status, SAT)
        self.assertEqual(result.model, {1: True, 2: True, 3: True})
        self.assertGreaterEqual(result.stats.propagations, 3)
        self.assertEqual(result.stats.decisions, 0)

    def test_pure_literal_elimination(self):
        # 2 occurs only positively, -3 only negatively
        clauses = [[1, 2], [-1, 2], [1, -3]]
        result = solve(3, clauses)
        self.assertEqual(result.status, SAT)
        self.assertGreaterEqual(result.stats.pure_literals, 1)
        self.assertTrue(verify(clauses, result.model))

    def test_deep_backtracking_pigeonhole(self):
        nvars, clauses = pigeonhole(4, 3)
        result = solve(nvars, clauses)
        self.assertEqual(result.status, UNSAT)
        self.assertGreater(result.stats.backtracks, 0)
        self.assertGreater(result.stats.decisions, 0)

    def test_sat_pigeonhole_boundary(self):
        nvars, clauses = pigeonhole(3, 3)
        result = solve(nvars, clauses)
        self.assertEqual(result.status, SAT)
        self.assertTrue(verify(clauses, result.model))

    def test_statistics_reported(self):
        result = solve(2, [[1, 2], [-1, -2]])
        for field_name in ("decisions", "propagations", "backtracks"):
            self.assertGreaterEqual(getattr(result.stats, field_name), 0)


class TestRandomOracle(unittest.TestCase):
    def test_random_small_formulas_against_brute_force(self):
        rng = random.Random(20261002)
        for _ in range(300):
            nvars = rng.randint(1, 5)
            nclauses = rng.randint(0, 10)
            clauses = []
            for _ in range(nclauses):
                size = rng.randint(1, 3)
                clause = [
                    rng.choice([-1, 1]) * rng.randint(1, nvars)
                    for _ in range(size)
                ]
                clauses.append(clause)
            result = solve(nvars, clauses)
            oracle = brute_force(nvars, clauses)
            if oracle is None:
                self.assertEqual(result.status, UNSAT, msg=str(clauses))
            else:
                self.assertEqual(result.status, SAT, msg=str(clauses))
                self.assertTrue(verify(clauses, result.model),
                                msg=str(clauses))


if __name__ == "__main__":
    unittest.main()

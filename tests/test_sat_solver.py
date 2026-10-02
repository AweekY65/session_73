"""Automated tests for the local DPLL SAT solver.

Run from the repository root:
    python3 -m unittest discover -s tests -v
"""

import itertools
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sat_solver import (  # noqa: E402
    DimacsError,
    SatSolver,
    normalize_clause,
    parse_dimacs,
    verify_model,
)


def dimacs(num_vars, clauses):
    lines = [f"p cnf {num_vars} {len(clauses)}"]
    lines += [" ".join(map(str, c)) + " 0" for c in clauses]
    lines.append("%")
    return "\n".join(lines) + "\n"


def brute_force_sat(num_vars, clauses):
    """Exhaustive oracle: evaluate the raw clauses on all 2^n assignments."""
    for values in itertools.product([False, True], repeat=num_vars):
        model = {v + 1: values[v] for v in range(num_vars)}
        if all(any(model[abs(l)] == (l > 0) for l in c) for c in clauses):
            return True, model
    return False, None


class TestDimacsParsing(unittest.TestCase):
    def test_valid_file_with_comments_and_multiline_clause(self):
        text = "c comment\np cnf 3 2\n1 2\n-3 0\n2 0\n%\n0\n"
        num_vars, clauses = parse_dimacs(text)
        self.assertEqual(num_vars, 3)
        self.assertEqual(clauses, [(1, 2, -3), (2,)])

    def test_empty_formula(self):
        num_vars, clauses = parse_dimacs("p cnf 4 0\n%\n")
        self.assertEqual(num_vars, 4)
        self.assertEqual(clauses, [])

    def test_missing_header(self):
        with self.assertRaises(DimacsError):
            parse_dimacs("1 0\n%\n")

    def test_malformed_header(self):
        with self.assertRaises(DimacsError):
            parse_dimacs("p cnf 3\n1 0\n%\n")

    def test_duplicate_header(self):
        with self.assertRaises(DimacsError):
            parse_dimacs("p cnf 1 0\np cnf 1 0\n%\n")

    def test_literal_out_of_range(self):
        with self.assertRaises(DimacsError):
            parse_dimacs("p cnf 2 1\n3 0\n%\n")

    def test_clause_count_mismatch(self):
        with self.assertRaises(DimacsError):
            parse_dimacs("p cnf 2 2\n1 0\n%\n")

    def test_missing_end_marker(self):
        with self.assertRaises(DimacsError):
            parse_dimacs("p cnf 1 1\n1 0\n")

    def test_content_after_end_marker(self):
        with self.assertRaises(DimacsError):
            parse_dimacs("p cnf 1 1\n1 0\n%\n1 0\n")

    def test_unterminated_clause(self):
        with self.assertRaises(DimacsError):
            parse_dimacs("p cnf 2 1\n1 2\n%\n")

    def test_invalid_token(self):
        with self.assertRaises(DimacsError):
            parse_dimacs("p cnf 2 1\n1 x 0\n%\n")


class TestClauseSemantics(unittest.TestCase):
    def test_duplicate_literals_removed(self):
        self.assertEqual(normalize_clause([2, 1, 2, -3, 1]), (1, 2, -3))

    def test_tautology_returns_none(self):
        self.assertIsNone(normalize_clause([1, -1, 5]))

    def test_empty_clause_preserved(self):
        self.assertEqual(normalize_clause([]), ())

    def test_tautology_clause_dropped_by_parser(self):
        num_vars, clauses = parse_dimacs("p cnf 2 2\n1 -1 0\n2 0\n%\n")
        self.assertEqual(clauses, [(2,)])

    def test_empty_formula_is_sat(self):
        result = SatSolver(3, []).solve()
        self.assertTrue(result.sat)
        self.assertEqual(set(result.model), {1, 2, 3})

    def test_empty_clause_is_unsat(self):
        result = SatSolver(2, [()]).solve()
        self.assertFalse(result.sat)
        self.assertIsNone(result.model)


class TestDPLL(unittest.TestCase):
    def solve_dimacs(self, text):
        num_vars, clauses = parse_dimacs(text)
        return num_vars, clauses, SatSolver(num_vars, clauses).solve()

    def test_simple_sat_with_verified_model(self):
        num_vars, clauses, result = self.solve_dimacs(
            dimacs(3, [[1, 2], [-1, 3], [-2, -3]])
        )
        self.assertTrue(result.sat)
        self.assertTrue(verify_model(num_vars, clauses, result.model))

    def test_simple_unsat(self):
        _, _, result = self.solve_dimacs(dimacs(1, [[1], [-1]]))
        self.assertFalse(result.sat)

    def test_unit_propagation_only_no_decisions(self):
        # (x1) & (!x1 | x2) & (!x2 | x3): solved by propagation alone.
        num_vars, clauses, result = self.solve_dimacs(
            dimacs(3, [[1], [-1, 2], [-2, 3]])
        )
        self.assertTrue(result.sat)
        self.assertEqual(result.stats.decisions, 0)
        self.assertGreaterEqual(result.stats.propagations, 3)
        self.assertEqual(result.model, {1: True, 2: True, 3: True})
        self.assertTrue(verify_model(num_vars, clauses, result.model))

    def test_pure_literal_elimination(self):
        # No unit clauses; x1 occurs only positively -> pure literal step.
        num_vars, clauses, result = self.solve_dimacs(
            dimacs(2, [[1, 2], [1, -2]])
        )
        self.assertTrue(result.sat)
        self.assertGreaterEqual(result.stats.pure_literals, 1)
        self.assertTrue(verify_model(num_vars, clauses, result.model))

    def test_deep_backtracking_pigeonhole(self):
        # PHP(4 pigeons, 3 holes) is UNSAT and forces real search.
        pigeons, holes = 4, 3
        var = lambda p, h: (p - 1) * holes + h  # noqa: E731
        clauses = [[var(p, h) for h in range(1, holes + 1)]
                   for p in range(1, pigeons + 1)]
        for h in range(1, holes + 1):
            for p1 in range(1, pigeons + 1):
                for p2 in range(p1 + 1, pigeons + 1):
                    clauses.append([-var(p1, h), -var(p2, h)])
        num_vars = pigeons * holes
        result = SatSolver(num_vars, clauses).solve()
        self.assertFalse(result.sat)
        self.assertGreater(result.stats.decisions, 0)
        self.assertGreater(result.stats.backtracks, 0)

    def test_backtracking_finds_sat_after_failed_branch(self):
        # x1=True conflicts, so the search must backtrack to x1=False.
        num_vars, clauses, result = self.solve_dimacs(
            dimacs(2, [[1, 2], [-1, 2], [-1, -2]])
        )
        self.assertTrue(result.sat)
        self.assertTrue(verify_model(num_vars, clauses, result.model))
        self.assertGreaterEqual(result.stats.backtracks, 1)

    def test_complete_model_extension(self):
        # x2 never appears: model must still assign it (don't-care -> False).
        num_vars, clauses, result = self.solve_dimacs(dimacs(2, [[1]]))
        self.assertTrue(result.sat)
        self.assertEqual(set(result.model), {1, 2})
        self.assertTrue(verify_model(num_vars, clauses, result.model))

    def test_verify_model_rejects_bad_model(self):
        self.assertFalse(verify_model(2, [[1]], {1: False, 2: False}))
        self.assertFalse(verify_model(2, [[1]], {1: True}))  # incomplete


class TestRandomAgainstOracle(unittest.TestCase):
    def test_random_small_formulas_match_exhaustive_search(self):
        rng = random.Random(20261002)
        for trial in range(400):
            num_vars = rng.randint(1, 5)
            num_clauses = rng.randint(0, 14)
            clauses = []
            for _ in range(num_clauses):
                size = rng.randint(0, 3)  # size 0 -> empty clause
                clause = [rng.choice([-1, 1]) * rng.randint(1, num_vars)
                          for _ in range(size)]
                clauses.append(clause)
            expected_sat, _ = brute_force_sat(num_vars, clauses)
            result = SatSolver(num_vars, clauses).solve()
            self.assertEqual(
                result.sat, expected_sat,
                f"trial {trial}: vars={num_vars} clauses={clauses}",
            )
            if result.sat:
                self.assertTrue(verify_model(num_vars, clauses, result.model))

    def test_random_dimacs_roundtrip(self):
        rng = random.Random(7)
        for _ in range(100):
            num_vars = rng.randint(1, 4)
            clauses = [[rng.choice([-1, 1]) * rng.randint(1, num_vars)
                        for _ in range(rng.randint(1, 3))]
                       for _ in range(rng.randint(0, 8))]
            parsed_vars, parsed_clauses = parse_dimacs(dimacs(num_vars, clauses))
            self.assertEqual(parsed_vars, num_vars)
            expected_sat, _ = brute_force_sat(num_vars, clauses)
            result = SatSolver(parsed_vars, parsed_clauses).solve()
            self.assertEqual(result.sat, expected_sat)


if __name__ == "__main__":
    unittest.main()

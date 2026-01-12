"""Tests for constraint optimizer."""

from satisfactory_planner.core.constraint_optimizer import (
    ConstraintSystem,
    ConstraintType,
    LinearConstraint,
)


class TestLinearConstraint:
    """Tests for LinearConstraint."""

    def test_is_simple_equality_positive(self) -> None:
        """Test detecting x_i = x_j."""
        # x_0 - x_1 = 0  means x_0 = x_1
        c = LinearConstraint(ConstraintType.EQUALITY, {0: 1.0, 1: -1.0}, 0.0)
        result = c.is_simple_equality()
        assert result == (0, 1)

    def test_is_simple_equality_negative(self) -> None:
        """Test detecting -x_i + x_j = 0."""
        # -x_0 + x_1 = 0  means x_1 = x_0
        c = LinearConstraint(ConstraintType.EQUALITY, {0: -1.0, 1: 1.0}, 0.0)
        result = c.is_simple_equality()
        assert result == (1, 0)

    def test_is_simple_equality_not_equality(self) -> None:
        """Test that inequality is not simple equality."""
        c = LinearConstraint(ConstraintType.LESS_EQUAL, {0: 1.0, 1: -1.0}, 0.0)
        assert c.is_simple_equality() is None

    def test_is_simple_equality_nonzero_rhs(self) -> None:
        """Test that nonzero rhs is not simple equality."""
        c = LinearConstraint(ConstraintType.EQUALITY, {0: 1.0, 1: -1.0}, 5.0)
        assert c.is_simple_equality() is None

    def test_is_upper_bound_positive(self) -> None:
        """Test detecting x_i <= K."""
        c = LinearConstraint(ConstraintType.LESS_EQUAL, {3: 1.0}, 100.0)
        result = c.is_upper_bound()
        assert result == (3, 100.0)

    def test_is_upper_bound_multiple_vars(self) -> None:
        """Test that multi-var constraint is not upper bound."""
        c = LinearConstraint(ConstraintType.LESS_EQUAL, {0: 1.0, 1: 1.0}, 100.0)
        assert c.is_upper_bound() is None

    def test_substitute(self) -> None:
        """Test variable substitution."""
        c = LinearConstraint(ConstraintType.EQUALITY, {0: 1.0, 1: -1.0, 2: 2.0}, 0.0)
        c.substitute(1, 3)
        assert c.coeffs == {0: 1.0, 3: -1.0, 2: 2.0}

    def test_substitute_merge(self) -> None:
        """Test substitution that merges coefficients."""
        c = LinearConstraint(ConstraintType.EQUALITY, {0: 1.0, 1: 2.0}, 0.0)
        c.substitute(1, 0)  # Replace x_1 with x_0
        assert c.coeffs == {0: 3.0}

    def test_substitute_cancellation(self) -> None:
        """Test substitution that cancels coefficients."""
        c = LinearConstraint(ConstraintType.EQUALITY, {0: 1.0, 1: -1.0}, 0.0)
        c.substitute(1, 0)  # Replace x_1 with x_0
        assert c.coeffs == {}  # 1*x_0 + (-1)*x_0 = 0


class TestConstraintSystem:
    """Tests for ConstraintSystem optimization."""

    def test_simple_chain_collapse(self) -> None:
        """Test that x_0 = x_1, x_1 = x_2 collapses to one variable."""
        cs = ConstraintSystem(n_vars=3)
        cs.add_equality({0: 1.0, 1: -1.0}, 0.0)  # x_0 = x_1
        cs.add_equality({1: 1.0, 2: -1.0}, 0.0)  # x_1 = x_2
        cs.add_inequality({2: 1.0}, 100.0)  # x_2 <= 100
        cs.objective = [-1.0, -1.0, -1.0]

        cs.optimize()
        active_vars, eq, eq_rhs, ineq, ineq_rhs, obj = cs.get_reduced_system()

        # Should reduce to 1 variable with 1 upper bound
        assert len(active_vars) == 1
        assert len(eq) == 0  # Equalities are eliminated
        assert len(ineq) == 1  # One upper bound remains

    def test_bound_tightening(self) -> None:
        """Test that multiple bounds on same var keep tightest."""
        cs = ConstraintSystem(n_vars=1)
        cs.add_inequality({0: 1.0}, 100.0)  # x_0 <= 100
        cs.add_inequality({0: 1.0}, 50.0)  # x_0 <= 50
        cs.add_inequality({0: 1.0}, 75.0)  # x_0 <= 75
        cs.objective = [-1.0]

        cs.optimize()
        active_vars, eq, eq_rhs, ineq, ineq_rhs, obj = cs.get_reduced_system()

        # Should have one bound at 50
        assert len(ineq) == 1
        assert ineq_rhs[0] == 50.0

    def test_expand_solution(self) -> None:
        """Test expanding reduced solution to original variables."""
        cs = ConstraintSystem(n_vars=3)
        cs.add_equality({0: 1.0, 1: -1.0}, 0.0)  # x_0 = x_1
        cs.add_equality({1: 1.0, 2: -1.0}, 0.0)  # x_1 = x_2
        cs.objective = [-1.0, -1.0, -1.0]

        cs.optimize()
        active_vars, _, _, _, _, _ = cs.get_reduced_system()

        # Solve reduced: all equal, say value is 42
        reduced_solution = [42.0]
        full_solution = cs.expand_solution(reduced_solution, active_vars)

        assert full_solution == [42.0, 42.0, 42.0]

    def test_preserves_complex_constraints(self) -> None:
        """Test that non-trivial constraints are preserved."""
        cs = ConstraintSystem(n_vars=3)
        # x_0 + x_1 = x_2 (merger/splitter conservation)
        cs.add_equality({0: 1.0, 1: 1.0, 2: -1.0}, 0.0)
        cs.add_inequality({0: 1.0}, 60.0)
        cs.add_inequality({1: 1.0}, 60.0)
        cs.objective = [-1.0, -1.0, -1.0]

        cs.optimize()
        active_vars, eq, eq_rhs, ineq, ineq_rhs, obj = cs.get_reduced_system()

        # All 3 vars should remain active
        assert len(active_vars) == 3
        # Conservation constraint preserved
        assert len(eq) == 1

    def test_trivial_constraint_removal(self) -> None:
        """Test that 0 <= K is removed."""
        cs = ConstraintSystem(n_vars=2)
        cs.add_equality({0: 1.0, 1: -1.0}, 0.0)  # x_0 = x_1
        cs.add_inequality({0: 1.0}, 100.0)
        cs.objective = [-1.0, -1.0]

        cs.optimize()

        # After substitution, one equality becomes trivial (0 = 0)
        # Count non-trivial constraints
        non_trivial = [c for c in cs.constraints if not c.is_trivial()]
        # Should just have the upper bound
        upper_bounds = [c for c in non_trivial if c.is_upper_bound()]
        assert len(upper_bounds) == 1

    def test_scaled_merge_removes_redundant(self) -> None:
        """Test that scaled equality becomes trivial after merge."""
        cs = ConstraintSystem(n_vars=2)
        # 30*a - 15*b = 0 means a = 0.5*b
        cs.add_equality({0: 30.0, 1: -15.0}, 0.0)
        cs.add_inequality({0: 1.0}, 50.0)  # a <= 50
        cs.add_inequality({1: 1.0}, 100.0)  # b <= 100
        cs.objective = [-1.0, -1.0]

        cs.optimize()
        active_vars, eq, eq_rhs, ineq, ineq_rhs, obj = cs.get_reduced_system()

        # Should reduce to 1 variable (b is canonical since index 1 > 0? no, 0 < 1 so 0 is canonical)
        # a = 0.5*b, so if a is canonical: b = 2*a
        # Bound a <= 50 stays, bound b <= 100 becomes 2*a <= 100 → a <= 50
        # So tightest is a <= 50
        assert len(active_vars) == 1
        assert len(eq) == 0  # Equality eliminated
        assert len(ineq) == 1  # One tightest bound

    def test_scaled_solution_expansion(self) -> None:
        """Test that solution correctly applies scale factors."""
        cs = ConstraintSystem(n_vars=2)
        # 2*a - 1*b = 0 means a = 0.5*b, or b = 2*a
        cs.add_equality({0: 2.0, 1: -1.0}, 0.0)
        cs.add_inequality({0: 1.0}, 30.0)  # a <= 30
        cs.objective = [-1.0, -1.0]

        cs.optimize()
        active_vars, _, _, _, _, _ = cs.get_reduced_system()

        # If canonical is 0 (a), then b = 2*a
        # Solve: a = 30 (at bound)
        reduced_solution = [30.0]
        full_solution = cs.expand_solution(reduced_solution, active_vars)

        # a = 30, b = 2*30 = 60
        assert full_solution[0] == 30.0
        assert full_solution[1] == 60.0

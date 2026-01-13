"""Tests for constraint optimizer."""

from satisfactory_planner.core.constraint_optimizer import (
    ConstraintSystem,
    ConstraintType,
    LinearConstraint,
)
from satisfactory_planner.core.linprog import RESOLUTION_SOLVED, LPResult, linsolve


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


class TestSourceTracking:
    """Tests for constraint source tracking through optimization."""

    def test_bound_source_tracked(self) -> None:
        """Source tag is preserved when adding an inequality."""
        cs: ConstraintSystem[str] = ConstraintSystem(n_vars=2)
        cs.add_inequality({0: 1.0}, 100.0, source="belt_capacity_edge1")
        cs.add_inequality({1: 1.0}, 50.0, source="demand_node2")

        cs.optimize()

        # Sources should be tracked for bounds
        assert cs.get_bound_source(0) == "belt_capacity_edge1"
        assert cs.get_bound_source(1) == "demand_node2"

    def test_tighter_bound_wins(self) -> None:
        """When multiple bounds exist, tightest one's source is kept."""
        cs: ConstraintSystem[str] = ConstraintSystem(n_vars=1)
        cs.objective = [-1.0]  # maximize x
        cs.add_inequality({0: 1.0}, 100.0, source="loose_bound")
        cs.add_inequality({0: 1.0}, 50.0, source="tight_bound")
        cs.add_inequality({0: 1.0}, 75.0, source="medium_bound")

        cs.optimize()

        # Tightest bound's source should win
        assert cs.get_bound_source(0) == "tight_bound"
        assert cs._upper_bounds[0] == 50.0

        # Verify solution is at tightest bound
        active_vars, eq_matrix, eq_rhs, ineq_matrix, ineq_rhs, objective = cs.get_reduced_system()
        result = linsolve(
            objective,
            ineq_left=ineq_matrix,
            ineq_right=ineq_rhs,
            eq_left=eq_matrix,
            eq_right=eq_rhs,
            nonneg_variables=list(range(len(active_vars))),
            return_duals=True,
        )
        assert isinstance(result, LPResult)
        assert result.resolution == RESOLUTION_SOLVED
        assert result.solution is not None
        assert result.solution[0] == 50.0

        # Only the tight bound should be binding
        binding = cs.get_binding_sources(result.solution, active_vars, result.ineq_duals or [])
        assert "tight_bound" in binding
        assert binding["tight_bound"] == 1.0

    def test_source_survives_variable_merge(self) -> None:
        """When variables are merged, bound sources are preserved on canonical."""
        cs: ConstraintSystem[str] = ConstraintSystem(n_vars=3)
        cs.objective = [-1.0, -1.0, -1.0]  # maximize all
        # x0 = x1 (equality merge)
        cs.add_equality({0: 1.0, 1: -1.0}, 0.0)
        # Bound on x1
        cs.add_inequality({1: 1.0}, 60.0, source="belt_on_x1")
        # Bound on x2 to make it interesting
        cs.add_inequality({2: 1.0}, 100.0, source="belt_on_x2")

        cs.optimize()

        # After merge, x0 is canonical (lower index)
        # The bound source should still be accessible via either variable
        assert cs.get_bound_source(0) == "belt_on_x1"
        assert cs.get_bound_source(1) == "belt_on_x1"
        assert cs.get_bound_source(2) == "belt_on_x2"

        # Verify solution: x0 = x1 = 60, x2 = 100
        active_vars, eq_matrix, eq_rhs, ineq_matrix, ineq_rhs, objective = cs.get_reduced_system()

        # Should have collapsed to 2 variables (x0/x1 merged, x2 separate)
        assert len(active_vars) == 2

        result = linsolve(
            objective,
            ineq_left=ineq_matrix,
            ineq_right=ineq_rhs,
            eq_left=eq_matrix,
            eq_right=eq_rhs,
            nonneg_variables=list(range(len(active_vars))),
            return_duals=True,
        )
        assert isinstance(result, LPResult)
        assert result.resolution == RESOLUTION_SOLVED
        assert result.solution is not None

        # Expand and verify
        full_solution = cs.expand_solution(result.solution, active_vars)
        assert full_solution[0] == 60.0  # x0 at merged bound
        assert full_solution[1] == 60.0  # x1 = x0
        assert full_solution[2] == 100.0  # x2 at its own bound

        # Both bounds should be binding
        binding = cs.get_binding_sources(result.solution, active_vars, result.ineq_duals or [])
        assert "belt_on_x1" in binding
        assert "belt_on_x2" in binding
        # x0 and x1 are merged, so objective is -2*x0 - x2
        # Relaxing x0's bound by 1 improves objective by 2, hence dual = 2
        assert binding["belt_on_x1"] == 2.0
        assert binding["belt_on_x2"] == 1.0

    def test_get_binding_sources_with_duals(self) -> None:
        """get_binding_sources returns sources for constraints with non-zero duals."""
        cs: ConstraintSystem[str] = ConstraintSystem(n_vars=2)
        cs.objective = [-1.0, -1.0]  # maximize x0 + x1 (via minimize -x0 - x1)
        cs.add_inequality({0: 1.0}, 100.0, source="bound_x0")
        cs.add_inequality({1: 1.0}, 50.0, source="bound_x1")

        cs.optimize()
        active_vars, eq_matrix, eq_rhs, ineq_matrix, ineq_rhs, objective = cs.get_reduced_system()

        # Solve with duals
        result = linsolve(
            objective,
            ineq_left=ineq_matrix,
            ineq_right=ineq_rhs,
            eq_left=eq_matrix,
            eq_right=eq_rhs,
            nonneg_variables=list(range(len(active_vars))),
            return_duals=True,
        )
        assert isinstance(result, LPResult)
        assert result.resolution == RESOLUTION_SOLVED
        assert result.ineq_duals is not None
        assert result.solution is not None

        # Solution should be at the bounds
        assert result.solution[0] == 100.0
        assert result.solution[1] == 50.0

        # Get binding sources
        binding = cs.get_binding_sources(result.solution, active_vars, result.ineq_duals)

        # Both bounds should be binding (maximizing pushes against bounds)
        assert "bound_x0" in binding
        assert "bound_x1" in binding
        # Duals should be positive: relaxing bound would decrease objective (help minimization)
        # For minimize -x0 - x1, if x0 bound goes from 100 to 101:
        #   new objective = -101 - 50 = -151, change = -1
        # So dual = 1 (objective decreases by 1 per unit of relaxation)
        assert binding["bound_x0"] == 1.0
        assert binding["bound_x1"] == 1.0

    def test_non_binding_constraint_not_in_sources(self) -> None:
        """Constraints that aren't binding don't appear in binding_sources."""
        cs: ConstraintSystem[str] = ConstraintSystem(n_vars=2)
        cs.objective = [-1.0, -1.0]  # maximize x0 + x1
        # x0 <= 100, but we'll also constrain x0 + x1 <= 80
        cs.add_inequality({0: 1.0}, 100.0, source="loose_bound")
        cs.add_inequality({1: 1.0}, 100.0, source="another_loose")
        cs.add_inequality({0: 1.0, 1: 1.0}, 80.0, source="tight_sum")

        cs.optimize()
        active_vars, eq_matrix, eq_rhs, ineq_matrix, ineq_rhs, objective = cs.get_reduced_system()

        result = linsolve(
            objective,
            ineq_left=ineq_matrix,
            ineq_right=ineq_rhs,
            eq_left=eq_matrix,
            eq_right=eq_rhs,
            nonneg_variables=list(range(len(active_vars))),
            return_duals=True,
        )
        assert isinstance(result, LPResult)
        assert result.resolution == RESOLUTION_SOLVED
        assert result.solution is not None

        # Solution: x0 + x1 = 80, optimum is x0=40, x1=40 (or any split)
        # The sum is 80, individual values are at most 80 (well under 100)
        full_solution = cs.expand_solution(result.solution, active_vars)
        assert abs(full_solution[0] + full_solution[1] - 80.0) < 0.01

        # The individual bounds (100) aren't binding - the sum constraint (80) is
        # But get_binding_sources only tracks single-variable bounds for now
        binding = cs.get_binding_sources(result.solution, active_vars, result.ineq_duals or [])

        # The loose bounds shouldn't be binding (they're at 100, solution is ~40 each)
        assert "loose_bound" not in binding
        assert "another_loose" not in binding

    def test_scaled_bound_source_tracked(self) -> None:
        """Scaled bounds (2*x <= 100) track source correctly."""
        cs: ConstraintSystem[str] = ConstraintSystem(n_vars=1)
        cs.objective = [-1.0]  # maximize x
        # 2*x <= 100 means x <= 50
        cs.add_inequality({0: 2.0}, 100.0, source="scaled_bound")

        cs.optimize()

        # Should normalize to x <= 50 and track source
        assert cs.get_bound_source(0) == "scaled_bound"
        assert cs._upper_bounds[0] == 50.0

        # Verify it solves correctly
        active_vars, eq_matrix, eq_rhs, ineq_matrix, ineq_rhs, objective = cs.get_reduced_system()
        result = linsolve(
            objective,
            ineq_left=ineq_matrix,
            ineq_right=ineq_rhs,
            eq_left=eq_matrix,
            eq_right=eq_rhs,
            nonneg_variables=list(range(len(active_vars))),
            return_duals=True,
        )
        assert isinstance(result, LPResult)
        assert result.resolution == RESOLUTION_SOLVED
        assert result.solution is not None

        # Solution should be x = 50 (at the effective bound)
        assert result.solution[0] == 50.0

        # The bound should be binding with positive dual
        binding = cs.get_binding_sources(result.solution, active_vars, result.ineq_duals or [])
        assert "scaled_bound" in binding
        assert binding["scaled_bound"] == 1.0


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

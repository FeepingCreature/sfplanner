"""Constraint optimizer for LP formulation.

Performs symbolic simplification of linear constraints before
passing to the simplex solver. This exploits the structure of
factory flow graphs where many constraints form simple chains
that can be collapsed.

The optimizer works on symbolic constraints, not on factory semantics.
All simplifications are valid LP transformations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto


class ConstraintType(Enum):
    """Type of constraint."""

    EQUALITY = auto()  # sum(coeffs[i] * vars[i]) = rhs
    LESS_EQUAL = auto()  # sum(coeffs[i] * vars[i]) <= rhs


@dataclass
class LinearConstraint:
    """A linear constraint over variables.

    Represents: sum(coeffs[var] * var for var in coeffs) <=/= rhs
    """

    constraint_type: ConstraintType
    coeffs: dict[int, float]  # var_index -> coefficient
    rhs: float

    def is_simple_equality(self) -> tuple[int, int] | None:
        """Check if this is x_i = x_j (coeffs 1, -1, rhs 0).

        Returns (i, j) if so, None otherwise.
        """
        if self.constraint_type != ConstraintType.EQUALITY:
            return None
        if abs(self.rhs) > 1e-9:
            return None
        if len(self.coeffs) != 2:
            return None

        items = list(self.coeffs.items())
        v1, c1 = items[0]
        v2, c2 = items[1]

        # Check for x_i - x_j = 0 pattern (or -x_i + x_j = 0)
        if abs(c1 + c2) < 1e-9 and abs(abs(c1) - 1.0) < 1e-9:
            if c1 > 0:
                return (v1, v2)  # v1 = v2
            else:
                return (v2, v1)  # v2 = v1

        return None

    def is_upper_bound(self) -> tuple[int, float] | None:
        """Check if this is x_i <= K.

        Returns (i, K) if so, None otherwise.
        """
        if self.constraint_type != ConstraintType.LESS_EQUAL:
            return None
        if len(self.coeffs) != 1:
            return None

        var, coeff = next(iter(self.coeffs.items()))
        if abs(coeff - 1.0) < 1e-9:
            return (var, self.rhs)

        return None

    def substitute(self, old_var: int, new_var: int) -> None:
        """Replace old_var with new_var in this constraint."""
        if old_var not in self.coeffs:
            return

        old_coeff = self.coeffs.pop(old_var)
        if new_var in self.coeffs:
            self.coeffs[new_var] += old_coeff
            # Clean up zero coefficients
            if abs(self.coeffs[new_var]) < 1e-9:
                del self.coeffs[new_var]
        else:
            self.coeffs[new_var] = old_coeff

    def is_trivial(self) -> bool:
        """Check if constraint is trivially satisfied (0 <= K where K >= 0)."""
        if not self.coeffs:
            if self.constraint_type == ConstraintType.LESS_EQUAL:
                return self.rhs >= -1e-9
            else:
                return abs(self.rhs) < 1e-9
        return False


@dataclass
class ConstraintSystem:
    """A system of linear constraints that can be optimized."""

    n_vars: int
    constraints: list[LinearConstraint] = field(default_factory=list)
    objective: list[float] = field(default_factory=list)  # coefficients for min

    # Optimization state
    _var_mapping: dict[int, int] = field(default_factory=dict)  # old -> canonical
    _upper_bounds: dict[int, float] = field(default_factory=dict)  # var -> tightest bound
    _eliminated_vars: set[int] = field(default_factory=set)

    def add_equality(self, coeffs: dict[int, float], rhs: float) -> None:
        """Add equality constraint: sum(coeffs[i] * x_i) = rhs."""
        self.constraints.append(LinearConstraint(ConstraintType.EQUALITY, coeffs.copy(), rhs))

    def add_inequality(self, coeffs: dict[int, float], rhs: float) -> None:
        """Add inequality constraint: sum(coeffs[i] * x_i) <= rhs."""
        self.constraints.append(LinearConstraint(ConstraintType.LESS_EQUAL, coeffs.copy(), rhs))

    def _find_canonical(self, var: int) -> int:
        """Find canonical representative for a variable (union-find with path compression)."""
        if var not in self._var_mapping:
            return var
        # Path compression
        root = var
        while root in self._var_mapping and self._var_mapping[root] != root:
            root = self._var_mapping[root]
        # Compress path
        current = var
        while current in self._var_mapping and self._var_mapping[current] != root:
            next_var = self._var_mapping[current]
            self._var_mapping[current] = root
            current = next_var
        return root

    def _merge_vars(self, var1: int, var2: int) -> None:
        """Merge two variables (they are equal)."""
        c1 = self._find_canonical(var1)
        c2 = self._find_canonical(var2)
        if c1 != c2:
            # Use lower index as canonical (arbitrary but consistent)
            if c1 < c2:
                self._var_mapping[c2] = c1
            else:
                self._var_mapping[c1] = c2

    def optimize(self) -> None:
        """Apply all simplification passes."""
        changed = True
        iterations = 0
        max_iterations = self.n_vars + 10  # Safety bound

        while changed and iterations < max_iterations:
            changed = False
            iterations += 1

            # Pass 1: Find and merge simple equalities (x_i = x_j)
            for constraint in self.constraints:
                eq = constraint.is_simple_equality()
                if eq:
                    v1, v2 = eq
                    c1 = self._find_canonical(v1)
                    c2 = self._find_canonical(v2)
                    if c1 != c2:
                        self._merge_vars(c1, c2)
                        changed = True

            # Pass 2: Substitute canonical variables into all constraints
            for constraint in self.constraints:
                new_coeffs: dict[int, float] = {}
                for var, coeff in list(constraint.coeffs.items()):
                    canonical = self._find_canonical(var)
                    if canonical in new_coeffs:
                        new_coeffs[canonical] += coeff
                    else:
                        new_coeffs[canonical] = coeff
                # Clean up zeros
                constraint.coeffs = {v: c for v, c in new_coeffs.items() if abs(c) > 1e-9}

            # Pass 3: Collect and tighten upper bounds
            for constraint in self.constraints:
                ub = constraint.is_upper_bound()
                if ub:
                    var, bound = ub
                    canonical = self._find_canonical(var)
                    if canonical not in self._upper_bounds:
                        self._upper_bounds[canonical] = bound
                    else:
                        self._upper_bounds[canonical] = min(self._upper_bounds[canonical], bound)

            # Pass 4: Remove trivial constraints
            self.constraints = [c for c in self.constraints if not c.is_trivial()]

            # Pass 5: Remove duplicate upper bounds (keep only tightest)
            seen_upper_bounds: set[int] = set()
            new_constraints: list[LinearConstraint] = []
            for constraint in self.constraints:
                ub = constraint.is_upper_bound()
                if ub:
                    var, bound = ub
                    canonical = self._find_canonical(var)
                    if canonical in seen_upper_bounds:
                        # Skip duplicate, we'll add the tight one later
                        changed = True
                        continue
                    if canonical in self._upper_bounds:
                        # Replace with tightest bound
                        if abs(bound - self._upper_bounds[canonical]) > 1e-9:
                            constraint.rhs = self._upper_bounds[canonical]
                            changed = True
                        seen_upper_bounds.add(canonical)
                new_constraints.append(constraint)
            self.constraints = new_constraints

            # Pass 6: Remove redundant simple equalities (already merged)
            new_constraints = []
            for constraint in self.constraints:
                eq = constraint.is_simple_equality()
                if eq:
                    v1, v2 = eq
                    c1 = self._find_canonical(v1)
                    c2 = self._find_canonical(v2)
                    if c1 == c2:
                        # Redundant: both sides are the same canonical var
                        changed = True
                        continue
                new_constraints.append(constraint)
            self.constraints = new_constraints

    def get_reduced_system(
        self,
    ) -> tuple[
        list[int], list[list[float]], list[float], list[list[float]], list[float], list[float]
    ]:
        """Get the reduced constraint system.

        Returns:
            (active_vars, eq_matrix, eq_rhs, ineq_matrix, ineq_rhs, objective)

        Where active_vars maps new indices to original variable indices.
        """
        # Find all active canonical variables
        active_canonical: set[int] = set()
        for constraint in self.constraints:
            for var in constraint.coeffs:
                active_canonical.add(self._find_canonical(var))

        # Also need variables from objective
        for i, coeff in enumerate(self.objective):
            if abs(coeff) > 1e-9:
                active_canonical.add(self._find_canonical(i))

        # Create mapping from canonical var to reduced index
        active_vars = sorted(active_canonical)
        canonical_to_reduced = {v: i for i, v in enumerate(active_vars)}
        n_reduced = len(active_vars)

        eq_matrix: list[list[float]] = []
        eq_rhs: list[float] = []
        ineq_matrix: list[list[float]] = []
        ineq_rhs: list[float] = []

        for constraint in self.constraints:
            row = [0.0] * n_reduced
            for var, coeff in constraint.coeffs.items():
                canonical = self._find_canonical(var)
                if canonical in canonical_to_reduced:
                    row[canonical_to_reduced[canonical]] += coeff

            if constraint.constraint_type == ConstraintType.EQUALITY:
                eq_matrix.append(row)
                eq_rhs.append(constraint.rhs)
            else:
                ineq_matrix.append(row)
                ineq_rhs.append(constraint.rhs)

        # Reduce objective
        reduced_objective = [0.0] * n_reduced
        for i, coeff in enumerate(self.objective):
            if abs(coeff) > 1e-9:
                canonical = self._find_canonical(i)
                if canonical in canonical_to_reduced:
                    reduced_objective[canonical_to_reduced[canonical]] += coeff

        return (active_vars, eq_matrix, eq_rhs, ineq_matrix, ineq_rhs, reduced_objective)

    def expand_solution(self, reduced_solution: list[float], active_vars: list[int]) -> list[float]:
        """Expand a reduced solution back to the original variable space."""
        # Build canonical -> value mapping
        canonical_to_value: dict[int, float] = {}
        for i, var in enumerate(active_vars):
            canonical_to_value[var] = reduced_solution[i]

        # Expand to all original variables
        solution = [0.0] * self.n_vars
        for i in range(self.n_vars):
            canonical = self._find_canonical(i)
            if canonical in canonical_to_value:
                solution[i] = canonical_to_value[canonical]

        return solution

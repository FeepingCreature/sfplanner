"""Constraint optimizer for LP formulation.

Performs symbolic simplification of linear constraints before
passing to the simplex solver. This exploits the structure of
factory flow graphs where many constraints form simple chains
that can be collapsed.

The optimizer works on symbolic constraints, not on factory semantics.
All simplifications are valid LP transformations.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum, auto

logger = logging.getLogger(__name__)


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

    def is_two_var_equality(self) -> tuple[int, float, int, float] | None:
        """Check if this is U*x_i + V*x_j = 0 (generalized ratio constraint).

        Returns (i, U, j, V) if so, None otherwise.
        This includes simple equalities as a special case.
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

        # Need opposite signs for a valid ratio (U*a = -V*b means a = (-V/U)*b)
        if c1 * c2 >= 0:
            return None  # Same sign means no valid substitution for non-negative vars

        return (v1, c1, v2, c2)

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
    _var_scale: dict[int, float] = field(default_factory=dict)  # var -> scale relative to canonical
    _upper_bounds: dict[int, float] = field(default_factory=dict)  # var -> tightest bound
    _eliminated_vars: set[int] = field(default_factory=set)

    def add_equality(self, coeffs: dict[int, float], rhs: float) -> None:
        """Add equality constraint: sum(coeffs[i] * x_i) = rhs."""
        self.constraints.append(LinearConstraint(ConstraintType.EQUALITY, coeffs.copy(), rhs))

    def add_inequality(self, coeffs: dict[int, float], rhs: float) -> None:
        """Add inequality constraint: sum(coeffs[i] * x_i) <= rhs."""
        self.constraints.append(LinearConstraint(ConstraintType.LESS_EQUAL, coeffs.copy(), rhs))

    def _find_canonical_and_scale(self, var: int) -> tuple[int, float]:
        """Find canonical representative and cumulative scale factor.

        Returns (canonical_var, scale) where var = scale * canonical_var.
        """
        if var not in self._var_mapping:
            return var, 1.0

        # Follow the chain, accumulating scale factors
        scale = 1.0
        current = var
        while current in self._var_mapping:
            scale *= self._var_scale.get(current, 1.0)
            current = self._var_mapping[current]

        # Path compression: point directly to root with accumulated scale
        if var != current:
            self._var_mapping[var] = current
            self._var_scale[var] = scale

        return current, scale

    def _find_canonical(self, var: int) -> int:
        """Find canonical representative for a variable."""
        canonical, _ = self._find_canonical_and_scale(var)
        return canonical

    def _merge_vars(self, var1: int, var2: int, scale: float = 1.0) -> None:
        """Merge two variables with optional scale factor.

        After merge: var1 = scale * var2 (if var2 becomes canonical)
        or equivalently: var2 = (1/scale) * var1 (if var1 becomes canonical)
        """
        c1, s1 = self._find_canonical_and_scale(var1)
        c2, s2 = self._find_canonical_and_scale(var2)
        if c1 != c2:
            # effective relationship: s1 * c1 = scale * s2 * c2
            # so c1 = (scale * s2 / s1) * c2
            # Use lower index as canonical (arbitrary but consistent)
            if c1 < c2:
                # c2 maps to c1: c2 = (s1 / (scale * s2)) * c1
                self._var_mapping[c2] = c1
                self._var_scale[c2] = s1 / (scale * s2)
            else:
                # c1 maps to c2: c1 = (scale * s2 / s1) * c2
                self._var_mapping[c1] = c2
                self._var_scale[c1] = (scale * s2) / s1

    def optimize(self) -> None:
        """Apply all simplification passes."""
        initial_constraints = len(self.constraints)

        changed = True
        iterations = 0
        max_iterations = self.n_vars + 10  # Safety bound

        merges = 0
        bounds_tightened = 0
        trivial_removed = 0
        duplicates_removed = 0
        redundant_eq_removed = 0

        while changed and iterations < max_iterations:
            changed = False
            iterations += 1

            # Pass 1: Find and merge two-variable equalities (U*x_i + V*x_j = 0)
            for constraint in self.constraints:
                ratio = constraint.is_two_var_equality()
                if ratio:
                    v1, c1_coeff, v2, c2_coeff = ratio
                    canon1 = self._find_canonical(v1)
                    canon2 = self._find_canonical(v2)
                    if canon1 != canon2:
                        # U*v1 + V*v2 = 0 means v1 = (-V/U) * v2
                        # scale = -c2_coeff / c1_coeff
                        scale = -c2_coeff / c1_coeff
                        self._merge_vars(v1, v2, scale)
                        merges += 1
                        changed = True

            # Pass 2: Substitute canonical variables into all constraints (with scaling)
            for constraint in self.constraints:
                new_coeffs: dict[int, float] = {}
                for var, coeff in list(constraint.coeffs.items()):
                    canonical, scale = self._find_canonical_and_scale(var)
                    # var = scale * canonical, so coeff * var = coeff * scale * canonical
                    scaled_coeff = coeff * scale
                    if canonical in new_coeffs:
                        new_coeffs[canonical] += scaled_coeff
                    else:
                        new_coeffs[canonical] = scaled_coeff
                # Clean up zeros
                constraint.coeffs = {v: c for v, c in new_coeffs.items() if abs(c) > 1e-9}

            # Pass 3: Collect and tighten upper bounds (including scaled bounds)
            for constraint in self.constraints:
                # Check for simple upper bound first
                ub = constraint.is_upper_bound()
                if ub:
                    var, bound = ub
                    canonical = self._find_canonical(var)
                    if canonical not in self._upper_bounds:
                        self._upper_bounds[canonical] = bound
                    else:
                        old_bound = self._upper_bounds[canonical]
                        self._upper_bounds[canonical] = min(old_bound, bound)
                        if bound < old_bound:
                            bounds_tightened += 1
                # Also check for scaled upper bounds: coeff * x <= K means x <= K/coeff
                elif (
                    constraint.constraint_type == ConstraintType.LESS_EQUAL
                    and len(constraint.coeffs) == 1
                ):
                    var, coeff = next(iter(constraint.coeffs.items()))
                    if coeff > 1e-9:  # Positive coefficient
                        effective_bound = constraint.rhs / coeff
                        canonical = self._find_canonical(var)
                        if canonical not in self._upper_bounds:
                            self._upper_bounds[canonical] = effective_bound
                        else:
                            old_bound = self._upper_bounds[canonical]
                            if effective_bound < old_bound:
                                self._upper_bounds[canonical] = effective_bound
                                bounds_tightened += 1

            # Pass 4: Remove trivial constraints
            before_trivial = len(self.constraints)
            self.constraints = [c for c in self.constraints if not c.is_trivial()]
            trivial_removed += before_trivial - len(self.constraints)

            # Pass 5: Remove duplicate upper bounds (keep only tightest)
            # Also handles scaled bounds like 2*x <= 100 (equivalent to x <= 50)
            seen_upper_bounds: set[int] = set()
            new_constraints: list[LinearConstraint] = []
            for constraint in self.constraints:
                # Check if this is any kind of single-variable upper bound
                is_single_var_ub = (
                    constraint.constraint_type == ConstraintType.LESS_EQUAL
                    and len(constraint.coeffs) == 1
                )
                if is_single_var_ub:
                    var, coeff = next(iter(constraint.coeffs.items()))
                    if coeff > 1e-9:  # Positive coefficient
                        canonical = self._find_canonical(var)
                        if canonical in seen_upper_bounds:
                            duplicates_removed += 1
                            changed = True
                            continue
                        if canonical in self._upper_bounds:
                            # Normalize to coefficient 1 with tightest bound
                            constraint.coeffs[var] = 1.0
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
                        redundant_eq_removed += 1
                        changed = True
                        continue
                new_constraints.append(constraint)
            self.constraints = new_constraints

        # Log summary if any simplifications occurred
        final_constraints = len(self.constraints)
        active_canonical: set[int] = set()
        for constraint in self.constraints:
            for var in constraint.coeffs:
                active_canonical.add(self._find_canonical(var))
        final_vars = len(active_canonical)

        if merges > 0 or trivial_removed > 0 or duplicates_removed > 0:
            logger.info(
                f"Constraint optimizer: {self.n_vars} vars → {final_vars} vars, "
                f"{initial_constraints} constraints → {final_constraints} constraints "
                f"({iterations} iters)"
            )
            logger.debug(
                f"  Details: {merges} var merges, {bounds_tightened} bounds tightened, "
                f"{trivial_removed} trivial removed, {duplicates_removed} dup bounds removed, "
                f"{redundant_eq_removed} redundant eq removed"
            )

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

        # Expand to all original variables (applying scale factors)
        solution = [0.0] * self.n_vars
        for i in range(self.n_vars):
            canonical, scale = self._find_canonical_and_scale(i)
            if canonical in canonical_to_value:
                # i = scale * canonical, so value[i] = scale * value[canonical]
                solution[i] = scale * canonical_to_value[canonical]

        return solution

    def to_dot(self, var_names: list[str] | None = None) -> str:
        """Generate DOT graph of constraint relationships.

        Variables are nodes, constraints are hyperedges (shown as constraint nodes).
        """
        lines = [
            "digraph Constraints {",
            "  rankdir=LR;",
            '  node [fontname="Courier", fontsize=10];',
            "",
            "  // Variables",
        ]

        # Collect all active variables
        active_vars: set[int] = set()
        for constraint in self.constraints:
            for var in constraint.coeffs:
                active_vars.add(var)

        # Variable nodes
        for var in sorted(active_vars):
            name = var_names[var] if var_names and var < len(var_names) else f"x{var}"
            canonical = self._find_canonical(var)
            if canonical != var:
                # Show merged variables differently
                canon_name = (
                    var_names[canonical]
                    if var_names and canonical < len(var_names)
                    else f"x{canonical}"
                )
                lines.append(
                    f'  v{var} [label="{name}\\n(={canon_name})", '
                    f'style=filled, fillcolor="#FFCCCC"];'
                )
            else:
                # Check if has upper bound
                if var in self._upper_bounds:
                    bound = self._upper_bounds[var]
                    lines.append(
                        f'  v{var} [label="{name}\\n≤{bound:.0f}", '
                        f'style=filled, fillcolor="#CCFFCC"];'
                    )
                else:
                    lines.append(f'  v{var} [label="{name}"];')

        lines.append("")
        lines.append("  // Constraints")

        # Constraint nodes (hyperedges)
        for i, constraint in enumerate(self.constraints):
            if constraint.is_simple_equality() or constraint.is_upper_bound():
                # Skip simple ones - already shown on variable nodes
                continue

            # Complex constraint - show as a node
            if constraint.constraint_type == ConstraintType.EQUALITY:
                op = "="
                color = "#CCCCFF"
            else:
                op = "≤"
                color = "#FFFFCC"

            # Build constraint expression
            terms = []
            for var, coeff in sorted(constraint.coeffs.items()):
                name = var_names[var] if var_names and var < len(var_names) else f"x{var}"
                if coeff == 1.0:
                    terms.append(name)
                elif coeff == -1.0:
                    terms.append(f"-{name}")
                else:
                    terms.append(f"{coeff:.1f}*{name}")

            expr = " + ".join(terms).replace("+ -", "- ")
            label = f"{expr} {op} {constraint.rhs:.0f}"

            lines.append(f'  c{i} [label="{label}", shape=box, style=filled, fillcolor="{color}"];')

            # Edges from constraint to variables
            for var in constraint.coeffs:
                lines.append(f"  c{i} -> v{var} [arrowhead=none];")

        lines.append("}")
        return "\n".join(lines)

    def write_dot(self, path: str, var_names: list[str] | None = None) -> None:
        """Write constraint graph to DOT file."""
        from pathlib import Path

        Path(path).write_text(self.to_dot(var_names))
        logger.info(f"Wrote constraint graph to {path}")

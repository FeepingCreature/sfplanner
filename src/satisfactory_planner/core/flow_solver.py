"""Flow solver for validating factory production rates.

This orchestrates the flow simulation pipeline:
1. Build flow graph from document
2. Solve for steady-state flows using LP
3. Run warning detectors
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

from satisfactory_planner.core.item_key import ItemKey

if TYPE_CHECKING:
    from satisfactory_planner.core.flow_builder import FatalErrorType
    from satisfactory_planner.core.flow_lp_solver import SolvedModel
    from satisfactory_planner.core.flow_models import BuildingEfficiency
    from satisfactory_planner.core.models import Document, Recipe


class WarningType(Enum):
    """Types of validation warnings."""

    DISCONNECTED_BELT = "disconnected_belt"
    RESOURCE_UNDERFLOW = "resource_underflow"
    PRODUCTION_UNDERFLOW = "production_underflow"
    LEFTOVER_ITEMS = "leftover_items"
    BELT_OVERCAPACITY = "belt_overcapacity"
    ITEM_MISMATCH = "item_mismatch"
    RECIPE_NOT_SET = "recipe_not_set"


@dataclass
class Warning:
    """A validation warning."""

    type: WarningType
    message: str
    element_id: str  # ID of the element with the issue
    severity: float = 1.0  # 0.0-1.0, for sorting
    details: dict[str, object] | None = None
    caused_by: list[Warning] = field(default_factory=list)  # Causal chain


class FlowSolver:
    """Validates factory flows and generates warnings.

    Uses LP-based flow solving to compute steady-state flow rates,
    then runs detectors to find issues.
    """

    def __init__(self, document: Document, recipes: dict[str, Recipe] | None = None) -> None:
        self.document = document
        self._recipes = recipes
        self._solved_model: SolvedModel | None = None
        self._warnings: list[Warning] = []

    def solve(self) -> list[Warning]:
        """Analyze the factory and return warnings."""
        # Import here to avoid circular imports
        from satisfactory_planner.core.detectors import detect_all_warnings
        from satisfactory_planner.core.flow_builder import build_flow_graph
        from satisfactory_planner.core.flow_lp_solver import solve_flows
        from satisfactory_planner.core.persistence import load_all_recipes

        # Get recipes if not provided
        recipes = self._recipes
        if recipes is None:
            recipes = load_all_recipes()

        self._warnings = []

        # Step 1: Build flow graph
        build_result = build_flow_graph(self.document, recipes)

        if not build_result.success:
            # Convert fatal errors to warnings
            for error in build_result.errors:
                warning_type = self._fatal_error_to_warning_type(error.error_type)
                self._warnings.append(
                    Warning(
                        type=warning_type,
                        message=error.message,
                        element_id=error.element_id,
                        severity=1.0,
                    )
                )
            return self._warnings

        assert build_result.graph is not None

        # Step 2: Solve flows
        self._solved_model = solve_flows(build_result.graph)

        if not self._solved_model.success:
            self._warnings.append(
                Warning(
                    type=WarningType.DISCONNECTED_BELT,
                    message=self._solved_model.message,
                    element_id="",
                )
            )
            return self._warnings

        # Step 3: Detect warnings
        self._warnings = detect_all_warnings(self._solved_model)
        return self._warnings

    def _fatal_error_to_warning_type(self, error_type: FatalErrorType) -> WarningType:
        """Convert FatalErrorType to WarningType."""
        from satisfactory_planner.core.flow_builder import FatalErrorType

        mapping: dict[FatalErrorType, WarningType] = {
            FatalErrorType.DISCONNECTED_BELT: WarningType.DISCONNECTED_BELT,
            FatalErrorType.ITEM_MISMATCH: WarningType.ITEM_MISMATCH,
            FatalErrorType.MERGER_TYPE_CONFLICT: WarningType.ITEM_MISMATCH,
            FatalErrorType.RECIPE_NOT_SET: WarningType.RECIPE_NOT_SET,
            FatalErrorType.SOURCELESS_CYCLE: WarningType.DISCONNECTED_BELT,
        }
        return mapping.get(error_type, WarningType.DISCONNECTED_BELT)

    def get_flow_rate(self, key: ItemKey) -> float | None:
        """Get the calculated flow rate for a belt."""
        if self._solved_model is None:
            return None
        return self._solved_model.flows.get(key)

    def get_efficiency(self, key: ItemKey) -> BuildingEfficiency | None:
        """Get efficiency info for a building."""
        if self._solved_model is None:
            return None
        # Look up directly by ItemKey
        return self._solved_model.efficiencies.get(key)

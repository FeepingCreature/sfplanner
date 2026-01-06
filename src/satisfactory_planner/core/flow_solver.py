"""Flow solver for validating factory production rates."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from satisfactory_planner.core.models import Document


class WarningType(Enum):
    """Types of validation warnings."""

    DISCONNECTED_BELT = "disconnected_belt"
    RESOURCE_UNDERFLOW = "resource_underflow"
    PRODUCTION_UNDERFLOW = "production_underflow"
    LEFTOVER_ITEMS = "leftover_items"
    BELT_OVERCAPACITY = "belt_overcapacity"


@dataclass
class Warning:
    """A validation warning."""

    type: WarningType
    message: str
    element_id: str  # ID of the element with the issue
    details: dict[str, object] | None = None
    # TODO: Add causal chain tracking


class FlowSolver:
    """Validates factory flows and generates warnings."""

    def __init__(self, document: Document) -> None:
        self.document = document
        self.warnings: list[Warning] = []

    def solve(self) -> list[Warning]:
        """Analyze the factory and return warnings."""
        self.warnings = []

        self._check_disconnected_belts()
        self._check_belt_capacity()
        self._check_production_rates()

        return self.warnings

    def _check_disconnected_belts(self) -> None:
        """Check for belts with missing source or destination."""
        for belt in self.document.belts.values():
            if belt.source_building_id not in self.document.buildings:
                self.warnings.append(
                    Warning(
                        type=WarningType.DISCONNECTED_BELT,
                        message=f"Belt {belt.id} has no source building",
                        element_id=belt.id,
                    )
                )
            if belt.dest_building_id not in self.document.buildings:
                self.warnings.append(
                    Warning(
                        type=WarningType.DISCONNECTED_BELT,
                        message=f"Belt {belt.id} has no destination building",
                        element_id=belt.id,
                    )
                )

    def _check_belt_capacity(self) -> None:
        """Check for belts that are over capacity."""
        for belt in self.document.belts.values():
            # TODO: Calculate actual flow rate through belt
            # For now, just check if belt exists
            pass

    def _check_production_rates(self) -> None:
        """Check for production underflows."""
        # TODO: Implement full flow analysis
        # This requires propagating rates through the graph
        # and checking demand vs supply at each node
        pass

    def get_flow_rate(self, belt_id: str) -> float | None:
        """Get the calculated flow rate for a belt."""
        # TODO: Implement flow calculation
        belt = self.document.belts.get(belt_id)
        if not belt:
            return None
        # For now, return None to indicate unknown
        return None

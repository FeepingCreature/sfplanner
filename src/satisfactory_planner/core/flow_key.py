"""FlowKey: Unique identifier for buildings/belts in the flow graph.

A FlowKey identifies a specific instance of a building or belt. Since Rooms
can be placed multiple times (as RoomPlacements), the same building ID can
appear in multiple places. The FlowKey combines the placement context with
the element ID to create a unique identifier.

For top-level buildings (not in a room), placement_id is None.
For buildings inside a room placement, placement_id is the RoomPlacement.id.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FlowKey:
    """Unique identifier for a building or belt instance in flow analysis.

    Attributes:
        element_id: The Building.id or Belt.id
        placement_id: The RoomPlacement.id if inside a room, None for top-level
    """

    element_id: str
    placement_id: str | None = None

    def __str__(self) -> str:
        """String representation for debugging."""
        if self.placement_id:
            return f"FlowKey({self.placement_id}:{self.element_id})"
        return f"FlowKey({self.element_id})"

    def __repr__(self) -> str:
        """Repr for debugging."""
        return self.__str__()

"""Build FlowGraph from Document, with fatal error detection.

This module converts visual models (buildings, belts) into the flow graph
used for simulation. Fatal errors are detected during construction.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING

from satisfactory_planner.core.flow_models import (
    FlowEdge,
    FlowGraph,
    FlowNode,
    FlowPort,
    NodeType,
)
from satisfactory_planner.core.models import (
    BELT_CAPACITIES,
    Building,
    BuildingType,
    Scene,
)

if TYPE_CHECKING:
    from satisfactory_planner.core.models import Belt, Document, Recipe


class FatalErrorType(Enum):
    """Types of fatal errors that prevent model construction."""

    DISCONNECTED_BELT = auto()  # Belt missing source or dest
    ITEM_MISMATCH = auto()  # Belt connects incompatible item types
    MERGER_TYPE_CONFLICT = auto()  # Merger inputs have different item types
    RECIPE_NOT_SET = auto()  # Connected production building has no recipe
    SOURCELESS_CYCLE = auto()  # Loop with no external input


@dataclass
class FatalError:
    """A fatal error that prevents building the flow model."""

    error_type: FatalErrorType
    message: str
    element_id: str  # ID of the problematic element


@dataclass
class BuildResult:
    """Result of building a flow graph - either success or errors."""

    graph: FlowGraph | None = None
    errors: list[FatalError] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return self.graph is not None and len(self.errors) == 0


def _get_node_type(building_type: BuildingType) -> NodeType:
    """Map building type to flow node type."""
    if building_type in (BuildingType.MINER_MK1, BuildingType.MINER_MK2, BuildingType.MINER_MK3):
        return NodeType.MINER
    if building_type == BuildingType.SPLITTER:
        return NodeType.SPLITTER
    if building_type == BuildingType.MERGER:
        return NodeType.MERGER
    if building_type == BuildingType.PORT_IN:
        return NodeType.PORT_IN
    if building_type == BuildingType.PORT_OUT:
        return NodeType.PORT_OUT
    if building_type == BuildingType.SOURCE:
        return NodeType.MINER  # Sources act like miners (infinite supply)
    if building_type == BuildingType.SINK:
        return NodeType.SINK  # Sinks consume everything
    return NodeType.PRODUCER


def _get_port_item_id(
    building: Building, is_input: bool, port_index: int, recipes: dict[str, Recipe]
) -> str | None:
    """Get the item ID for a port based on recipe."""
    if building.recipe_id is None:
        return None

    recipe = recipes.get(building.recipe_id)
    if recipe is None:
        return None

    if is_input:
        if port_index < len(recipe.inputs):
            return recipe.inputs[port_index].item_id
    else:
        if port_index < len(recipe.outputs):
            return recipe.outputs[port_index].item_id

    return None


def _build_flow_ports(
    building: Building, recipes: dict[str, Recipe]
) -> tuple[list[FlowPort], list[FlowPort]]:
    """Build input and output FlowPorts for a building."""
    inputs: list[FlowPort] = []
    outputs: list[FlowPort] = []

    if building.recipe_id and building.recipe_id in recipes:
        recipe = recipes[building.recipe_id].scaled(building.clock_speed)
        for item_rate in recipe.inputs:
            inputs.append(FlowPort(item_id=item_rate.item_id, rate=item_rate.rate))
        for item_rate in recipe.outputs:
            outputs.append(FlowPort(item_id=item_rate.item_id, rate=item_rate.rate))
    elif building.building_type == BuildingType.SPLITTER:
        # Splitter: 1 input, 3 outputs (item type determined by connection)
        inputs.append(FlowPort(item_id=None, rate=0))
        for _ in range(3):
            outputs.append(FlowPort(item_id=None, rate=0))
    elif building.building_type == BuildingType.MERGER:
        # Merger: 3 inputs, 1 output (item type determined by connection)
        for _ in range(3):
            inputs.append(FlowPort(item_id=None, rate=0))
        outputs.append(FlowPort(item_id=None, rate=0))

    return inputs, outputs


def _is_production_building(building_type: BuildingType) -> bool:
    """Check if building type requires a recipe."""
    return building_type not in (
        BuildingType.SPLITTER,
        BuildingType.MERGER,
        BuildingType.MINER_MK1,
        BuildingType.MINER_MK2,
        BuildingType.MINER_MK3,
        BuildingType.PORT_IN,
        BuildingType.PORT_OUT,
        BuildingType.SOURCE,
        BuildingType.SINK,
    )


def _has_connections(building_id: str, belts: dict[str, Belt]) -> bool:
    """Check if a building has any belt connections."""
    for belt in belts.values():
        if belt.source_building_id == building_id or belt.dest_building_id == building_id:
            return True
    return False


def _find_logistics_loop(graph: FlowGraph) -> list[str] | None:
    """Find a pure logistics loop (splitters/mergers only, no producers).

    Returns the cycle as a list of node IDs, or None if no such loop exists.
    """
    logistics_types = {NodeType.SPLITTER, NodeType.MERGER}

    def dfs(node_id: str, path: list[str], visited: set[str]) -> list[str] | None:
        if node_id in path:
            cycle_start = path.index(node_id)
            return path[cycle_start:] + [node_id]

        node = graph.nodes.get(node_id)
        if node is None or node.node_type not in logistics_types:
            return None

        if node_id in visited:
            return None
        visited.add(node_id)

        path.append(node_id)
        for edge in graph.get_outgoing_edges(node_id):
            result = dfs(edge.dest_node_id, path, visited)
            if result:
                return result
        path.pop()
        return None

    visited: set[str] = set()
    for node_id, node in graph.nodes.items():
        if node.node_type in logistics_types and node_id not in visited:
            result = dfs(node_id, [], visited)
            if result:
                return result

    return None


def build_flow_graph(document: Document, recipes: dict[str, Recipe]) -> BuildResult:
    """Build a FlowGraph from a Document.

    Args:
        document: The document to build from
        recipes: Dict of recipe_id -> Recipe for looking up recipes

    Returns:
        BuildResult with either a valid graph or a list of fatal errors.
    """
    errors: list[FatalError] = []
    graph = FlowGraph()

    # Build from all scenes (document + rooms)
    _build_scene(document, recipes, graph, errors)

    # Also build from room contents (for room placements)
    for placement in document.room_placements.values():
        room = document.rooms.get(placement.room_id)
        if room:
            _build_scene(room, recipes, graph, errors)

    if errors:
        return BuildResult(errors=errors)

    # Phase: Check for pure logistics loops
    logistics_loop = _find_logistics_loop(graph)
    if logistics_loop:
        errors.append(
            FatalError(
                error_type=FatalErrorType.SOURCELESS_CYCLE,
                message=f"Pure logistics loop detected: {' -> '.join(logistics_loop)}",
                element_id=logistics_loop[0],
            )
        )

    # Phase: Check merger type conflicts
    for node in graph.nodes.values():
        if node.node_type == NodeType.MERGER:
            incoming_edges = graph.get_incoming_edges(node.id)
            item_ids = {e.item_id for e in incoming_edges if e.item_id is not None}
            if len(item_ids) > 1:
                errors.append(
                    FatalError(
                        error_type=FatalErrorType.MERGER_TYPE_CONFLICT,
                        message=f"Merger {node.id} has mixed item types: {item_ids}",
                        element_id=node.id,
                    )
                )

    if errors:
        return BuildResult(errors=errors)

    return BuildResult(graph=graph)


def _build_scene(
    scene: Scene,
    recipes: dict[str, Recipe],
    graph: FlowGraph,
    errors: list[FatalError],
) -> None:
    """Build flow graph nodes and edges from a scene (Document or Room)."""
    # Phase 1: Check for disconnected belts
    for belt_id, belt in scene.belts.items():
        if belt.source_building_id is None:
            errors.append(
                FatalError(
                    error_type=FatalErrorType.DISCONNECTED_BELT,
                    message=f"Belt {belt_id} has no source building",
                    element_id=belt_id,
                )
            )
        elif belt.source_building_id not in scene.buildings:
            errors.append(
                FatalError(
                    error_type=FatalErrorType.DISCONNECTED_BELT,
                    message=f"Belt {belt_id} source building not found",
                    element_id=belt_id,
                )
            )

        if belt.dest_building_id is None:
            errors.append(
                FatalError(
                    error_type=FatalErrorType.DISCONNECTED_BELT,
                    message=f"Belt {belt_id} has no destination building",
                    element_id=belt_id,
                )
            )
        elif belt.dest_building_id not in scene.buildings:
            errors.append(
                FatalError(
                    error_type=FatalErrorType.DISCONNECTED_BELT,
                    message=f"Belt {belt_id} destination building not found",
                    element_id=belt_id,
                )
            )

    # Phase 2: Check for missing recipes on connected production buildings
    for building_id, building in scene.buildings.items():
        if (
            _is_production_building(building.building_type)
            and _has_connections(building_id, scene.belts)
            and building.recipe_id is None
        ):
            errors.append(
                FatalError(
                    error_type=FatalErrorType.RECIPE_NOT_SET,
                    message=f"Building {building_id} ({building.building_type.value}) has no recipe",
                    element_id=building_id,
                )
            )

    if errors:
        return

    # Phase 3: Build nodes
    for building_id, building in scene.buildings.items():
        inputs, outputs = _build_flow_ports(building, recipes)
        node = FlowNode(
            id=building_id,
            node_type=_get_node_type(building.building_type),
            building_id=building_id,
            recipe_id=building.recipe_id,
            clock_speed=building.clock_speed,
            inputs=inputs,
            outputs=outputs,
        )
        graph.add_node(node)

    # Phase 4: Build edges and check item type compatibility
    for belt_id, belt in scene.belts.items():
        assert belt.source_building_id is not None
        assert belt.dest_building_id is not None

        source_building = scene.buildings[belt.source_building_id]
        dest_building = scene.buildings[belt.dest_building_id]

        source_item_id = _get_port_item_id(source_building, False, belt.source_port_index, recipes)
        dest_item_id = _get_port_item_id(dest_building, True, belt.dest_port_index, recipes)

        # Check item type mismatch (only if both are known)
        if (
            source_item_id is not None
            and dest_item_id is not None
            and source_item_id != dest_item_id
        ):
            errors.append(
                FatalError(
                    error_type=FatalErrorType.ITEM_MISMATCH,
                    message=f"Belt {belt_id} connects {source_item_id} to {dest_item_id}",
                    element_id=belt_id,
                )
            )
            continue

        # Determine the item type for this edge
        item_id = source_item_id or dest_item_id

        edge = FlowEdge(
            id=belt_id,
            belt_id=belt_id,
            source_node_id=belt.source_building_id,
            source_port_index=belt.source_port_index,
            dest_node_id=belt.dest_building_id,
            dest_port_index=belt.dest_port_index,
            capacity=BELT_CAPACITIES[belt.tier],
            item_id=item_id,
        )
        graph.add_edge(edge)

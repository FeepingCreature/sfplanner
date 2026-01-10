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
from satisfactory_planner.core.item_key import ItemKey
from satisfactory_planner.core.models import (
    BELT_CAPACITIES,
    MINER_RATES,
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
    if building_type == BuildingType.MINER:
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
    """Get the item ID for a port based on recipe or item_id field."""
    # Source/Sink/Miner use item_id field directly
    if building.building_type == BuildingType.SOURCE:
        if not is_input and port_index == 0:
            return building.item_id
        return None
    if building.building_type == BuildingType.SINK:
        if is_input and port_index == 0:
            return building.item_id
        return None
    if building.building_type == BuildingType.MINER:
        if not is_input and port_index == 0:
            return building.item_id
        return None

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

    # Source: single output using item_id field
    # Use max_rate if set, otherwise "infinite" (100000)
    if building.building_type == BuildingType.SOURCE:
        rate = building.max_rate if building.max_rate is not None else 100000.0
        outputs.append(FlowPort(item_id=building.item_id, rate=rate))
        return inputs, outputs

    # Sink: single input using item_id field
    # Use max_rate if set, otherwise "infinite" (100000)
    if building.building_type == BuildingType.SINK:
        rate = building.max_rate if building.max_rate is not None else 100000.0
        inputs.append(FlowPort(item_id=building.item_id, rate=rate))
        return inputs, outputs

    # Miner: single output with tier-based rate using item_id field
    if building.building_type == BuildingType.MINER:
        base_rate = MINER_RATES.get(building.tier, 60)
        rate = base_rate * building.clock_speed
        outputs.append(FlowPort(item_id=building.item_id, rate=rate))
        return inputs, outputs

    # PORT_IN/PORT_OUT: pass-through with 1 input and 1 output
    # Item type is determined by connected belts (like splitters/mergers)
    if building.building_type in (BuildingType.PORT_IN, BuildingType.PORT_OUT):
        inputs.append(FlowPort(item_id=None, rate=0))
        outputs.append(FlowPort(item_id=None, rate=0))
        return inputs, outputs

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
        BuildingType.MINER,
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


def _find_logistics_loop(graph: FlowGraph) -> list[ItemKey] | None:
    """Find a pure logistics loop (splitters/mergers only, no producers).

    Returns the cycle as a list of ItemKeys, or None if no such loop exists.
    """
    logistics_types = {NodeType.SPLITTER, NodeType.MERGER}

    def dfs(node_id: ItemKey, path: list[ItemKey], visited: set[ItemKey]) -> list[ItemKey] | None:
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

    visited: set[ItemKey] = set()
    for node_id, node in graph.nodes.items():
        if node.node_type in logistics_types and node_id not in visited:
            result = dfs(node_id, [], visited)
            if result:
                return result

    return None


def _resolve_belt_endpoint(
    document: Document,
    building_id: str,
    port_index: int,
    is_output: bool,
) -> tuple[str, int, str | None]:
    """Resolve a belt endpoint, translating RoomPlacement references to PORT buildings.

    When a belt connects to a RoomPlacement (room acting as a building), we need to
    find the corresponding PORT_IN or PORT_OUT building inside the room.

    Args:
        document: The document containing rooms and placements
        building_id: The building or room_placement ID
        port_index: The port index on the building/placement
        is_output: True if this is the source (output) side of a belt

    Returns:
        Tuple of (resolved_building_id, resolved_port_index, placement_id_or_none)
        The placement_id is returned so caller can create composite node IDs.
    """
    # Check if this is a room placement
    placement = document.room_placements.get(building_id)
    if placement is None:
        # It's a regular building, return as-is
        return (building_id, port_index, None)

    # It's a room placement - find the corresponding PORT building
    room = document.rooms.get(placement.room_id)
    if room is None:
        return (building_id, port_index, None)

    # For output side of belt (source), we connect to room's input port (PORT_IN)
    # For input side of belt (dest), we connect to room's output port (PORT_OUT)
    # This is because:
    #   - Belt going INTO room: source is outside, dest is room → connects to PORT_IN inside
    #   - Belt coming FROM room: source is room, dest is outside → connects to PORT_OUT inside
    port = room.get_port_by_index(port_index, is_output=is_output)
    if port is None:
        return (building_id, port_index, None)

    # Return the PORT building ID and the placement ID for composite key creation
    # The port_index on PORT buildings is always 0 (they have exactly one input or one output)
    return (port.id, 0, placement.id)


def build_flow_graph(document: Document, recipes: dict[str, Recipe]) -> BuildResult:
    """Build a FlowGraph from a Document.

    Args:
        document: The document to build from
        recipes: Dict of recipe_id -> Recipe for looking up recipes

    Returns:
        BuildResult with either a valid graph or a list of fatal errors.

    Node IDs use composite keys for buildings inside room placements:
    - Top-level buildings: just building_id
    - Buildings in rooms: placement_id:building_id

    This allows the same Room to be placed multiple times with separate
    flow analysis for each placement.
    """
    errors: list[FatalError] = []
    graph = FlowGraph()

    # Build from all scenes (document + rooms)
    _build_scene(document, document, recipes, graph, errors, placement_id=None)

    # Also build from room contents (for room placements)
    # Each placement gets its own set of nodes with composite IDs
    for placement in document.room_placements.values():
        room = document.rooms.get(placement.room_id)
        if room:
            _build_scene(room, document, recipes, graph, errors, placement_id=placement.id)

    if errors:
        return BuildResult(errors=errors)

    # Phase: Check for pure logistics loops
    logistics_loop = _find_logistics_loop(graph)
    if logistics_loop:
        loop_str = " -> ".join(str(k) for k in logistics_loop)
        errors.append(
            FatalError(
                error_type=FatalErrorType.SOURCELESS_CYCLE,
                message=f"Pure logistics loop detected: {loop_str}",
                element_id=logistics_loop[0].element_id,
            )
        )

    # Phase: Check merger type conflicts
    for node in graph.nodes.values():
        if node.node_type == NodeType.MERGER:
            incoming_edges = graph.get_incoming_edges(node.id)
            item_ids = {e.item_id for e in incoming_edges if e.item_id is not None}
            if len(item_ids) > 1:
                # Build detailed message showing which belts bring which items
                details = []
                for edge in incoming_edges:
                    if edge.item_id:
                        details.append(f"  • Input {edge.dest_port_index}: {edge.item_id}")
                detail_str = "\n".join(details)
                errors.append(
                    FatalError(
                        error_type=FatalErrorType.MERGER_TYPE_CONFLICT,
                        message=f"Merger receives different item types:\n{detail_str}",
                        element_id=node.id.element_id,
                    )
                )

    if errors:
        return BuildResult(errors=errors)

    # Phase: Propagate item types through splitters/mergers
    _propagate_item_types(graph)

    return BuildResult(graph=graph)


def _propagate_item_types(graph: FlowGraph) -> None:
    """Propagate item types through splitters and mergers.

    Splitters/mergers don't have recipes, so their port item types
    must be inferred from connected edges. We also propagate item types
    along edges to handle chains of logistics nodes.

    Convergence: Each iteration must make progress (set at least one item_id).
    With N logistics nodes, we converge in at most N iterations.
    """
    # Count logistics nodes for convergence check (includes PORT_IN/PORT_OUT)
    logistics_types = (NodeType.SPLITTER, NodeType.MERGER, NodeType.PORT_IN, NodeType.PORT_OUT)
    logistics_count = sum(1 for n in graph.nodes.values() if n.node_type in logistics_types)

    # Iterate until no more changes
    changed = True
    iteration = 0

    while changed:
        changed = False
        iteration += 1

        # Safety check: should never exceed logistics node count
        if iteration > logistics_count + 1:
            # This indicates a bug in the algorithm, not user error
            raise RuntimeError(
                f"Item type propagation failed to converge after {iteration} iterations. "
                f"This is a bug - please report it."
            )

        # Step 1: Propagate item types along edges from known nodes
        for edge in graph.edges.values():
            if edge.item_id is not None:
                continue  # Already has item type

            # Check if source node knows its output item type
            source_node = graph.nodes.get(edge.source_node_id)
            if source_node and edge.source_port_index < len(source_node.outputs):
                source_item = source_node.outputs[edge.source_port_index].item_id
                if source_item is not None:
                    edge.item_id = source_item
                    changed = True
                    continue

            # Check if dest node knows its input item type
            dest_node = graph.nodes.get(edge.dest_node_id)
            if dest_node and edge.dest_port_index < len(dest_node.inputs):
                dest_item = dest_node.inputs[edge.dest_port_index].item_id
                if dest_item is not None:
                    edge.item_id = dest_item
                    changed = True

        # Step 2: Update splitter/merger ports from connected edges
        for node in graph.nodes.values():
            if node.node_type == NodeType.SPLITTER:
                # Get item type from incoming edge
                incoming = graph.get_incoming_edges(node.id)
                item_id = None
                for edge in incoming:
                    if edge.item_id is not None:
                        item_id = edge.item_id
                        break

                # Also check outgoing edges
                if item_id is None:
                    outgoing = graph.get_outgoing_edges(node.id)
                    for edge in outgoing:
                        if edge.item_id is not None:
                            item_id = edge.item_id
                            break

                if item_id is not None:
                    # Update all ports with this item type
                    for port in node.inputs:
                        if port.item_id != item_id:
                            port.item_id = item_id
                            port.rate = 100000.0  # High capacity
                            changed = True
                    for port in node.outputs:
                        if port.item_id != item_id:
                            port.item_id = item_id
                            port.rate = 100000.0  # High capacity
                            changed = True

            elif node.node_type in (NodeType.MERGER, NodeType.PORT_IN, NodeType.PORT_OUT):
                # Get item type from any incoming edge that has one
                incoming = graph.get_incoming_edges(node.id)
                item_id = None
                for edge in incoming:
                    if edge.item_id is not None:
                        item_id = edge.item_id
                        break

                # Also check outgoing edge
                if item_id is None:
                    outgoing = graph.get_outgoing_edges(node.id)
                    for edge in outgoing:
                        if edge.item_id is not None:
                            item_id = edge.item_id
                            break

                if item_id is not None:
                    # Update all ports with this item type
                    for port in node.inputs:
                        if port.item_id != item_id:
                            port.item_id = item_id
                            port.rate = 100000.0  # High capacity
                            changed = True
                    for port in node.outputs:
                        if port.item_id != item_id:
                            port.item_id = item_id
                            port.rate = 100000.0  # High capacity
                            changed = True


def _make_item_key(element_id: str, placement_id: str | None) -> ItemKey:
    """Create a ItemKey for a building or belt."""
    return ItemKey(element_id=element_id, placement_id=placement_id)


def _build_scene(
    scene: Scene,
    document: Document,
    recipes: dict[str, Recipe],
    graph: FlowGraph,
    errors: list[FatalError],
    placement_id: str | None = None,
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
        else:
            # Check if source exists (as building or room placement)
            source_in_scene = belt.source_building_id in scene.buildings
            source_is_placement = hasattr(
                scene, "room_placements"
            ) and belt.source_building_id in getattr(scene, "room_placements", {})
            if not source_in_scene and not source_is_placement:
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
        else:
            # Check if dest exists (as building or room placement)
            dest_in_scene = belt.dest_building_id in scene.buildings
            dest_is_placement = hasattr(
                scene, "room_placements"
            ) and belt.dest_building_id in getattr(scene, "room_placements", {})
            if not dest_in_scene and not dest_is_placement:
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
        node_key = _make_item_key(building_id, placement_id)
        node = FlowNode(
            id=node_key,
            node_type=_get_node_type(building.building_type),
            building_id=node_key,
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

        # Resolve room placement references to PORT buildings
        # Returns (building_id, port_index, placement_id_if_room)
        source_building_id, source_port_idx, source_placement_id = _resolve_belt_endpoint(
            document, belt.source_building_id, belt.source_port_index, is_output=True
        )
        dest_building_id, dest_port_idx, dest_placement_id = _resolve_belt_endpoint(
            document, belt.dest_building_id, belt.dest_port_index, is_output=False
        )

        # Get the actual buildings (may be in rooms)
        source_building = document.find_building(source_building_id)
        dest_building = document.find_building(dest_building_id)

        if source_building is None or dest_building is None:
            # Already reported as disconnected belt error
            continue

        source_item_id = _get_port_item_id(source_building, False, source_port_idx, recipes)
        dest_item_id = _get_port_item_id(dest_building, True, dest_port_idx, recipes)

        # Check item type mismatch (only if both are known)
        if (
            source_item_id is not None
            and dest_item_id is not None
            and source_item_id != dest_item_id
        ):
            # Get building names for clearer message
            src_name = source_building.building_type.value
            dst_name = dest_building.building_type.value
            if source_building.recipe_id and source_building.recipe_id in recipes:
                src_name = recipes[source_building.recipe_id].name
            if dest_building.recipe_id and dest_building.recipe_id in recipes:
                dst_name = recipes[dest_building.recipe_id].name

            errors.append(
                FatalError(
                    error_type=FatalErrorType.ITEM_MISMATCH,
                    message=(
                        f"Item mismatch: {src_name} outputs {source_item_id}, "
                        f"but {dst_name} expects {dest_item_id}"
                    ),
                    element_id=belt_id,
                )
            )
            continue

        # Determine the item type for this edge
        item_id = source_item_id or dest_item_id

        # Use ItemKeys for buildings in room placements
        # For endpoints resolved to room PORTs, use the placement_id from resolution
        # For regular buildings in the current scene, use the scene's placement_id
        source_node_key = _make_item_key(
            source_building_id, source_placement_id if source_placement_id else placement_id
        )
        dest_node_key = _make_item_key(
            dest_building_id, dest_placement_id if dest_placement_id else placement_id
        )

        # Belt key uses the current scene's placement_id (belts belong to their scene)
        edge_belt_key = _make_item_key(belt_id, placement_id)

        edge = FlowEdge(
            id=edge_belt_key,
            belt_id=edge_belt_key,
            source_node_id=source_node_key,
            source_port_index=source_port_idx,
            dest_node_id=dest_node_key,
            dest_port_index=dest_port_idx,
            capacity=BELT_CAPACITIES[belt.tier],
            item_id=item_id,
        )
        graph.add_edge(edge)

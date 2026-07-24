"""Belt connection manager for the factory canvas."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QCursor, QPen
from PySide6.QtWidgets import QGraphicsItem, QGraphicsPathItem, QMenu

from satisfactory_planner.core import Belt, BuildingType, ItemId, Recipe
from satisfactory_planner.core.models import Building, generate_id
from satisfactory_planner.core.routing import Point, compute_belt_path
from satisfactory_planner.ui.commands import ConnectBeltCommand, PlaceBuildingCommand
from satisfactory_planner.ui.items.path_utils import belt_path_to_painter_path

if TYPE_CHECKING:
    from satisfactory_planner.core.flow_models import FlowNode
    from satisfactory_planner.ui.canvas.factory_canvas import FactoryCanvas
    from satisfactory_planner.ui.items.port_item import PortItem
    from satisfactory_planner.ui.items.room_port_item import RoomPortItem


@dataclass
class BuildingOption:
    """An option in the building picker menu."""

    building_type: BuildingType
    recipe: Recipe | None  # None for splitter/merger
    port_index: int  # Which port to connect to
    display_name: str  # "Constructor: Iron Plate" or "Splitter"
    item_id: ItemId | None = None  # For Source/Sink: the item to produce/consume


class BeltConnector:
    """Manages belt connection dragging and creation.

    Handles the drag preview, port hover highlighting, and connection completion.
    Supports both forward (from output) and backward (from input) dragging.
    """

    def __init__(self, canvas: FactoryCanvas) -> None:
        self.canvas = canvas
        self._is_connecting = False
        self._drag_forward = True  # True = from output, False = from input
        # The building/placement being dragged from, and the scene it lives in.
        # NOTE: the scene id is a Room id (scene context), NOT a RoomPlacement id -
        # don't confuse it with ItemKey.placement_id.
        self._connect_start_building_id: str | None = None
        self._connect_start_scene_room_id: str | None = None
        self._connect_start_port: int = 0
        self._drag_preview: QGraphicsPathItem | None = None
        self._drag_start_pos: QPointF | None = None
        self._drag_start_dir: float = 0
        self._hover_target_port: PortItem | RoomPortItem | None = None

    @property
    def is_connecting(self) -> bool:
        """Return whether a belt connection is in progress."""
        return self._is_connecting

    def start_drag(
        self,
        building_id: str,
        port_index: int,
        start_pos: QPointF,
        is_output: bool = True,
        scene_room_id: str | None = None,
    ) -> None:
        """Start dragging a belt connection from a port.

        Args:
            building_id: The building or room placement being dragged from
            port_index: Which port
            start_pos: Scene position to start drag from
            is_output: True if dragging from output (forward), False if from input (backward)
            scene_room_id: Room id of the scene the port lives in (None = document root)

        If the port already has a belt, delete it first (implicit replacement).
        """

        # Check if port is already connected - if so, delete existing belt
        existing_belt = self.canvas.document.get_belt_at_port(building_id, port_index, is_output)
        if existing_belt:
            from satisfactory_planner.ui.commands import DeleteItemsCommand

            cmd = DeleteItemsCommand(
                scene_room_id=None,
                buildings=(),
                belts=(existing_belt,),
                canvas=self.canvas,
            )
            self.canvas.command_stack.execute(cmd)

        self._is_connecting = True
        self._drag_forward = is_output
        self._connect_start_building_id = building_id
        self._connect_start_scene_room_id = scene_room_id
        self._connect_start_port = port_index
        self._drag_start_pos = start_pos
        self.canvas.setCursor(Qt.CursorShape.CrossCursor)

        # Get start direction from the source (building or room placement)
        building = self.canvas.document.buildings.get(building_id)
        if building:
            if is_output:
                self._drag_start_dir = building.output_port_direction(port_index)
            else:
                self._drag_start_dir = building.input_port_direction(port_index)
        else:
            # Check if it's a room placement
            placement = self.canvas.document.room_placements.get(building_id)
            if placement:
                if is_output:
                    self._drag_start_dir = placement.output_port_direction(
                        port_index, self.canvas.document
                    )
                else:
                    self._drag_start_dir = placement.input_port_direction(
                        port_index, self.canvas.document
                    )
            else:
                self._drag_start_dir = 0

        # Create preview path
        self._drag_preview = QGraphicsPathItem()
        self._drag_preview.setPen(QPen(QColor(100, 200, 100, 180), 3, Qt.PenStyle.DashLine))
        self._drag_preview.setZValue(1000)
        self._drag_preview.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self._drag_preview.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.canvas._scene.addItem(self._drag_preview)

    def update_preview(self, end_pos: QPointF) -> None:
        """Update the drag preview path to the given end position.

        If a port is currently auto-targeted (hovering over a compatible port
        or a building body that resolved to one via update_hover_target), the
        preview snaps to that port's exact position/direction instead of the
        raw cursor position, so the user can see which port will be used.
        """
        if not self._drag_preview or not self._drag_start_pos:
            return

        snapped = self._hover_target_port is not None
        if self._hover_target_port is not None:
            end_pos = self._hover_target_port.scenePos()
            end_dir = self._get_target_port_direction(self._hover_target_port)
        else:
            # Default end direction: toward end point
            dx = end_pos.x() - self._drag_start_pos.x()
            dy = end_pos.y() - self._drag_start_pos.y()
            end_dir = math.atan2(dy, dx)

        if self._drag_forward:
            # Forward: dragging from output to input
            # Belt goes from start (output) to end (cursor/input)
            start = Point(self._drag_start_pos.x(), self._drag_start_pos.y())
            end = Point(end_pos.x(), end_pos.y())
            start_dir = self._drag_start_dir
            belt_path = compute_belt_path(start, start_dir, end, end_dir)
            path = belt_path_to_painter_path(start, end, belt_path)
        else:
            # Backward: dragging from input to output
            # Belt goes from end (cursor/output) to start (input)
            # So we swap start/end for the path calculation
            start = Point(end_pos.x(), end_pos.y())
            end = Point(self._drag_start_pos.x(), self._drag_start_pos.y())
            # If snapped, end_dir already holds the real port's own
            # belt-facing direction (same convention as _drag_start_dir) -
            # use it directly. Otherwise the cursor has no real orientation,
            # so approximate the output's facing direction as pointing back
            # along the cursor ray.
            start_dir = end_dir if snapped else end_dir + math.pi
            end_dir = self._drag_start_dir
            belt_path = compute_belt_path(start, start_dir, end, end_dir)
            path = belt_path_to_painter_path(start, end, belt_path)

        self._drag_preview.setPath(path)

    def _get_target_port_direction(self, port: PortItem | RoomPortItem) -> float:
        """Get the belt-facing direction (radians) for a PortItem or RoomPortItem."""
        from satisfactory_planner.ui.items.port_item import PortItem as _PortItem

        if isinstance(port, _PortItem):
            return math.radians(port.angle)
        # RoomPortItem: derive direction from its building's port layout/rotation
        if port.is_output:
            return port.building.output_port_direction(port.port_index)
        return port.building.input_port_direction(port.port_index)

    def update_hover_target(self, scene_pos: QPointF) -> None:
        """Check if hovering over a valid target port and update highlight.

        When dragging forward (from output), look for input ports.
        When dragging backward (from input), look for output ports.

        If the cursor is over a leaf building's body (not a specific port,
        and not a Room), auto-resolve to that building's best free port of
        the correct direction and highlight/snap to it, matching what
        try_complete would pick.
        """
        from satisfactory_planner.ui.items.building_item import BuildingItem
        from satisfactory_planner.ui.items.port_item import PortItem
        from satisfactory_planner.ui.items.room_port_item import RoomPortItem

        # When dragging forward, we look for inputs; when backward, we look for outputs
        target_is_output = not self._drag_forward

        new_target: PortItem | RoomPortItem | None = None
        hit_building: BuildingItem | None = None
        for item in self.canvas._scene.items(scene_pos):
            # Check for building port
            if isinstance(item, PortItem) and item.is_output == target_is_output:
                new_target = item
                break
            # Check for room port
            if isinstance(item, RoomPortItem) and item.is_output == target_is_output:
                new_target = item
                break
            if (
                hit_building is None
                and isinstance(item, BuildingItem)
                and item.building.id != self._connect_start_building_id
            ):
                hit_building = item

        if new_target is None and hit_building is not None:
            best_index = self._find_best_port_on_building(
                hit_building.building.id, target_is_output
            )
            if best_index is not None:
                ports = (
                    hit_building._output_ports if target_is_output else hit_building._input_ports
                )
                if best_index < len(ports):
                    new_target = ports[best_index]

        if new_target != self._hover_target_port:
            if self._hover_target_port:
                self._hover_target_port.set_drag_target(False)
            if new_target:
                new_target.set_drag_target(True)
            self._hover_target_port = new_target

    def try_complete(self, scene_pos: QPointF) -> bool:
        """Try to complete the connection at the given position.

        Returns True if connection was completed or cancelled, False if still dragging.
        """
        if not self._is_connecting:
            return False

        from satisfactory_planner.ui.items.port_item import PortItem
        from satisfactory_planner.ui.items.room_port_item import RoomPortItem

        # When dragging forward, we look for inputs; when backward, we look for outputs
        target_is_output = not self._drag_forward

        # Find target port at position
        for item in self.canvas._scene.items(scene_pos):
            # Check for building port
            if isinstance(item, PortItem) and item.is_output == target_is_output:
                # Check if port already connected
                if self.canvas.document.is_port_connected(
                    item.building_id, item.port_index, target_is_output
                ):
                    self.cancel()
                    return True
                self.complete(item.building_id, item.port_index)
                return True
            # Check for room port
            if isinstance(item, RoomPortItem) and item.is_output == target_is_output:
                # Check if port already connected (using placement_id as building_id)
                if self.canvas.document.is_port_connected(
                    item.placement_id, item.port_index, target_is_output
                ):
                    self.cancel()
                    return True
                self.complete(item.placement_id, item.port_index)
                return True

        # No port hit directly - check if we dropped onto a leaf building's body.
        # (Rooms are excluded: they're not "visual objects" for belt-drop purposes.)
        from satisfactory_planner.ui.items.building_item import BuildingItem

        for item in self.canvas._scene.items(scene_pos):
            if isinstance(item, BuildingItem):
                if item.building.id == self._connect_start_building_id:
                    # Dragging a belt onto the same building it started from
                    # would feed an output back into its own input - never valid.
                    continue
                best_port = self._find_best_port_on_building(item.building.id, target_is_output)
                if best_port is not None:
                    self.complete(item.building.id, best_port)
                    return True
                break

        # No valid port - cancel
        self.cancel()
        return True

    def _find_best_port_on_building(self, building_id: str, target_is_output: bool) -> int | None:
        """Find the best (shortest-arrow) free port of the given direction on a building.

        Returns the port index, or None if no free port of that direction exists.
        """
        if not self._drag_start_pos:
            return None

        scene = self.canvas.document.find_building(building_id)
        building = scene
        if building is None:
            return None

        num_ports = building.num_outputs if target_is_output else building.num_inputs

        best_index: int | None = None
        best_length = float("inf")

        for idx in range(num_ports):
            if self.canvas.document.is_port_connected(building_id, idx, target_is_output):
                continue

            if target_is_output:
                port_pos = building.output_port_pos(idx)
                port_dir = building.output_port_direction(idx)
            else:
                port_pos = building.input_port_pos(idx)
                port_dir = building.input_port_direction(idx)

            length = self._compute_candidate_length(QPointF(*port_pos), port_dir)
            if length is not None and length < best_length:
                best_length = length
                best_index = idx

        return best_index

    def _compute_candidate_length(self, target_pos: QPointF, target_dir: float) -> float | None:
        """Compute the Dubins path length from the drag start to a candidate port.

        target_dir is the direction the belt travels when entering/leaving the
        candidate port (same convention as Building.input/output_port_direction).
        """
        if not self._drag_start_pos:
            return None

        if self._drag_forward:
            # Forward: belt goes from start (output) to target (input)
            start = Point(self._drag_start_pos.x(), self._drag_start_pos.y())
            end = Point(target_pos.x(), target_pos.y())
            belt_path = compute_belt_path(start, self._drag_start_dir, end, target_dir)
        else:
            # Backward: belt goes from target (output) to start (input)
            start = Point(target_pos.x(), target_pos.y())
            end = Point(self._drag_start_pos.x(), self._drag_start_pos.y())
            belt_path = compute_belt_path(start, target_dir, end, self._drag_start_dir)

        return belt_path.total_length if belt_path else None

    def complete(self, target_building_id: str, target_port_index: int) -> None:
        """Complete a belt connection to a target port.

        For forward drag: target is an input port (dest)
        For backward drag: target is an output port (source)
        """
        if self._is_connecting and self._connect_start_building_id:
            start_building_id = self._connect_start_building_id
            scene_room_id = self._connect_start_scene_room_id

            if self._drag_forward:
                # Forward: we started at output, connecting to input
                source_building_id = start_building_id
                source_port_index = self._connect_start_port
                dest_building_id = target_building_id
                dest_port_index = target_port_index
            else:
                # Backward: we started at input, connecting to output
                source_building_id = target_building_id
                source_port_index = target_port_index
                dest_building_id = start_building_id
                dest_port_index = self._connect_start_port

            belt = Belt(
                id=generate_id(),
                tier=self.canvas.default_belt_tier,
                source_building_id=source_building_id,
                source_port_index=source_port_index,
                dest_building_id=dest_building_id,
                dest_port_index=dest_port_index,
            )
            cmd = ConnectBeltCommand(scene_room_id=scene_room_id, belt=belt, canvas=self.canvas)
            self.canvas.command_stack.execute(cmd)

        self._cleanup()

    def cancel(self) -> None:
        """Cancel the current belt connection."""
        self._cleanup()

    def _cleanup(self) -> None:
        """Clean up drag state."""
        self._is_connecting = False
        self._drag_forward = True
        self._connect_start_building_id = None
        self._connect_start_scene_room_id = None
        self._drag_start_pos = None
        if self._drag_preview:
            self.canvas._scene.removeItem(self._drag_preview)
            self._drag_preview = None
        if self._hover_target_port:
            self._hover_target_port.set_drag_target(False)
            self._hover_target_port = None
        self.canvas.setCursor(Qt.CursorShape.ArrowCursor)

    # === Building Picker (right-click during drag) ===

    def show_building_picker(self, scene_pos: QPointF) -> None:
        """Show a dropdown menu of buildings that can connect to current drag.

        For forward drag: show buildings that consume the item being produced
        For backward drag: show buildings that produce items needed as input
        """
        if not self._is_connecting or not self._connect_start_building_id:
            self.cancel()
            return

        if self._drag_forward:
            options = self._get_forward_options()
        else:
            options = self._get_backward_options()

        if not options:
            self.cancel()
            return

        # Build menu
        menu = QMenu()

        # Separate options into categories
        logistics_options = [
            o for o in options if o.building_type in (BuildingType.SPLITTER, BuildingType.MERGER)
        ]
        source_sink_options = [
            o
            for o in options
            if o.building_type in (BuildingType.SOURCE, BuildingType.SINK, BuildingType.MINER)
        ]
        recipe_options = [o for o in options if o.recipe is not None]
        no_recipe_options = [
            o
            for o in options
            if o.recipe is None
            and o.building_type
            not in (
                BuildingType.SPLITTER,
                BuildingType.MERGER,
                BuildingType.SOURCE,
                BuildingType.SINK,
            )
        ]

        # Order: Splitter/Merger, separator, recipes, separator, no-recipe buildings, Source/Sink
        for option in logistics_options:
            action = menu.addAction(option.display_name)
            action.setData(option)

        if logistics_options and (recipe_options or no_recipe_options or source_sink_options):
            menu.addSeparator()

        for option in recipe_options:
            action = menu.addAction(option.display_name)
            action.setData(option)

        if recipe_options and (no_recipe_options or source_sink_options):
            menu.addSeparator()

        for option in no_recipe_options:
            action = menu.addAction(option.display_name)
            action.setData(option)

        for option in source_sink_options:
            action = menu.addAction(option.display_name)
            action.setData(option)

        # Show menu at cursor
        selected = menu.exec(QCursor.pos())
        if selected:
            option = selected.data()
            self._spawn_and_connect(option, scene_pos)
        else:
            self.cancel()

    def _get_forward_options(self) -> list[BuildingOption]:
        """Get building options for forward drag (from output).

        Uses flow solver to determine what item is on the output port.
        """
        options: list[BuildingOption] = []

        # Always offer splitter (1 input)
        options.append(
            BuildingOption(
                building_type=BuildingType.SPLITTER,
                recipe=None,
                port_index=0,
                display_name="Splitter",
            )
        )

        # Always offer merger (3 inputs - offer first available)
        options.append(
            BuildingOption(
                building_type=BuildingType.MERGER,
                recipe=None,
                port_index=0,
                display_name="Merger",
            )
        )

        # Try to get item from flow solver
        item_id = self._get_item_from_flow_solver()

        if item_id:
            # Find recipes that consume this item
            recipes = self.canvas.get_all_recipes()
            for recipe in recipes.values():
                for i, inp in enumerate(recipe.inputs):
                    if inp.item_id == item_id:
                        options.append(
                            BuildingOption(
                                building_type=recipe.building_type,
                                recipe=recipe,
                                port_index=i,
                                display_name=f"{recipe.building_type.value}: {recipe.name}",
                            )
                        )
                        break  # Only add each recipe once

            # Offer Sink for known item
            item_name = self._item_id_to_name(ItemId(item_id))
            options.append(
                BuildingOption(
                    building_type=BuildingType.SINK,
                    recipe=None,
                    port_index=0,
                    display_name=f"Sink: {item_name or item_id}",
                    item_id=ItemId(item_id),
                )
            )
        else:
            # No item known - offer all production buildings without recipes
            for bt in BuildingType:
                if bt in (
                    BuildingType.SMELTER,
                    BuildingType.FOUNDRY,
                    BuildingType.CONSTRUCTOR,
                    BuildingType.ASSEMBLER,
                    BuildingType.MANUFACTURER,
                    BuildingType.REFINERY,
                    BuildingType.PACKAGER,
                    BuildingType.BLENDER,
                ):
                    options.append(
                        BuildingOption(
                            building_type=bt,
                            recipe=None,
                            port_index=0,
                            display_name=f"{bt.value} (no recipe)",
                        )
                    )

            # Also offer Sink
            options.append(
                BuildingOption(
                    building_type=BuildingType.SINK,
                    recipe=None,
                    port_index=0,
                    display_name="Sink",
                )
            )

        return options

    def _get_backward_options(self) -> list[BuildingOption]:
        """Get building options for backward drag (from input).

        Checks the recipe of the source building to find needed inputs.
        For multi-input buildings, shows recipes for ALL unsatisfied inputs.
        """
        options: list[BuildingOption] = []

        # Always offer merger (1 output)
        options.append(
            BuildingOption(
                building_type=BuildingType.MERGER,
                recipe=None,
                port_index=0,
                display_name="Merger",
            )
        )

        # Always offer splitter (3 outputs - offer first available)
        options.append(
            BuildingOption(
                building_type=BuildingType.SPLITTER,
                recipe=None,
                port_index=0,
                display_name="Splitter",
            )
        )

        # Get the building we're dragging from
        if not self._connect_start_building_id:
            return options
        building = self.canvas.document.find_building(self._connect_start_building_id)
        if not building:
            return options

        # Get all items needed by the recipe (Satisfactory allows any port ordering)
        needed_item_ids = self._get_all_recipe_inputs(building)

        if needed_item_ids:
            # Find recipes that produce these items
            recipes = self.canvas.get_all_recipes()
            for recipe in recipes.values():
                for i, out in enumerate(recipe.outputs):
                    if out.item_id in needed_item_ids:
                        options.append(
                            BuildingOption(
                                building_type=recipe.building_type,
                                recipe=recipe,
                                port_index=i,
                                display_name=f"{recipe.building_type.value}: {recipe.name}",
                            )
                        )
                        break  # Only add each recipe once

            # Offer Source for each needed item (we can't know which port the belt is for)
            for needed_id in needed_item_ids:
                item_name = self._item_id_to_name(needed_id)
                options.append(
                    BuildingOption(
                        building_type=BuildingType.SOURCE,
                        recipe=None,
                        port_index=0,
                        display_name=f"Source: {item_name or needed_id}",
                        item_id=needed_id,
                    )
                )
                # Also offer a Miner if the needed item is a mineable raw resource
                if self._item_id_is_mineable(needed_id):
                    options.append(
                        BuildingOption(
                            building_type=BuildingType.MINER,
                            recipe=None,
                            port_index=0,
                            display_name=f"Miner: {item_name or needed_id}",
                            item_id=needed_id,
                        )
                    )
        else:
            # No recipe set - offer all production buildings without recipes
            for bt in BuildingType:
                if bt in (
                    BuildingType.SMELTER,
                    BuildingType.FOUNDRY,
                    BuildingType.CONSTRUCTOR,
                    BuildingType.ASSEMBLER,
                    BuildingType.MANUFACTURER,
                    BuildingType.REFINERY,
                    BuildingType.PACKAGER,
                    BuildingType.BLENDER,
                    BuildingType.MINER,
                ):
                    options.append(
                        BuildingOption(
                            building_type=bt,
                            recipe=None,
                            port_index=0,
                            display_name=f"{bt.value} (no recipe)",
                        )
                    )

            # Also offer Source
            options.append(
                BuildingOption(
                    building_type=BuildingType.SOURCE,
                    recipe=None,
                    port_index=0,
                    display_name="Source",
                )
            )

        return options

    def _get_all_recipe_inputs(self, building: Building) -> list[ItemId]:
        """Get all unique item IDs needed by a building's recipe that aren't already supplied.

        Satisfactory allows any belt ordering on inputs, so we return
        all items the recipe needs, not per-port items. We filter out
        items that already have incoming flow according to the flow solver.
        """
        if not building.recipe_id:
            return []

        recipe = self.canvas.get_recipe(building.recipe_id)
        if not recipe:
            return []

        # Get items already being supplied via flow solver
        already_supplied = self._get_supplied_items(building.id)

        # Return unique item IDs from all inputs, excluding already-supplied ones
        seen: set[ItemId] = set()
        result: list[ItemId] = []
        for inp in recipe.inputs:
            if inp.item_id not in seen and inp.item_id not in already_supplied:
                seen.add(inp.item_id)
                result.append(inp.item_id)
        return result

    def _get_supplied_items(self, building_id: str) -> set[ItemId]:
        """Get item IDs already being supplied to a building's inputs.

        Uses the flow solver graph to find incoming edges to this building's node.
        """
        supplied: set[ItemId] = set()

        flow_solver = self.canvas.flow_solver
        if not flow_solver or not flow_solver._solved_model:
            return supplied

        graph = flow_solver._solved_model.graph
        node = self._find_flow_node(building_id)
        if not node:
            return supplied

        # Check incoming edges for items
        for edge in graph.get_incoming_edges(node.id):
            if edge.item_name:
                item_id = self._item_name_to_id(edge.item_name)
                if item_id:
                    supplied.add(ItemId(item_id))

        return supplied

    def _find_flow_node(self, building_id: str) -> FlowNode | None:
        """Find the flow graph node for a building by element id.

        Flow graph nodes are keyed by ItemKey using real RoomPlacement ids,
        which the belt connector doesn't have (it only knows the scene's Room
        id). Linked placements share the same room content, so matching by
        element id alone yields equivalent flow info for any placement.
        """
        flow_solver = self.canvas.flow_solver
        if not flow_solver or not flow_solver._solved_model:
            return None

        graph = flow_solver._solved_model.graph
        for node in graph.nodes.values():
            if node.building_id and node.building_id.element_id == building_id:
                return node
        return None

    def _get_item_from_flow_solver(self) -> str | None:
        """Get the item ID flowing from the current output port via flow solver."""
        if not self._connect_start_building_id:
            return None

        node = self._find_flow_node(self._connect_start_building_id)
        if not node:
            return None

        port_index = self._connect_start_port
        if port_index < len(node.outputs):
            item_name = node.outputs[port_index].item_name
            if item_name:
                return self._item_name_to_id(item_name)

        return None

    def _item_name_to_id(self, item_name: str) -> str | None:
        """Convert item display name to item ID."""
        from satisfactory_planner.core import load_items

        for item_id, name, _is_fluid, _is_mineable in load_items():
            if name == item_name:
                return str(item_id)
        return None

    def _item_id_to_name(self, item_id: ItemId) -> str | None:
        """Convert item ID to display name."""
        from satisfactory_planner.core import load_items

        for iid, name, _is_fluid, _is_mineable in load_items():
            if iid == item_id:
                return str(name)
        return None

    def _item_id_is_mineable(self, item_id: ItemId) -> bool:
        """Return True if the item is a mineable raw resource (extractable by a Miner)."""
        from satisfactory_planner.core import load_items

        for iid, _name, _is_fluid, is_mineable in load_items():
            if iid == item_id:
                return bool(is_mineable)
        return False

    def _spawn_and_connect(self, option: BuildingOption, scene_pos: QPointF) -> None:
        """Spawn a building and connect it with a belt.

        Positions the building so the chosen port aligns with scene_pos. When
        multiple ports could semantically hold this connection (any free
        input on a recipe building - Satisfactory allows free port
        assignment - or any output on an item-agnostic Splitter), picks the
        port giving the shortest belt (Dubins path length).
        """
        if not self._connect_start_building_id:
            self.cancel()
            return

        scene_room_id = self._connect_start_scene_room_id

        # Create the building
        building = Building(
            id=generate_id(),
            building_type=option.building_type,
            x=0,
            y=0,
            recipe_id=option.recipe.id if option.recipe else None,
            item_id=option.item_id,  # Set for Source/Sink from the option
        )

        # Determine candidate port indices for this connection.
        # Forward drag connects to the new building's INPUT - any input port
        # qualifies (free port assignment).
        # Backward drag connects to the new building's OUTPUT - only
        # item-agnostic Splitter outputs are interchangeable; recipe outputs
        # (and single-output Merger/Source) are positionally fixed.
        if self._drag_forward:
            candidates = list(range(building.num_inputs)) or [option.port_index]
        elif option.building_type == BuildingType.SPLITTER:
            candidates = list(range(building.num_outputs)) or [option.port_index]
        else:
            candidates = [option.port_index]

        best_port_index = option.port_index
        best_length = float("inf")

        for candidate in candidates:
            if self._drag_forward:
                port_pos = building.input_port_pos(candidate)
                port_dir = building.input_port_direction(candidate)
            else:
                port_pos = building.output_port_pos(candidate)
                port_dir = building.output_port_direction(candidate)

            # The chosen port always lands exactly at scene_pos (building is
            # offset to place it there), so only the direction varies here.
            length = self._compute_candidate_length(scene_pos, port_dir)
            if length is not None and length < best_length:
                best_length = length
                best_port_index = candidate

        # Calculate building position so the chosen port aligns with scene_pos
        if self._drag_forward:
            port_pos = building.input_port_pos(best_port_index)
        else:
            port_pos = building.output_port_pos(best_port_index)

        # port_pos is relative to building at (0,0), so offset is negative
        building.x = scene_pos.x() - port_pos[0]
        building.y = scene_pos.y() - port_pos[1]

        # Snap to grid if enabled
        if self.canvas.grid_snap:
            grid = self.canvas.grid_size
            building.x = round(building.x / grid) * grid
            building.y = round(building.y / grid) * grid

        # Place building command
        place_cmd = PlaceBuildingCommand(
            scene_room_id=scene_room_id,
            building=building,
            canvas=self.canvas,
        )
        self.canvas.command_stack.execute(place_cmd)

        # Now complete the belt connection
        self.complete(building.id, best_port_index)

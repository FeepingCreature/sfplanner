"""Belt connection manager for the factory canvas."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QCursor, QPen
from PySide6.QtWidgets import QGraphicsItem, QGraphicsPathItem, QMenu

from satisfactory_planner.core import Belt, BuildingType, ItemId, Recipe
from satisfactory_planner.core.item_key import ItemKey
from satisfactory_planner.core.models import Building, generate_id
from satisfactory_planner.core.routing import Point, compute_belt_path
from satisfactory_planner.ui.commands import ConnectBeltCommand, PlaceBuildingCommand
from satisfactory_planner.ui.items.path_utils import belt_path_to_painter_path

if TYPE_CHECKING:
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


class BeltConnector:
    """Manages belt connection dragging and creation.

    Handles the drag preview, port hover highlighting, and connection completion.
    Supports both forward (from output) and backward (from input) dragging.
    """

    def __init__(self, canvas: FactoryCanvas) -> None:
        self.canvas = canvas
        self._is_connecting = False
        self._drag_forward = True  # True = from output, False = from input
        self._connect_start_item: ItemKey | None = None  # The building/placement being dragged from
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
        item_key: ItemKey,
        port_index: int,
        start_pos: QPointF,
        is_output: bool = True,
    ) -> None:
        """Start dragging a belt connection from a port.

        Args:
            item_key: ItemKey for the building or room placement
            port_index: Which port
            start_pos: Scene position to start drag from
            is_output: True if dragging from output (forward), False if from input (backward)

        If the port already has a belt, delete it first (implicit replacement).
        """
        building_id = item_key.element_id

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
        self._connect_start_item = item_key
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
        """Update the drag preview path to the given end position."""
        if not self._drag_preview or not self._drag_start_pos:
            return

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
            # Reverse the end direction (cursor pointing back)
            start_dir = end_dir + math.pi
            end_dir = self._drag_start_dir
            belt_path = compute_belt_path(start, start_dir, end, end_dir)
            path = belt_path_to_painter_path(start, end, belt_path)

        self._drag_preview.setPath(path)

    def update_hover_target(self, scene_pos: QPointF) -> None:
        """Check if hovering over a valid target port and update highlight.

        When dragging forward (from output), look for input ports.
        When dragging backward (from input), look for output ports.
        """
        from satisfactory_planner.ui.items.port_item import PortItem
        from satisfactory_planner.ui.items.room_port_item import RoomPortItem

        # When dragging forward, we look for inputs; when backward, we look for outputs
        target_is_output = not self._drag_forward

        new_target: PortItem | RoomPortItem | None = None
        for item in self.canvas._scene.items(scene_pos):
            # Check for building port
            if isinstance(item, PortItem) and item.is_output == target_is_output:
                new_target = item
                break
            # Check for room port
            if isinstance(item, RoomPortItem) and item.is_output == target_is_output:
                new_target = item
                break

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

        # No valid port - cancel
        self.cancel()
        return True

    def complete(self, target_building_id: str, target_port_index: int) -> None:
        """Complete a belt connection to a target port.

        For forward drag: target is an input port (dest)
        For backward drag: target is an output port (source)
        """
        if self._is_connecting and self._connect_start_item:
            start_building_id = self._connect_start_item.element_id
            scene_room_id = self._connect_start_item.placement_id

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
        self._connect_start_item = None
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
        if not self._is_connecting or not self._connect_start_item:
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

        # Add splitter/merger at top
        logistics_options = [o for o in options if o.recipe is None]
        recipe_options = [o for o in options if o.recipe is not None]

        for option in logistics_options:
            action = menu.addAction(option.display_name)
            action.setData(option)

        if logistics_options and recipe_options:
            menu.addSeparator()

        for option in recipe_options:
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
        if not self._connect_start_item:
            return options
        building = self.canvas.document.find_building(self._connect_start_item.element_id)
        if not building:
            return options

        # Get all items needed by the recipe (Satisfactory allows any port ordering)
        needed_item_ids = self._get_all_recipe_inputs(self._connect_start_item, building)

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

            # Offer Source for any item
            options.append(
                BuildingOption(
                    building_type=BuildingType.SOURCE,
                    recipe=None,
                    port_index=0,
                    display_name="Source",
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

    def _get_all_recipe_inputs(self, item_key: ItemKey, building: Building) -> list[ItemId]:
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
        already_supplied = self._get_supplied_items(item_key)

        # Return unique item IDs from all inputs, excluding already-supplied ones
        seen: set[ItemId] = set()
        result: list[ItemId] = []
        for inp in recipe.inputs:
            if inp.item_id not in seen and inp.item_id not in already_supplied:
                seen.add(inp.item_id)
                result.append(inp.item_id)
        return result

    def _get_supplied_items(self, item_key: ItemKey) -> set[ItemId]:
        """Get item IDs already being supplied to a building's inputs.

        Uses the flow solver graph to find incoming edges to this building's node.
        """
        supplied: set[ItemId] = set()

        flow_solver = self.canvas.flow_solver
        if not flow_solver or not flow_solver._solved_model:
            return supplied

        graph = flow_solver._solved_model.graph
        node = graph.nodes.get(item_key)
        if not node:
            return supplied

        # Check incoming edges for items
        for edge in graph.get_incoming_edges(node.id):
            if edge.item_name:
                item_id = self._item_name_to_id(edge.item_name)
                if item_id:
                    supplied.add(ItemId(item_id))

        return supplied

    def _get_item_from_flow_solver(self) -> str | None:
        """Get the item ID flowing from the current output port via flow solver."""
        flow_solver = self.canvas.flow_solver
        if not flow_solver or not flow_solver._solved_model:
            return None

        if not self._connect_start_item:
            return None

        graph = flow_solver._solved_model.graph
        node = graph.nodes.get(self._connect_start_item)
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

        for item_id, name, _is_fluid in load_items():
            if name == item_name:
                return item_id
        return None

    def _spawn_and_connect(self, option: BuildingOption, scene_pos: QPointF) -> None:
        """Spawn a building and connect it with a belt.

        Positions the building so the target port aligns with scene_pos.
        """
        if not self._connect_start_item:
            self.cancel()
            return

        scene_room_id = self._connect_start_item.placement_id

        # Create the building
        building = Building(
            id=generate_id(),
            building_type=option.building_type,
            x=0,
            y=0,
            recipe_id=option.recipe.id if option.recipe else None,
        )

        # Calculate building position so target port aligns with scene_pos
        # For forward drag, we're connecting to the new building's INPUT
        # For backward drag, we're connecting to the new building's OUTPUT
        if self._drag_forward:
            # New building's input port should be at scene_pos
            port_pos = building.input_port_pos(option.port_index)
        else:
            # New building's output port should be at scene_pos
            port_pos = building.output_port_pos(option.port_index)

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
        self.complete(building.id, option.port_index)

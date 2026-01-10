"""Visual synchronization manager for the factory canvas.

Handles syncing visual items with model state, including:
- Adding/removing visual items for buildings, belts, rooms
- Refreshing item state from model
- Flow visualization updates
- Warning icon management
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QGraphicsItem

from satisfactory_planner.core import BuildingType
from satisfactory_planner.core.models import Scene
from satisfactory_planner.ui.items.belt_item import BeltItem
from satisfactory_planner.ui.items.building_item import BuildingItem
from satisfactory_planner.ui.items.warning_icon_item import WarningIconItem

if TYPE_CHECKING:
    from collections.abc import Iterator
    from typing import Protocol

    from satisfactory_planner.ui.canvas.factory_canvas import FactoryCanvas
    from satisfactory_planner.ui.items.room_item import RoomItem

    class VisualContainer(Protocol):
        """Protocol for anything that can contain visual items for buildings and belts."""

        def add_building_item(self, building_id: str) -> object | None: ...
        def remove_building_item(self, building_id: str) -> None: ...
        def add_belt_item(self, belt_id: str) -> object | None: ...
        def remove_belt_item(self, belt_id: str) -> None: ...


class VisualSyncManager:
    """Manages synchronization between model state and visual items."""

    def __init__(self, canvas: FactoryCanvas) -> None:
        self.canvas = canvas
        self._warning_icons: list[WarningIconItem] = []

    # === Scene/item lookup helpers ===

    def get_scene(self, scene_room_id: str | None) -> Scene:
        """Get the Scene for a room_id (or document if None)."""
        if scene_room_id and scene_room_id in self.canvas.document.rooms:
            return self.canvas.document.rooms[scene_room_id]
        return self.canvas.document

    def iter_building_items(
        self, building_id: str, scene_room_id: str | None
    ) -> Iterator[BuildingItem]:
        """Iterate all visual items for a building (including linked room placements)."""
        from satisfactory_planner.ui.items.room_item import RoomItem

        if scene_room_id:
            for room_item in self.canvas._room_items.values():
                if isinstance(room_item, RoomItem) and room_item.room.id == scene_room_id:
                    item = room_item._building_items.get(building_id)
                    if item:
                        yield item
        else:
            item = self.canvas._building_items.get(building_id)
            if item:
                yield item

    def iter_belt_items(self, belt_id: str, scene_room_id: str | None) -> Iterator[BeltItem]:
        """Iterate all visual items for a belt (including linked room placements)."""
        from satisfactory_planner.ui.items.room_item import RoomItem

        if scene_room_id:
            for room_item in self.canvas._room_items.values():
                if isinstance(room_item, RoomItem) and room_item.room.id == scene_room_id:
                    item = room_item._belt_items.get(belt_id)
                    if item:
                        yield item
        else:
            item = self.canvas._belt_items.get(belt_id)
            if item:
                yield item

    def iter_room_items_for_room(self, room_id: str) -> Iterator[RoomItem]:
        """Iterate all RoomItems displaying a given room."""
        from satisfactory_planner.ui.items.room_item import RoomItem

        for room_item in self.canvas._room_items.values():
            if isinstance(room_item, RoomItem) and room_item.room.id == room_id:
                yield room_item

    def iter_visual_containers(self, scene_room_id: str | None) -> Iterator[VisualContainer]:
        """Iterate all visual containers for a scene.

        For document-level (scene_room_id=None): yields canvas.
        For room-level: yields all RoomItems displaying that room.
        """
        if scene_room_id:
            yield from self.iter_room_items_for_room(scene_room_id)
        else:
            yield self.canvas

    # === Sync methods (for commands) ===

    def sync_add_belt(self, belt_id: str, scene_room_id: str | None) -> None:
        """Add visual for a belt - routes to correct container(s)."""
        for container in self.iter_visual_containers(scene_room_id):
            container.add_belt_item(belt_id)

    def sync_remove_belt(self, belt_id: str, scene_room_id: str | None) -> None:
        """Remove visual for a belt - routes to correct container(s)."""
        for container in self.iter_visual_containers(scene_room_id):
            container.remove_belt_item(belt_id)

    def sync_add_building(self, building_id: str, scene_room_id: str | None) -> None:
        """Add visual for a building - routes to correct container(s)."""
        for container in self.iter_visual_containers(scene_room_id):
            container.add_building_item(building_id)

    def sync_remove_building(self, building_id: str, scene_room_id: str | None) -> None:
        """Remove visual for a building - routes to correct container(s)."""
        for container in self.iter_visual_containers(scene_room_id):
            container.remove_building_item(building_id)

    def sync_building_moved(
        self, building_id: str, scene_room_id: str | None, source_item: object = None
    ) -> None:
        """Sync all visual items after a building's position changed in the model.

        This is the central method for propagating position changes to all visual
        representations of a building (including linked room placements).

        Args:
            building_id: The building that moved
            scene_room_id: The room the building is in (None for document-level)
            source_item: The item that initiated the move (will be skipped to avoid feedback)
        """
        scene = self.get_scene(scene_room_id)
        building = scene.buildings.get(building_id)
        if not building:
            return

        new_pos = QPointF(building.x, building.y)

        # Update all visual items for this building
        for item in self.iter_building_items(building_id, scene_room_id):
            if item is not source_item:
                # Suppress itemChange to avoid feedback loop
                item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, False)
                item.setPos(new_pos)
                item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)

        # Update all belts connected to this building
        for belt in scene.get_belts_for_building(building_id):
            for belt_item in self.iter_belt_items(belt.id, scene_room_id):
                belt_item._update_path_from_endpoints()

        # If this is a PORT building, update room ports on all room items
        if (
            building.building_type in (BuildingType.PORT_IN, BuildingType.PORT_OUT)
            and scene_room_id
        ):
            for room_item in self.iter_room_items_for_room(scene_room_id):
                room_item.update_room_ports()

        # Update selection outline
        self.canvas._selection.update_outline()

    # === Refresh methods ===

    def refresh_building(self, building_id: str) -> None:
        """Refresh a building's visual state."""
        item = self.canvas._building_items.get(building_id)
        if item:
            building = self.canvas.document.buildings.get(building_id)
            if building:
                item.setPos(building.x, building.y)
            item.update()

    def refresh_belt(self, belt_id: str, scene_room_id: str | None = None) -> None:
        """Refresh a belt's visual state.

        For belts in rooms, this updates ALL visual instances (since linked
        room placements share the same Room data).
        """
        scene = self.get_scene(scene_room_id)
        belt = scene.belts.get(belt_id)
        if not belt:
            return

        for belt_item in self.iter_belt_items(belt_id, scene_room_id):
            belt_item.belt = belt  # Update reference to get new tier
            belt_item._setup_appearance()
            source = scene.buildings.get(belt.source_building_id)
            dest = scene.buildings.get(belt.dest_building_id)
            if source and dest:
                belt_item.update_path(source, dest)
            else:
                belt_item._update_path_from_endpoints()
            belt_item.update()

    def refresh_belts_for_building(self, building_id: str, scene: Scene) -> None:
        """Refresh belts connected to a building."""
        for room_id, room in self.canvas.document.rooms.items():
            if building_id in room.buildings:
                self.refresh_all_room_items(room_id)
                return
        self.canvas.update_belts_for_building(building_id, scene)

    def refresh_all_room_items(self, room_id: str) -> None:
        """Refresh all RoomItems displaying the given room."""
        for room_item in self.iter_room_items_for_room(room_id):
            room_item.refresh()

    # === Flow visualization ===

    def update_flow_visualization(self) -> None:
        """Update visual state of items based on flow solver results.

        Iterates visual items and lets each look up its own flow data using
        its flow_key (which includes placement_id for items inside rooms).
        """
        from satisfactory_planner.ui.items.room_item import RoomItem

        main_window = self.canvas.window()
        if not hasattr(main_window, "current_tab") or not main_window.current_tab:
            return

        flow_solver = main_window.current_tab.flow_solver
        solved = flow_solver and flow_solver._solved_model

        # Update all belt items - each uses its flow_key to look up results
        for belt_item in self.canvas._belt_items.values():
            flow_rate = solved and solved.flows.get(belt_item.flow_key)
            optimal_flow_rate = solved and solved.theoretical_flows.get(belt_item.flow_key)
            belt_item.set_flow_rate(flow_rate, optimal_flow_rate)

        # Update all building items - each uses its flow_key to look up results
        for building_item in self.canvas._building_items.values():
            eff = solved and solved.efficiencies.get(building_item.flow_key)
            building_item.set_efficiency(eff and eff.duty_cycle)

        # Also update items inside room placements
        for room_item in self.canvas._room_items.values():
            if not isinstance(room_item, RoomItem):
                continue
            for belt_item in room_item._belt_items.values():
                flow_rate = solved and solved.flows.get(belt_item.flow_key)
                optimal_flow_rate = solved and solved.theoretical_flows.get(belt_item.flow_key)
                belt_item.set_flow_rate(flow_rate, optimal_flow_rate)

            for building_item in room_item._building_items.values():
                eff = solved and solved.efficiencies.get(building_item.flow_key)
                building_item.set_efficiency(eff and eff.duty_cycle)

        # Update warning icons
        self.update_warning_icons(flow_solver._warnings)

    def update_warning_icons(self, warnings: list[object]) -> None:
        """Update warning icons based on current warnings."""
        from satisfactory_planner.core.flow_solver import Warning

        # Remove existing warning icons
        for icon in self._warning_icons:
            self.canvas._scene.removeItem(icon)
        self._warning_icons.clear()

        # Add new warning icons at element positions
        for warning in warnings:
            if not isinstance(warning, Warning):
                continue

            position = self._get_element_position(warning.element_id)
            if position:
                # Offset slightly so icon doesn't cover the element
                offset_pos = QPointF(position.x() + 30, position.y() - 10)
                icon = WarningIconItem(warning, offset_pos)
                self.canvas._scene.addItem(icon)
                self._warning_icons.append(icon)

    def _get_element_position(self, element_id: str) -> QPointF | None:
        """Get the scene position for an element (building or belt)."""
        # Check buildings
        if element_id in self.canvas._building_items:
            building_item = self.canvas._building_items[element_id]
            rect = building_item.boundingRect()
            # Use mapToScene to handle buildings inside rooms correctly
            return building_item.mapToScene(rect.center())

        # Check belts - use midpoint
        if element_id in self.canvas._belt_items:
            belt_item = self.canvas._belt_items[element_id]
            path = belt_item.path()
            if path.length() > 0:
                # Use mapToScene to handle belts inside rooms correctly
                point = path.pointAtPercent(0.5)
                return belt_item.mapToScene(point)

        return None

    @property
    def warning_icons(self) -> list[WarningIconItem]:
        """Get the list of warning icons."""
        return self._warning_icons

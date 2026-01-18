"""Placement manager for building and blueprint placement."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QBrush, QColor, QPen
from PySide6.QtWidgets import QGraphicsRectItem

from satisfactory_planner.core import Building, BuildingType, Room
from satisfactory_planner.core.models import generate_id
from satisfactory_planner.ui.commands import PlaceBlueprintCommand, PlaceBuildingCommand

if TYPE_CHECKING:
    from satisfactory_planner.ui.canvas.factory_canvas import FactoryCanvas, GhostBuildingItem


class PlacementManager:
    """Manages building and blueprint placement modes.

    Handles ghost previews, placement mode state, and rotation during placement.
    """

    def __init__(self, canvas: FactoryCanvas) -> None:
        self.canvas = canvas
        self._placement_mode: BuildingType | None = None
        self._placement_rotation: int = 0
        self._ghost_item: GhostBuildingItem | None = None

        # Blueprint placement
        self._blueprint_room: Room | None = None
        self._blueprint_ghost: QGraphicsRectItem | None = None

        # Drag-drop placement from library
        self._drag_building_type: BuildingType | None = None
        self._drag_rotation: int = 0
        self._drag_ghost: GhostBuildingItem | None = None

    @property
    def is_placing(self) -> bool:
        """Return whether in any placement mode."""
        return self._placement_mode is not None or self._blueprint_room is not None

    @property
    def placement_mode(self) -> BuildingType | None:
        """Return current building placement mode."""
        return self._placement_mode

    @property
    def blueprint_room(self) -> Room | None:
        """Return current blueprint being placed."""
        return self._blueprint_room

    def set_building_mode(self, building_type: BuildingType | None) -> None:
        """Enter or exit building placement mode."""
        # Clean up old ghost
        if self._ghost_item:
            self.canvas._scene.removeItem(self._ghost_item)
            self._ghost_item = None

        # Clear blueprint mode
        self.clear_blueprint_mode()

        self._placement_mode = building_type
        self._placement_rotation = 0

        if building_type:
            self.canvas.setCursor(Qt.CursorShape.CrossCursor)
            # Create ghost preview
            from satisfactory_planner.ui.canvas.factory_canvas import GhostBuildingItem

            ghost_building = Building(
                id="ghost",
                building_type=building_type,
                x=0,
                y=0,
            )
            self._ghost_item = GhostBuildingItem(ghost_building, self.canvas)
            self._ghost_item.setVisible(False)
            self.canvas._scene.addItem(self._ghost_item)
        else:
            self.canvas.setCursor(Qt.CursorShape.ArrowCursor)

    def set_blueprint_mode(self, room: Room) -> None:
        """Enter blueprint placement mode."""
        # Clear building mode
        if self._ghost_item:
            self.canvas._scene.removeItem(self._ghost_item)
            self._ghost_item = None
        self._placement_mode = None

        # Clear previous blueprint
        self.clear_blueprint_mode()

        self._blueprint_room = room
        self.canvas.setCursor(Qt.CursorShape.CrossCursor)

        # Create ghost rectangle
        self._blueprint_ghost = QGraphicsRectItem(0, 0, room.width, room.height)
        self._blueprint_ghost.setPen(QPen(QColor(100, 200, 100), 2, Qt.PenStyle.DashLine))
        self._blueprint_ghost.setBrush(QBrush(QColor(100, 200, 100, 50)))
        self._blueprint_ghost.setOpacity(0.7)
        self._blueprint_ghost.setVisible(False)
        self._blueprint_ghost.setZValue(1000)
        self.canvas._scene.addItem(self._blueprint_ghost)

    def clear_blueprint_mode(self) -> None:
        """Clear blueprint placement mode."""
        self._blueprint_room = None
        if self._blueprint_ghost:
            self.canvas._scene.removeItem(self._blueprint_ghost)
            self._blueprint_ghost = None

    def update_ghost_position(self, scene_pos: QPointF) -> None:
        """Update ghost position during mouse move."""
        snapped = self.canvas._snap_to_grid(scene_pos)

        if self._placement_mode and self._ghost_item:
            self._ghost_item.setPos(snapped)
            self._ghost_item.setVisible(True)

        if self._blueprint_room and self._blueprint_ghost:
            self._blueprint_ghost.setPos(snapped)
            self._blueprint_ghost.setVisible(True)

    def rotate(self, delta: int) -> None:
        """Rotate the current placement by delta degrees (typically ±90)."""
        if self._placement_mode and self._ghost_item:
            self._placement_rotation = (self._placement_rotation + delta) % 360
            self._ghost_item.rotation_angle = self._placement_rotation
            self._ghost_item.update()

    def place_at(self, scene_pos: QPointF) -> bool:
        """Attempt to place at the given position.

        Returns True if something was placed.
        """
        snapped = self.canvas._snap_to_grid(scene_pos)

        if self._placement_mode:
            self._place_building(self._placement_mode, snapped.x(), snapped.y())
            return True

        if self._blueprint_room:
            self._place_blueprint(self._blueprint_room, snapped.x(), snapped.y())
            self.clear_blueprint_mode()
            self.canvas.setCursor(Qt.CursorShape.ArrowCursor)
            return True

        return False

    def _place_building(self, building_type: BuildingType, x: float, y: float) -> None:
        """Place a building at the given position."""
        # Check if dropping into a room - need to convert to room-local coordinates
        placement = self.canvas.get_room_placement_at_point(QPointF(x, y))
        if placement:
            # Convert scene coordinates to room-local coordinates
            local_x = x - placement.x
            local_y = y - placement.y
            scene_room_id = placement.room_id
        else:
            local_x = x
            local_y = y
            scene_room_id = None

        building = Building(
            id=generate_id(),
            building_type=building_type,
            x=local_x,
            y=local_y,
            rotation=self._placement_rotation,
        )
        cmd = PlaceBuildingCommand(
            scene_room_id=scene_room_id, building=building, canvas=self.canvas
        )
        self.canvas.command_stack.execute(cmd)

        item = self.canvas._building_items.get(building.id)
        if item:
            item.rotation_angle = self._placement_rotation

    def _place_blueprint(self, room: Room, x: float, y: float) -> None:
        """Place a blueprint at the given position."""
        cmd = PlaceBlueprintCommand.create(
            source_room=room, x=x, y=y, canvas=self.canvas, document=self.canvas.document
        )
        self.canvas.command_stack.execute(cmd)

    # Drag-drop support

    def start_drag(self, building_type: BuildingType, scene_pos: QPointF) -> None:
        """Start drag-drop placement from library."""
        from satisfactory_planner.ui.canvas.factory_canvas import GhostBuildingItem

        self._drag_building_type = building_type
        self._drag_rotation = 0

        ghost_building = Building(
            id="drag_ghost",
            building_type=building_type,
            x=0,
            y=0,
        )
        self._drag_ghost = GhostBuildingItem(ghost_building, self.canvas)
        self._drag_ghost.setPos(self.canvas._snap_to_grid(scene_pos))
        self.canvas._scene.addItem(self._drag_ghost)

    def update_drag(self, scene_pos: QPointF) -> None:
        """Update drag ghost position."""
        if self._drag_ghost:
            w, h = self._drag_ghost.building._get_display_size()
            centered = QPointF(scene_pos.x() - w / 2, scene_pos.y() - h / 2)
            self._drag_ghost.setPos(self.canvas._snap_to_grid(centered))

    def rotate_drag(self, delta: int) -> None:
        """Rotate the drag ghost."""
        if self._drag_building_type:
            self._drag_rotation = (self._drag_rotation + delta) % 360
            if self._drag_ghost:
                self._drag_ghost.rotation_angle = self._drag_rotation

    def complete_drag(self, scene_pos: QPointF) -> None:
        """Complete drag-drop placement."""
        if self._drag_building_type:
            from satisfactory_planner.core import BUILDING_METADATA

            spec = BUILDING_METADATA.get(self._drag_building_type)
            if spec:
                scene_pos = QPointF(scene_pos.x() - spec.width / 2, scene_pos.y() - spec.height / 2)
            snapped = self.canvas._snap_to_grid(scene_pos)

            # Check if dropping into a room - need to convert to room-local coordinates
            placement = self.canvas.get_room_placement_at_point(snapped)
            if placement:
                # Convert scene coordinates to room-local coordinates
                local_x = snapped.x() - placement.x
                local_y = snapped.y() - placement.y
                scene_room_id = placement.room_id
            else:
                local_x = snapped.x()
                local_y = snapped.y()
                scene_room_id = None

            building = Building(
                id=generate_id(),
                building_type=self._drag_building_type,
                x=local_x,
                y=local_y,
                rotation=self._drag_rotation,
            )
            cmd = PlaceBuildingCommand(
                scene_room_id=scene_room_id, building=building, canvas=self.canvas
            )
            self.canvas.command_stack.execute(cmd)

            item = self.canvas._building_items.get(building.id)
            if item:
                item.rotation_angle = self._drag_rotation

        self.cancel_drag()

    def cancel_drag(self) -> None:
        """Cancel drag-drop placement."""
        self._drag_building_type = None
        self._drag_rotation = 0
        if self._drag_ghost:
            self.canvas._scene.removeItem(self._drag_ghost)
            self._drag_ghost = None

    # Blueprint drag support

    def start_blueprint_drag(self, room: Room, scene_pos: QPointF) -> None:
        """Start dragging a blueprint from library."""
        self._blueprint_room = room
        self._blueprint_ghost = QGraphicsRectItem(0, 0, room.width, room.height)
        self._blueprint_ghost.setPen(QPen(QColor(100, 200, 100), 2, Qt.PenStyle.DashLine))
        self._blueprint_ghost.setBrush(QBrush(QColor(100, 200, 100, 50)))
        self._blueprint_ghost.setOpacity(0.7)
        self._blueprint_ghost.setZValue(1000)
        self._blueprint_ghost.setPos(self.canvas._snap_to_grid(scene_pos))
        self.canvas._scene.addItem(self._blueprint_ghost)

    def update_blueprint_drag(self, scene_pos: QPointF) -> None:
        """Update blueprint ghost position during drag."""
        if self._blueprint_ghost:
            self._blueprint_ghost.setPos(self.canvas._snap_to_grid(scene_pos))

    def complete_blueprint_drag(self, scene_pos: QPointF) -> None:
        """Complete blueprint drag-drop."""
        if self._blueprint_room:
            snapped = self.canvas._snap_to_grid(scene_pos)
            self._place_blueprint(self._blueprint_room, snapped.x(), snapped.y())
        self.clear_blueprint_mode()

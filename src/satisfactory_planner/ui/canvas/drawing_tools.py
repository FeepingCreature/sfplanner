"""Drawing tools for box selection and room creation."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPen
from PySide6.QtWidgets import QGraphicsItem, QGraphicsRectItem

from satisfactory_planner.core import Belt, Building
from satisfactory_planner.core.models import Scene
from satisfactory_planner.ui.commands import CreateRoomCommand

if TYPE_CHECKING:
    from satisfactory_planner.ui.canvas.factory_canvas import FactoryCanvas

logger = logging.getLogger(__name__)


class DrawingTools:
    """Manages box selection and room creation tools.

    Both are drag-to-create-rectangle operations with different outcomes.
    """

    def __init__(self, canvas: FactoryCanvas) -> None:
        self.canvas = canvas

        # Box select state
        self._box_select_start: QPointF | None = None
        self._box_select_rect: QGraphicsRectItem | None = None

        # Room creation state
        self._room_create_start: QPointF | None = None
        self._room_create_rect: QGraphicsRectItem | None = None

    @property
    def is_box_selecting(self) -> bool:
        """Return whether box selection is in progress."""
        return self._box_select_start is not None

    @property
    def is_creating_room(self) -> bool:
        """Return whether room creation is in progress."""
        return self._room_create_start is not None

    # Box selection

    def start_box_select(self, scene_pos: QPointF) -> None:
        """Start a box selection at the given scene position."""
        self._box_select_start = scene_pos

        self._box_select_rect = QGraphicsRectItem(QRectF(scene_pos, scene_pos))
        pen = QPen(QColor(100, 150, 255), 1, Qt.PenStyle.DashLine)
        self._box_select_rect.setPen(pen)
        self._box_select_rect.setBrush(QBrush(QColor(100, 150, 255, 30)))
        self._box_select_rect.setZValue(1000)
        self._box_select_rect.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.canvas._scene.addItem(self._box_select_rect)

    def update_box_select(self, scene_pos: QPointF) -> None:
        """Update the box selection rectangle."""
        if not self._box_select_start or not self._box_select_rect:
            return

        rect = QRectF(self._box_select_start, scene_pos).normalized()
        self._box_select_rect.setRect(rect)

    def complete_box_select(self) -> None:
        """Complete box selection, selecting all items in the rect."""
        if not self._box_select_rect:
            self.cancel_box_select()
            return

        select_rect = self._box_select_rect.rect()

        self.canvas._scene.clearSelection()

        # Select buildings
        for building_item in self.canvas._building_items.values():
            if select_rect.intersects(building_item.sceneBoundingRect()):
                building_item.setSelected(True)

        # Select belts
        for belt_item in self.canvas._belt_items.values():
            if select_rect.intersects(belt_item.sceneBoundingRect()):
                belt_item.setSelected(True)

        self.cancel_box_select()
        self.canvas._emit_selection_changed()

    def cancel_box_select(self) -> None:
        """Cancel the current box selection."""
        self._box_select_start = None
        if self._box_select_rect:
            self.canvas._scene.removeItem(self._box_select_rect)
            self._box_select_rect = None

    # Room creation

    def start_room_create(self, scene_pos: QPointF) -> None:
        """Start room creation at the given scene position."""
        self._room_create_start = scene_pos

        self._room_create_rect = QGraphicsRectItem(QRectF(scene_pos, scene_pos))
        pen = QPen(QColor(100, 200, 100), 2, Qt.PenStyle.DashLine)
        self._room_create_rect.setPen(pen)
        self._room_create_rect.setBrush(QBrush(QColor(100, 200, 100, 30)))
        self._room_create_rect.setZValue(1000)
        self._room_create_rect.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.canvas._scene.addItem(self._room_create_rect)

    def update_room_create(self, scene_pos: QPointF) -> None:
        """Update the room creation rectangle."""
        if not self._room_create_start or not self._room_create_rect:
            return

        rect = QRectF(self._room_create_start, scene_pos).normalized()
        self._room_create_rect.setRect(rect)

    def complete_room_create(self) -> None:
        """Complete room creation, validating and creating the room."""
        if not self._room_create_rect:
            self.cancel_room_create()
            return

        rect = self._room_create_rect.rect()

        # Validate minimum size
        if rect.width() < 50 or rect.height() < 50:
            logger.info("Room too small - minimum 50x50")
            self.cancel_room_create()
            self.canvas.set_tool_mode(None)
            return

        # Determine parent scene
        parent_scene_room_id = self.canvas.get_room_at_point(rect.topLeft())
        if parent_scene_room_id:
            parent_scene: Scene = self.canvas.document.rooms[parent_scene_room_id]
        else:
            parent_scene = self.canvas.document

        # Validate no intersected buildings
        for building in parent_scene.buildings.values():
            building_rect = self._get_building_rect(building)
            if rect.intersects(building_rect) and not rect.contains(building_rect):
                logger.warning("Room boundary cannot intersect buildings")
                self.cancel_room_create()
                self.canvas.set_tool_mode(None)
                return

        # Collect contained buildings
        contained_building_ids: list[str] = []
        for building in parent_scene.buildings.values():
            if rect.contains(self._get_building_rect(building)):
                contained_building_ids.append(building.id)

        # Collect contained and crossing belts
        contained_belt_ids: list[str] = []
        crossing_belts: list[Belt] = []
        for belt in parent_scene.belts.values():
            source_inside = belt.source_building_id in contained_building_ids
            dest_inside = belt.dest_building_id in contained_building_ids
            if source_inside and dest_inside:
                contained_belt_ids.append(belt.id)
            elif source_inside or dest_inside:
                crossing_belts.append(belt)

        # Create room command
        cmd = CreateRoomCommand.create(
            parent_scene_room_id=parent_scene_room_id,
            rect=(rect.x(), rect.y(), rect.width(), rect.height()),
            building_ids=tuple(contained_building_ids),
            belt_ids=tuple(contained_belt_ids),
            original_crossing_belts=tuple(crossing_belts),
            canvas=self.canvas,
        )
        self.canvas.command_stack.execute(cmd)

        self.cancel_room_create()
        self.canvas.set_tool_mode(None)

    def cancel_room_create(self) -> None:
        """Cancel the current room creation."""
        self._room_create_start = None
        if self._room_create_rect:
            self.canvas._scene.removeItem(self._room_create_rect)
            self._room_create_rect = None

    def _get_building_rect(self, building: Building) -> QRectF:
        """Get the bounding rectangle of a building."""
        w, h = building.get_display_size()
        return QRectF(building.x, building.y, w, h)

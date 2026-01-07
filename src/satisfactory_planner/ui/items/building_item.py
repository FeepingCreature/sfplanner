"""Graphics item for a factory building."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QPainter, QPen, QBrush, QColor, QFont, QPolygonF
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsRectItem,
    QStyleOptionGraphicsItem,
    QWidget,
    QGraphicsSceneMouseEvent,
)

from satisfactory_planner.core import Building, BuildingType, BUILDING_COLORS, LOGISTICS_DISPLAY_SIZE
from satisfactory_planner.ui.items.port_item import PortItem

if TYPE_CHECKING:
    from satisfactory_planner.ui.canvas import FactoryCanvas


def _get_building_color(building_type: BuildingType) -> QColor:
    """Get QColor for a building type from the core color definitions."""
    rgb = BUILDING_COLORS.get(building_type, (150, 150, 150))
    return QColor(rgb[0], rgb[1], rgb[2])


class BuildingItem(QGraphicsRectItem):
    """A draggable building item on the canvas."""

    def __init__(self, building: Building, canvas: FactoryCanvas) -> None:
        super().__init__()

        self.building = building
        self.canvas = canvas

        # Setup
        self._setup_rect()
        self._setup_flags()
        self._setup_ports()

        # Drag tracking
        self._drag_start_pos: QPointF | None = None

    def _get_display_size(self) -> tuple[int, int]:
        """Get display size - delegates to model."""
        return self.building._get_display_size()

    def _setup_rect(self) -> None:
        """Configure the rectangle."""
        w, h = self._get_display_size()
        self.setRect(0, 0, w, h)
        self.setPos(self.building.x, self.building.y)

        color = _get_building_color(self.building.building_type)
        self.setBrush(QBrush(color))
        self.setPen(QPen(QColor(255, 255, 255), 2))

    def _setup_flags(self) -> None:
        """Configure item flags."""
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)

    def _setup_ports(self) -> None:
        """Create port items based on building type and rotation."""
        self._input_ports: list[PortItem] = []
        self._output_ports: list[PortItem] = []

        w, h = self._get_display_size()

        if self.building.building_type == BuildingType.SPLITTER:
            # Splitter: 1 input (left), 3 outputs (top, right, bottom)
            # Input on left
            port = PortItem(False, 0, self.building.id, self.canvas, angle=180)
            port.setParentItem(self)
            port.setPos(0, h / 2)
            self._input_ports.append(port)

            # Outputs on top, right, bottom
            angles_pos = [(270, w / 2, 0), (0, w, h / 2), (90, w / 2, h)]
            for i, (angle, px, py) in enumerate(angles_pos):
                port = PortItem(True, i, self.building.id, self.canvas, angle=angle)
                port.setParentItem(self)
                port.setPos(px, py)
                self._output_ports.append(port)

        elif self.building.building_type == BuildingType.MERGER:
            # Merger: 3 inputs (top, left, bottom), 1 output (right)
            angles_pos = [(270, w / 2, 0), (180, 0, h / 2), (90, w / 2, h)]
            for i, (angle, px, py) in enumerate(angles_pos):
                port = PortItem(False, i, self.building.id, self.canvas, angle=angle)
                port.setParentItem(self)
                port.setPos(px, py)
                self._input_ports.append(port)

            # Output on right
            port = PortItem(True, 0, self.building.id, self.canvas, angle=0)
            port.setParentItem(self)
            port.setPos(w, h / 2)
            self._output_ports.append(port)

        else:
            # Standard building: inputs on left, outputs on right
            # Input ports (left side)
            for i in range(self.building.num_inputs):
                spacing = h / (self.building.num_inputs + 1)
                y = spacing * (i + 1)
                port = PortItem(False, i, self.building.id, self.canvas, angle=180)
                port.setParentItem(self)
                port.setPos(0, y)
                self._input_ports.append(port)

            # Output ports (right side)
            for i in range(self.building.num_outputs):
                spacing = h / (self.building.num_outputs + 1)
                y = spacing * (i + 1)
                port = PortItem(True, i, self.building.id, self.canvas, angle=0)
                port.setParentItem(self)
                port.setPos(w, y)
                self._output_ports.append(port)

    @property
    def rotation_angle(self) -> int:
        """Get rotation angle from model."""
        return self.building.rotation

    @rotation_angle.setter
    def rotation_angle(self, value: int) -> None:
        """Set rotation angle on model."""
        self.building.rotation = value

    def rotate_building(self, delta: int = 90) -> None:
        """Rotate the building by delta degrees."""
        self.building.rotation = (self.building.rotation + delta) % 360
        self.update()

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        """Paint the building."""
        w, h = self._get_display_size()
        rect = QRectF(0, 0, w, h)

        # Save state for rotation
        painter.save()

        # Apply rotation around center
        if self.rotation_angle != 0:
            painter.translate(w / 2, h / 2)
            painter.rotate(self.rotation_angle)
            painter.translate(-w / 2, -h / 2)

        # Draw the rectangle
        color = _get_building_color(self.building.building_type)
        painter.setBrush(QBrush(color))
        painter.setPen(QPen(QColor(255, 255, 255), 2))
        painter.drawRect(rect)

        painter.restore()

        # Draw the building name and recipe (always upright, centered)
        painter.setPen(QPen(QColor(255, 255, 255)))
        font = QFont()
        is_small = self.building.building_type in (BuildingType.SPLITTER, BuildingType.MERGER)
        font.setPointSize(7 if is_small else 8)
        painter.setFont(font)

        # Building type name
        name = self.building.building_type.value
        # Abbreviate for small buildings
        if self.building.building_type == BuildingType.SPLITTER:
            name = "SPL"
        elif self.building.building_type == BuildingType.MERGER:
            name = "MRG"

        # Get recipe name if available (skip for logistics)
        recipe_text = ""
        if not is_small and self.building.recipe_id:
            # Look up recipe in document
            doc = self.canvas.document
            recipe = doc.recipes.get(self.building.recipe_id)
            recipe_text = recipe.name if recipe else "No Recipe"
        elif not is_small:
            recipe_text = "No Recipe"

        if recipe_text:
            # Draw building type at top, recipe at bottom
            top_rect = QRectF(0, 2, w, h / 2 - 2)
            bottom_rect = QRectF(0, h / 2, w, h / 2 - 2)
            painter.drawText(top_rect, Qt.AlignHCenter | Qt.AlignBottom, name)
            
            # Recipe in smaller, slightly dimmer text
            painter.setPen(QPen(QColor(200, 200, 200)))
            small_font = QFont()
            small_font.setPointSize(7)
            painter.setFont(small_font)
            painter.drawText(bottom_rect, Qt.AlignHCenter | Qt.AlignTop, recipe_text)
        else:
            painter.drawText(rect, Qt.AlignCenter, name)

        # Draw selection highlight
        if self.isSelected():
            painter.setPen(QPen(QColor(255, 255, 0), 3))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(rect.adjusted(-2, -2, 2, 2))

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        """Track drag start."""
        self._drag_start_pos = self.pos()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        """Handle drag end - create move command."""
        super().mouseReleaseEvent(event)

        if self._drag_start_pos is not None:
            new_pos = self.pos()
            dx = new_pos.x() - self._drag_start_pos.x()
            dy = new_pos.y() - self._drag_start_pos.y()

            if dx != 0 or dy != 0:
                # DON'T update building.x/y here - the command will do it
                # Just notify canvas to create the command
                self.canvas.on_building_moved(self.building.id, dx, dy)

            self._drag_start_pos = None

    def itemChange(
        self, change: QGraphicsItem.GraphicsItemChange, value: object
    ) -> object:
        """Handle item changes."""
        if change == QGraphicsItem.ItemPositionChange and self.scene():
            # Snap to grid
            new_pos = value
            if isinstance(new_pos, QPointF) and self.canvas.grid_snap:
                grid = self.canvas.grid_size
                x = round(new_pos.x() / grid) * grid
                y = round(new_pos.y() / grid) * grid
                new_pos = QPointF(x, y)
            return new_pos
        elif change == QGraphicsItem.ItemPositionHasChanged and self.scene():
            # Update model position and redraw belts during drag
            new_pos = self.pos()
            self.building.x = new_pos.x()
            self.building.y = new_pos.y()
            self.canvas.update_belts_for_building(self.building.id)
        return super().itemChange(change, value)

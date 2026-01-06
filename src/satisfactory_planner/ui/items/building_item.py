"""Graphics item for a factory building."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QPainter, QPen, QBrush, QColor, QFont
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsRectItem,
    QStyleOptionGraphicsItem,
    QWidget,
    QGraphicsSceneMouseEvent,
)

from satisfactory_planner.core import Building, BuildingType
from satisfactory_planner.ui.items.port_item import PortItem

if TYPE_CHECKING:
    from satisfactory_planner.ui.canvas import FactoryCanvas


# Colors for different building types
BUILDING_COLORS: dict[BuildingType, QColor] = {
    BuildingType.SMELTER: QColor(200, 100, 50),
    BuildingType.FOUNDRY: QColor(180, 80, 40),
    BuildingType.CONSTRUCTOR: QColor(80, 150, 200),
    BuildingType.ASSEMBLER: QColor(100, 180, 100),
    BuildingType.MANUFACTURER: QColor(150, 100, 180),
    BuildingType.REFINERY: QColor(120, 120, 180),
    BuildingType.PACKAGER: QColor(100, 150, 150),
    BuildingType.BLENDER: QColor(180, 150, 100),
    BuildingType.MINER_MK1: QColor(150, 120, 80),
    BuildingType.MINER_MK2: QColor(160, 130, 90),
    BuildingType.MINER_MK3: QColor(170, 140, 100),
    BuildingType.SPLITTER: QColor(200, 200, 100),
    BuildingType.MERGER: QColor(100, 200, 200),
}


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

    def _setup_rect(self) -> None:
        """Configure the rectangle."""
        self.setRect(0, 0, self.building.width, self.building.height)
        self.setPos(self.building.x, self.building.y)

        color = BUILDING_COLORS.get(self.building.building_type, QColor(150, 150, 150))
        self.setBrush(QBrush(color))
        self.setPen(QPen(QColor(255, 255, 255), 2))

    def _setup_flags(self) -> None:
        """Configure item flags."""
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)

    def _setup_ports(self) -> None:
        """Create port items."""
        self._input_ports: list[PortItem] = []
        self._output_ports: list[PortItem] = []

        # Input ports (left side, yellow)
        for i in range(self.building.num_inputs):
            spacing = self.building.height / (self.building.num_inputs + 1)
            y = spacing * (i + 1)
            port = PortItem(
                is_output=False,
                port_index=i,
                building_id=self.building.id,
                canvas=self.canvas,
            )
            port.setParentItem(self)
            port.setPos(-5, y)
            self._input_ports.append(port)

        # Output ports (right side, green)
        for i in range(self.building.num_outputs):
            spacing = self.building.height / (self.building.num_outputs + 1)
            y = spacing * (i + 1)
            port = PortItem(
                is_output=True,
                port_index=i,
                building_id=self.building.id,
                canvas=self.canvas,
            )
            port.setParentItem(self)
            port.setPos(self.building.width + 5, y)
            self._output_ports.append(port)

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        """Paint the building."""
        # Draw the rectangle
        super().paint(painter, option, widget)

        # Draw the building name
        painter.setPen(QPen(QColor(255, 255, 255)))
        font = QFont()
        font.setPointSize(8)
        painter.setFont(font)

        name = self.building.building_type.value
        rect = self.rect()
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
                # Update the building model
                self.building.x = new_pos.x()
                self.building.y = new_pos.y()

                # Notify canvas
                self.canvas.on_building_moved(self.building.id, dx, dy)

            self._drag_start_pos = None

    def itemChange(
        self, change: QGraphicsItem.GraphicsItemChange, value: object
    ) -> object:
        """Handle item changes."""
        if change == QGraphicsItem.ItemPositionChange and self.scene():
            # Snap to grid
            new_pos = value
            if isinstance(new_pos, QPointF) and self.canvas._grid_snap:
                grid = self.canvas._grid_size
                x = round(new_pos.x() / grid) * grid
                y = round(new_pos.y() / grid) * grid
                return QPointF(x, y)
        return super().itemChange(change, value)

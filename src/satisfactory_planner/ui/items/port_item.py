"""Graphics item for building ports (inputs/outputs)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter, QPen, QBrush, QColor
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QStyleOptionGraphicsItem,
    QWidget,
    QGraphicsSceneMouseEvent,
)

if TYPE_CHECKING:
    from satisfactory_planner.ui.canvas import FactoryCanvas


# Port colors (matching Satisfactory)
INPUT_COLOR = QColor(255, 200, 50)   # Yellow for inputs
OUTPUT_COLOR = QColor(50, 200, 100)  # Green for outputs

PORT_RADIUS = 8


class PortItem(QGraphicsEllipseItem):
    """A clickable port for connecting belts."""

    def __init__(
        self,
        is_output: bool,
        port_index: int,
        building_id: str,
        canvas: FactoryCanvas,
    ) -> None:
        super().__init__(-PORT_RADIUS, -PORT_RADIUS, PORT_RADIUS * 2, PORT_RADIUS * 2)

        self.is_output = is_output
        self.port_index = port_index
        self.building_id = building_id
        self.canvas = canvas

        self._setup_appearance()
        self._setup_flags()

    def _setup_appearance(self) -> None:
        """Configure appearance."""
        color = OUTPUT_COLOR if self.is_output else INPUT_COLOR
        self.setBrush(QBrush(color))
        self.setPen(QPen(QColor(255, 255, 255), 1))

    def _setup_flags(self) -> None:
        """Configure flags."""
        self.setFlag(QGraphicsItem.ItemIsSelectable, False)
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.PointingHandCursor)

    def hoverEnterEvent(self, event: object) -> None:
        """Highlight on hover."""
        self.setPen(QPen(QColor(255, 255, 255), 2))
        self.setScale(1.2)

    def hoverLeaveEvent(self, event: object) -> None:
        """Remove highlight."""
        self.setPen(QPen(QColor(255, 255, 255), 1))
        self.setScale(1.0)

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        """Handle click to start/complete belt connection."""
        if event.button() == Qt.LeftButton:
            if self.is_output:
                # Start a new connection from output
                self.canvas.start_belt_connection(self.building_id, self.port_index)
            else:
                # Complete connection to input
                self.canvas.complete_belt_connection(self.building_id, self.port_index)
            event.accept()
        else:
            super().mousePressEvent(event)

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        """Paint the port with direction indicator."""
        super().paint(painter, option, widget)

        # Draw arrow to indicate direction
        painter.setPen(QPen(QColor(255, 255, 255), 1.5))
        if self.is_output:
            # Arrow pointing right
            painter.drawLine(int(-3), int(0), int(3), int(0))
            painter.drawLine(int(1), int(-3), int(3), int(0))
            painter.drawLine(int(1), int(3), int(3), int(0))
        else:
            # Arrow pointing left (into the building)
            painter.drawLine(int(-3), int(0), int(3), int(0))
            painter.drawLine(int(-1), int(-3), int(-3), int(0))
            painter.drawLine(int(-1), int(3), int(-3), int(0))

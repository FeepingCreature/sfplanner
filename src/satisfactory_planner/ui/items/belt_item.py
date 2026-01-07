"""Graphics item for belts connecting buildings."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsPathItem,
    QStyleOptionGraphicsItem,
    QWidget,
)

from satisfactory_planner.core import Belt, Building
from satisfactory_planner.core.routing import Point, compute_belt_path
from satisfactory_planner.ui.items.path_utils import belt_path_to_painter_path

if TYPE_CHECKING:
    pass


# Belt colors by tier (darker = lower tier)
BELT_COLORS = {
    1: QColor(100, 100, 100),
    2: QColor(120, 120, 120),
    3: QColor(140, 140, 140),
    4: QColor(160, 160, 160),
    5: QColor(180, 180, 180),
    6: QColor(200, 180, 100),  # Gold for max tier
}

# Belt widths by tier
BELT_WIDTHS = {
    1: 2,
    2: 3,
    3: 4,
    4: 5,
    5: 6,
    6: 7,
}


class BeltItem(QGraphicsPathItem):
    """A belt connecting two buildings."""

    def __init__(self, belt: Belt, source: Building, dest: Building) -> None:
        super().__init__()

        self.belt = belt

        self._setup_flags()
        self._setup_appearance()
        self.update_path(source, dest)

    def _setup_flags(self) -> None:
        """Configure item flags."""
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setZValue(-1)  # Draw behind buildings

    def _setup_appearance(self) -> None:
        """Configure appearance based on tier."""
        color = BELT_COLORS.get(self.belt.tier, BELT_COLORS[1])
        width = BELT_WIDTHS.get(self.belt.tier, BELT_WIDTHS[1])
        self.setPen(QPen(color, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))

    def update_path(self, source: Building, dest: Building) -> None:
        """Update the belt path between source and dest buildings."""
        # Get port positions and directions
        start_pos = source.output_port_pos(self.belt.source_port_index)
        end_pos = dest.input_port_pos(self.belt.dest_port_index)
        start_dir = source.output_port_direction(self.belt.source_port_index)
        end_dir = dest.input_port_direction(self.belt.dest_port_index)

        start = Point(start_pos[0], start_pos[1])
        end = Point(end_pos[0], end_pos[1])

        # Compute Dubins path and convert to QPainterPath
        belt_path = compute_belt_path(start, start_dir, end, end_dir)
        path = belt_path_to_painter_path(start, end, belt_path)
        self.setPath(path)

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        """Paint the belt with flow direction indicators."""
        # Draw the main belt line
        super().paint(painter, option, widget)

        # Draw selection highlight
        if self.isSelected():
            highlight_pen = QPen(QColor(255, 255, 0), self.pen().widthF() + 2)
            painter.setPen(highlight_pen)
            painter.drawPath(self.path())

        # Draw flow direction arrows
        self._draw_flow_arrows(painter)

    def _draw_flow_arrows(self, painter: QPainter) -> None:
        """Draw small arrows along the belt to show flow direction."""
        path = self.path()
        length = path.length()

        if length < 50:
            return  # Too short for arrows

        # Draw arrows at regular intervals
        arrow_spacing = 50
        num_arrows = int(length / arrow_spacing)

        painter.setPen(QPen(QColor(100, 100, 100, 150), 1))
        painter.setBrush(QBrush(QColor(100, 100, 100, 150)))

        for i in range(1, num_arrows):
            t = (i * arrow_spacing) / length
            point = path.pointAtPercent(t)
            angle = path.angleAtPercent(t)

            painter.save()
            painter.translate(point)
            painter.rotate(-angle)

            # Draw a small triangle arrow
            arrow_size = 4
            painter.drawPolygon(
                [
                    QPointF(arrow_size, 0),
                    QPointF(-arrow_size, -arrow_size),
                    QPointF(-arrow_size, arrow_size),
                ]
            )
            painter.restore()

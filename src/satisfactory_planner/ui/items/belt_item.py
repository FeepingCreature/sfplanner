"""Graphics item for belts connecting buildings."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QPainter, QPen, QBrush, QColor, QPainterPath
from PySide6.QtWidgets import (
    QGraphicsPathItem,
    QGraphicsItem,
    QStyleOptionGraphicsItem,
    QWidget,
)

from satisfactory_planner.core import Belt, Building, BELT_CAPACITIES
from satisfactory_planner.core.routing import compute_belt_path, Point

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
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setZValue(-1)  # Draw behind buildings

    def _setup_appearance(self) -> None:
        """Configure appearance based on tier."""
        color = BELT_COLORS.get(self.belt.tier, BELT_COLORS[1])
        width = BELT_WIDTHS.get(self.belt.tier, BELT_WIDTHS[1])
        self.setPen(QPen(color, width, Qt.SolidLine, Qt.RoundCap))

    def update_path(self, source: Building, dest: Building) -> None:
        """Update the belt path between source and dest buildings."""
        import math
        
        # Get port positions and directions
        start_pos = source.output_port_pos(self.belt.source_port_index)
        end_pos = dest.input_port_pos(self.belt.dest_port_index)
        start_dir = source.output_port_direction(self.belt.source_port_index)
        end_dir = dest.input_port_direction(self.belt.dest_port_index)

        start = Point(start_pos[0], start_pos[1])
        end = Point(end_pos[0], end_pos[1])

        # Compute circle-line-circle path
        belt_path = compute_belt_path(start, start_dir, end, end_dir)

        path = QPainterPath()
        
        if belt_path and belt_path.start_radius > 0:
            # Draw start arc
            path.moveTo(start.x, start.y)
            self._add_arc(
                path,
                belt_path.start_center,
                belt_path.start_radius,
                belt_path.start_angle_begin,
                belt_path.start_angle_end,
                belt_path.start_clockwise,
            )
            # Draw line segment
            path.lineTo(belt_path.line_end.x, belt_path.line_end.y)
            # Draw end arc
            self._add_arc(
                path,
                belt_path.end_center,
                belt_path.end_radius,
                belt_path.end_angle_begin,
                belt_path.end_angle_end,
                belt_path.end_clockwise,
            )
        else:
            # Fallback to straight line
            path.moveTo(start.x, start.y)
            path.lineTo(end.x, end.y)

        self.setPath(path)

    def _add_arc(
        self,
        path: QPainterPath,
        center: Point,
        radius: float,
        angle_begin: float,
        angle_end: float,
        clockwise: bool,
    ) -> None:
        """Add an arc to the path using line segments."""
        import math
        
        # Calculate sweep - always take the SHORT way around
        # Normalize angle difference to [-pi, pi]
        diff = angle_end - angle_begin
        while diff > math.pi:
            diff -= 2 * math.pi
        while diff < -math.pi:
            diff += 2 * math.pi
        
        # Skip tiny arcs
        if abs(diff) < 0.01:
            x = center.x + radius * math.cos(angle_end)
            y = center.y + radius * math.sin(angle_end)
            path.lineTo(x, y)
            return
        
        # Draw the arc by interpolating from begin to end
        angle_span = abs(diff)
        num_segments = max(4, int(angle_span * radius / 5))
        
        for i in range(1, num_segments + 1):
            t = i / num_segments
            angle = angle_begin + t * diff
            x = center.x + radius * math.cos(angle)
            y = center.y + radius * math.sin(angle)
            path.lineTo(x, y)

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

"""Circle-line-circle routing test.

Left-click to rotate start direction.
Move mouse to see the path.
"""

import math
import sys

from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QPainter, QPen, QColor, QPainterPath, QBrush
from PySide6.QtWidgets import QApplication, QGraphicsView, QGraphicsScene, QGraphicsPathItem, QGraphicsLineItem, QGraphicsTextItem


class ArcTestView(QGraphicsView):
    def __init__(self):
        super().__init__()
        self.scene = QGraphicsScene(self)
        self.scene.setSceneRect(-400, -400, 800, 800)
        self.setScene(self.scene)
        self.setRenderHint(QPainter.Antialiasing)
        self.setMouseTracking(True)
        
        # Fixed start point and direction
        self.start = QPointF(-100, 0)
        self.start_dir = 0  # radians, pointing RIGHT
        self.end_dir = 0  # absolute end direction, pointing RIGHT
        self.radius = 40
        
        # Draw origin marker
        self.start_marker = self.scene.addEllipse(-5, -5, 10, 10, QPen(Qt.red), QColor(255, 0, 0))
        self.start_marker.setPos(self.start)
        
        # Draw start direction arrow (green like end arrow)
        self.dir_arrow = QGraphicsLineItem(0, 0, 30, 0)
        self.dir_arrow.setPen(QPen(QColor(0, 150, 0), 2))
        self.dir_arrow.setPos(self.start)
        self.scene.addItem(self.dir_arrow)
        
        # Path item for the belt
        self.path_item = QGraphicsPathItem()
        self.path_item.setPen(QPen(QColor(0, 200, 0), 3))
        self.scene.addItem(self.path_item)
        
        # Debug circles for the turn circles
        self.circle1 = self.scene.addEllipse(-self.radius, -self.radius, 
                                              self.radius*2, self.radius*2,
                                              QPen(QColor(255, 0, 0, 100)))
        self.circle2 = self.scene.addEllipse(-self.radius, -self.radius,
                                              self.radius*2, self.radius*2,
                                              QPen(QColor(0, 0, 255, 100)))
        
        # Tangent point markers
        self.t1_marker = self.scene.addEllipse(-4, -4, 8, 8, QPen(Qt.black), QBrush(Qt.yellow))
        self.t2_marker = self.scene.addEllipse(-4, -4, 8, 8, QPen(Qt.black), QBrush(Qt.cyan))
        
        # End point marker (blue like start marker is red)
        self.end_marker = self.scene.addEllipse(-5, -5, 10, 10, QPen(Qt.blue), QColor(0, 0, 255))
        
        # End direction arrow (follows mouse)
        self.end_arrow = QGraphicsLineItem(0, 0, 30, 0)
        self.end_arrow.setPen(QPen(QColor(0, 150, 0), 2))
        self.scene.addItem(self.end_arrow)
        
        # Debug text with dark background
        self.debug_text = QGraphicsTextItem()
        self.debug_text.setPos(-380, -380)
        self.debug_text.setDefaultTextColor(QColor(200, 255, 200))
        self.debug_text.setZValue(1000)  # On top
        self.scene.addItem(self.debug_text)
        
        # Set dark scene background so we can see everything
        self.scene.setBackgroundBrush(QBrush(QColor(40, 40, 40)))
        
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            # Rotate start direction by 45 degrees
            self.start_dir += math.pi / 4
            self._update_arrow()
        elif event.button() == Qt.RightButton:
            # Rotate end direction by 45 degrees
            self.end_dir += math.pi / 4
        super().mousePressEvent(event)
        
    def _update_arrow(self):
        """Update the direction arrow rotation."""
        # Draw arrow in start direction
        length = 30
        dx = length * math.cos(self.start_dir)
        dy = length * math.sin(self.start_dir)
        self.dir_arrow.setLine(0, 0, dx, dy)
        
    def mouseMoveEvent(self, event):
        mouse = self.mapToScene(event.pos())
        path = self._compute_clc_path(mouse)
        self.path_item.setPath(path)
        super().mouseMoveEvent(event)
    
    def _compute_clc_path(self, end: QPointF) -> QPainterPath:
        """
        Compute circle-line-circle path.
        
        The key insight: we have two turning circles (one at start, one at end).
        We need to find the tangent line between them, then draw arcs to that line.
        """
        path = QPainterPath()
        path.moveTo(self.start)
        
        # End direction: absolute (right-click rotates)
        # The arrow shows where the belt is GOING, but for routing we need
        # the direction the belt is COMING FROM (opposite)
        end_dir = self.end_dir + math.pi  # Flip for routing
        
        # Update end marker and direction arrow (arrow shows actual end_dir, not flipped)
        self.end_marker.setPos(end)
        self.end_arrow.setPos(end)
        arrow_dx = 30 * math.cos(self.end_dir)
        arrow_dy = 30 * math.sin(self.end_dir)
        self.end_arrow.setLine(0, 0, arrow_dx, arrow_dy)
        
        # Determine which way to turn at START based on where end is
        # Vector from start to end
        to_end = QPointF(end.x() - self.start.x(), end.y() - self.start.y())
        
        # Cross product with start direction tells us which side end is on
        start_dx = math.cos(self.start_dir)
        start_dy = math.sin(self.start_dir)
        start_cross = start_dx * to_end.y() - start_dy * to_end.x()
        
        # If cross > 0, end is to the left, turn left (CCW)
        # If cross < 0, end is to the right, turn right (CW)
        start_sign = 1 if start_cross >= 0 else -1  # +1 = left/CCW, -1 = right/CW
        
        # Determine which way to turn at END based on where start is
        # Vector from end to start
        to_start = QPointF(self.start.x() - end.x(), self.start.y() - end.y())
        
        # Cross product with end direction (flipped) tells us which side start is on
        end_dx = math.cos(end_dir)
        end_dy = math.sin(end_dir)
        end_cross = end_dx * to_start.y() - end_dy * to_start.x()
        
        # Same logic for end
        end_sign = 1 if end_cross >= 0 else -1
        
        # Compute circle centers
        # Perpendicular to direction, offset by radius
        start_perp = self.start_dir + start_sign * math.pi / 2
        c1 = QPointF(
            self.start.x() + self.radius * math.cos(start_perp),
            self.start.y() + self.radius * math.sin(start_perp)
        )
        
        end_perp = end_dir + end_sign * math.pi / 2
        c2 = QPointF(
            end.x() + self.radius * math.cos(end_perp),
            end.y() + self.radius * math.sin(end_perp)
        )
        
        # Update debug circles
        self.circle1.setPos(c1)
        self.circle2.setPos(c2)
        
        # Find tangent line between the two circles
        d = math.sqrt((c2.x() - c1.x())**2 + (c2.y() - c1.y())**2)
        
        if d < 0.001:
            # Centers coincide, just draw line
            path.lineTo(end)
            return path
        
        # Angle from c1 to c2
        theta = math.atan2(c2.y() - c1.y(), c2.x() - c1.x())
        
        if start_sign == end_sign:
            # OUTER tangent: same turn direction at both ends
            # Tangent points are at same angle from both centers, perpendicular to center line
            tangent_angle = theta - start_sign * math.pi / 2
            
            t1 = QPointF(
                c1.x() + self.radius * math.cos(tangent_angle),
                c1.y() + self.radius * math.sin(tangent_angle)
            )
            t2 = QPointF(
                c2.x() + self.radius * math.cos(tangent_angle),
                c2.y() + self.radius * math.sin(tangent_angle)
            )
        else:
            # INNER tangent: opposite turn directions
            # The tangent crosses between the circles
            # For equal radii, the crossing point is at the midpoint
            if d < 2 * self.radius:
                # Circles overlap too much, fall back to straight line
                path.lineTo(end)
                return path
            
            # Angle offset for inner tangent
            alpha = math.asin(2 * self.radius / d) if d > 2 * self.radius else 0
            
            # Tangent angle depends on which way we're turning
            if start_sign > 0:  # start CCW, end CW
                tangent_angle = theta + alpha
            else:  # start CW, end CCW
                tangent_angle = theta - alpha
            
            # t1 is on c1, perpendicular in start_sign direction
            t1 = QPointF(
                c1.x() + self.radius * math.cos(tangent_angle - start_sign * math.pi / 2),
                c1.y() + self.radius * math.sin(tangent_angle - start_sign * math.pi / 2)
            )
            # t2 is on c2, perpendicular in end_sign direction (opposite side)
            t2 = QPointF(
                c2.x() + self.radius * math.cos(tangent_angle + math.pi - end_sign * math.pi / 2),
                c2.y() + self.radius * math.sin(tangent_angle + math.pi - end_sign * math.pi / 2)
            )
        
        # Update tangent markers
        self.t1_marker.setPos(t1)
        self.t2_marker.setPos(t2)
        
        # Draw arc from start to t1 around c1
        self._add_arc(path, c1, self.start, t1, start_sign)
        
        # Draw line from t1 to t2
        path.lineTo(t2)
        
        # Draw arc from t2 to end around c2
        self._add_arc(path, c2, t2, end, end_sign)
        
        # Update debug text
        def deg(r): return f"{math.degrees(r):.0f}°"
        tangent_type = "OUTER" if start_sign == end_sign else "INNER"
        self.debug_text.setPlainText(
            f"start_dir: {deg(self.start_dir)}  end_dir: {deg(self.end_dir)} (routing: {deg(end_dir)})\n"
            f"start_sign: {'+CCW' if start_sign > 0 else '-CW'}  end_sign: {'+CCW' if end_sign > 0 else '-CW'}  [{tangent_type}]\n"
            f"c1: ({c1.x():.0f}, {c1.y():.0f})  c2: ({c2.x():.0f}, {c2.y():.0f})  d: {d:.0f}\n"
            f"theta (c1→c2): {deg(theta)}  tangent_angle: {deg(tangent_angle)}\n"
            f"t1: ({t1.x():.0f}, {t1.y():.0f})  t2: ({t2.x():.0f}, {t2.y():.0f})\n"
            f"start_cross: {start_cross:.1f}  end_cross: {end_cross:.1f}"
        )
        
        return path
    
    def _add_arc(self, path: QPainterPath, center: QPointF, 
                 p1: QPointF, p2: QPointF, sign: int) -> None:
        """
        Add arc from p1 to p2 around center.
        sign: +1 for CCW, -1 for CW
        """
        # Angles from center to points
        a1 = math.atan2(p1.y() - center.y(), p1.x() - center.x())
        a2 = math.atan2(p2.y() - center.y(), p2.x() - center.x())
        
        # Compute sweep
        sweep = a2 - a1
        
        # Normalize based on direction
        if sign > 0:  # CCW: sweep should be positive
            while sweep < 0:
                sweep += 2 * math.pi
            while sweep > 2 * math.pi:
                sweep -= 2 * math.pi
        else:  # CW: sweep should be negative
            while sweep > 0:
                sweep -= 2 * math.pi
            while sweep < -2 * math.pi:
                sweep += 2 * math.pi
        
        # Draw arc
        num_segments = max(8, int(abs(sweep) * self.radius / 5))
        for i in range(1, num_segments + 1):
            t = i / num_segments
            angle = a1 + t * sweep
            x = center.x() + self.radius * math.cos(angle)
            y = center.y() + self.radius * math.sin(angle)
            path.lineTo(x, y)


def main():
    app = QApplication(sys.argv)
    view = ArcTestView()
    view.setWindowTitle("Circle-Line-Circle Test - LEFT=rotate start, RIGHT=rotate end")
    view.resize(800, 800)
    view.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

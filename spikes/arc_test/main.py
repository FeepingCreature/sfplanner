"""Minimal test: draw an arc from a fixed point toward the mouse."""

import math
import sys

from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QPainter, QPen, QColor, QPainterPath
from PySide6.QtWidgets import QApplication, QGraphicsView, QGraphicsScene, QGraphicsPathItem


class ArcTestView(QGraphicsView):
    def __init__(self):
        super().__init__()
        self.scene = QGraphicsScene(self)
        self.scene.setSceneRect(-400, -400, 800, 800)
        self.setScene(self.scene)
        self.setRenderHint(QPainter.Antialiasing)
        self.setMouseTracking(True)
        
        # Fixed start point and direction
        self.start = QPointF(0, 0)
        self.start_dir = 0  # radians, pointing RIGHT
        self.radius = 50
        
        # Draw origin marker
        self.scene.addEllipse(-5, -5, 10, 10, QPen(Qt.red), QColor(255, 0, 0))
        
        # Draw start direction arrow
        arrow_len = 30
        self.scene.addLine(0, 0, arrow_len, 0, QPen(Qt.blue, 2))
        
        # Path item for the arc
        self.path_item = QGraphicsPathItem()
        self.path_item.setPen(QPen(QColor(0, 200, 0), 3))
        self.scene.addItem(self.path_item)
        
    def mouseMoveEvent(self, event):
        # Get mouse position in scene coords
        mouse = self.mapToScene(event.pos())
        
        # Compute the arc from start toward mouse
        path = self._compute_arc_path(mouse)
        self.path_item.setPath(path)
        
        super().mouseMoveEvent(event)
    
    def _compute_arc_path(self, end: QPointF) -> QPainterPath:
        """Draw arc from start point, leaving in start_dir, curving toward end."""
        path = QPainterPath()
        path.moveTo(self.start)
        
        # Direction from start to end
        dx = end.x() - self.start.x()
        dy = end.y() - self.start.y()
        target_angle = math.atan2(dy, dx)
        
        # How much do we need to turn?
        turn = target_angle - self.start_dir
        # Normalize to [-pi, pi]
        while turn > math.pi:
            turn -= 2 * math.pi
        while turn < -math.pi:
            turn += 2 * math.pi
        
        # If turn is positive, we turn CCW (in math coords) = CW in screen coords
        # If turn is negative, we turn CW (in math coords) = CCW in screen coords
        
        # Circle center is perpendicular to start direction
        # If turning right (turn < 0), center is to the right (start_dir - 90)
        # If turning left (turn > 0), center is to the left (start_dir + 90)
        if turn >= 0:
            # Turn left (CCW in math) - center is to the left
            perp = self.start_dir + math.pi / 2
        else:
            # Turn right (CW in math) - center is to the right
            perp = self.start_dir - math.pi / 2
        
        center = QPointF(
            self.start.x() + self.radius * math.cos(perp),
            self.start.y() + self.radius * math.sin(perp)
        )
        
        # Angle from center to start point
        start_angle = math.atan2(self.start.y() - center.y(), self.start.x() - center.x())
        
        # We want to arc until we're pointing at the target
        # The tangent direction at any point on the circle is perpendicular to the radius
        # We want the tangent to equal target_angle
        
        # For CCW motion: tangent = radius_angle + 90
        # For CW motion: tangent = radius_angle - 90
        # So: radius_angle = tangent -/+ 90
        
        if turn >= 0:
            # CCW: tangent = radius_angle + 90, so radius_angle = tangent - 90
            end_angle = target_angle - math.pi / 2
        else:
            # CW: tangent = radius_angle - 90, so radius_angle = tangent + 90
            end_angle = target_angle + math.pi / 2
        
        # Draw the arc
        sweep = end_angle - start_angle
        # Normalize sweep based on direction
        if turn >= 0:
            # CCW: sweep should be positive
            while sweep < 0:
                sweep += 2 * math.pi
            while sweep > 2 * math.pi:
                sweep -= 2 * math.pi
        else:
            # CW: sweep should be negative
            while sweep > 0:
                sweep -= 2 * math.pi
            while sweep < -2 * math.pi:
                sweep += 2 * math.pi
        
        # Clamp to max 180 degrees for sanity
        if abs(sweep) > math.pi:
            sweep = math.copysign(math.pi, sweep)
        
        # Draw arc as line segments
        num_segments = max(8, int(abs(sweep) * self.radius / 5))
        for i in range(1, num_segments + 1):
            t = i / num_segments
            angle = start_angle + t * sweep
            x = center.x() + self.radius * math.cos(angle)
            y = center.y() + self.radius * math.sin(angle)
            path.lineTo(x, y)
        
        # Continue with straight line to mouse
        path.lineTo(end)
        
        return path


def main():
    app = QApplication(sys.argv)
    view = ArcTestView()
    view.setWindowTitle("Arc Test - move mouse around origin")
    view.resize(800, 800)
    view.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

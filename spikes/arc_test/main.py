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
        
        Try all 4 combinations of (start CW/CCW, end CW/CCW) and pick shortest.
        """
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
        
        # Try all 4 combinations and pick shortest
        best_result = None
        best_length = float('inf')
        
        for start_sign in [-1, 1]:
            for end_sign in [-1, 1]:
                result = self._try_path(end, end_dir, start_sign, end_sign)
                if result and result['length'] < best_length:
                    best_length = result['length']
                    best_result = result
        
        if not best_result:
            # Fallback: straight line
            path = QPainterPath()
            path.moveTo(self.start)
            path.lineTo(end)
            return path
        
        # Update debug visuals with best result
        self.circle1.setPos(best_result['c1'])
        self.circle2.setPos(best_result['c2'])
        self.t1_marker.setPos(best_result['t1'])
        self.t2_marker.setPos(best_result['t2'])
        
        # Update debug text
        def deg(r): return f"{math.degrees(r):.0f}°"
        r = best_result
        tangent_type = "OUTER" if r['start_sign'] == r['end_sign'] else "INNER"
        self.debug_text.setPlainText(
            f"start_dir: {deg(self.start_dir)}  end_dir: {deg(self.end_dir)} (routing: {deg(end_dir)})\n"
            f"start_sign: {'+CCW' if r['start_sign'] > 0 else '-CW'}  end_sign: {'+CCW' if r['end_sign'] > 0 else '-CW'}  [{tangent_type}]\n"
            f"c1: ({r['c1'].x():.0f}, {r['c1'].y():.0f})  c2: ({r['c2'].x():.0f}, {r['c2'].y():.0f})  d: {r['d']:.0f}\n"
            f"t1: ({r['t1'].x():.0f}, {r['t1'].y():.0f})  t2: ({r['t2'].x():.0f}, {r['t2'].y():.0f})\n"
            f"length: {r['length']:.0f}  arc1: {deg(r['arc1_sweep'])}  arc2: {deg(r['arc2_sweep'])}"
        )
        
        return best_result['path']
    
    def _try_path(self, end: QPointF, end_dir: float, start_sign: int, end_sign: int) -> dict | None:
        """Try computing a path with given turn directions. Returns dict with path and metadata, or None."""
        
        # Compute circle centers
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
        
        # Distance between centers
        d = math.sqrt((c2.x() - c1.x())**2 + (c2.y() - c1.y())**2)
        
        if d < 0.001:
            return None
        
        # Angle from c1 to c2
        theta = math.atan2(c2.y() - c1.y(), c2.x() - c1.x())
        
        # Compute tangent points based on tangent type
        if start_sign == end_sign:
            # OUTER tangent
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
            # INNER tangent
            if d < 2 * self.radius:
                return None  # Circles overlap
            
            half_d = d / 2
            beta = math.acos(self.radius / half_d)
            
            t1_angle = theta + start_sign * beta
            t1 = QPointF(
                c1.x() + self.radius * math.cos(t1_angle),
                c1.y() + self.radius * math.sin(t1_angle)
            )
            
            t2_angle = theta + math.pi - end_sign * beta
            t2 = QPointF(
                c2.x() + self.radius * math.cos(t2_angle),
                c2.y() + self.radius * math.sin(t2_angle)
            )
        
        # Compute arc sweeps
        arc1_sweep = self._compute_sweep(c1, self.start, t1, start_sign)
        arc2_sweep = self._compute_sweep(c2, t2, end, end_sign)
        
        # Compute total length
        line_len = math.sqrt((t2.x() - t1.x())**2 + (t2.y() - t1.y())**2)
        arc1_len = abs(arc1_sweep) * self.radius
        arc2_len = abs(arc2_sweep) * self.radius
        total_length = arc1_len + line_len + arc2_len
        
        # Build the path
        path = QPainterPath()
        path.moveTo(self.start)
        self._add_arc_with_sweep(path, c1, self.start, arc1_sweep)
        path.lineTo(t2)
        self._add_arc_with_sweep(path, c2, t2, arc2_sweep)
        
        return {
            'path': path,
            'length': total_length,
            'c1': c1, 'c2': c2,
            't1': t1, 't2': t2,
            'd': d,
            'start_sign': start_sign, 'end_sign': end_sign,
            'arc1_sweep': arc1_sweep, 'arc2_sweep': arc2_sweep,
        }
    
    def _compute_sweep(self, center: QPointF, p1: QPointF, p2: QPointF, sign: int) -> float:
        """Compute sweep angle from p1 to p2 around center, respecting sign direction."""
        a1 = math.atan2(p1.y() - center.y(), p1.x() - center.x())
        a2 = math.atan2(p2.y() - center.y(), p2.x() - center.x())
        
        sweep = a2 - a1
        
        # Normalize based on required direction
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
        
        return sweep
    
    def _add_arc_with_sweep(self, path: QPainterPath, center: QPointF, start: QPointF, sweep: float) -> None:
        """Add arc starting at start, going sweep radians around center."""
        if abs(sweep) < 0.01:
            return
        
        a1 = math.atan2(start.y() - center.y(), start.x() - center.x())
        
        num_segments = max(8, int(abs(sweep) * self.radius / 5))
        for i in range(1, num_segments + 1):
            t = i / num_segments
            angle = a1 + t * sweep
            x = center.x() + self.radius * math.cos(angle)
            y = center.y() + self.radius * math.sin(angle)
            path.lineTo(x, y)
    
    def _add_arc(self, path: QPainterPath, center: QPointF, 
                 p1: QPointF, p2: QPointF, sign: int) -> None:
        """
        Add arc from p1 to p2 around center.
        sign: +1 for CCW, -1 for CW (but we actually just take the short way)
        """
        # Angles from center to points
        a1 = math.atan2(p1.y() - center.y(), p1.x() - center.x())
        a2 = math.atan2(p2.y() - center.y(), p2.x() - center.x())
        
        # Compute sweep - ALWAYS take the short way
        sweep = a2 - a1
        
        # Normalize to [-pi, pi] to get shortest path
        while sweep > math.pi:
            sweep -= 2 * math.pi
        while sweep < -math.pi:
            sweep += 2 * math.pi
        
        # Skip tiny arcs
        if abs(sweep) < 0.01:
            return
        
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

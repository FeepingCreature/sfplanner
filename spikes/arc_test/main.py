"""Circle-line-circle (Dubins path) routing test.

Left-click to rotate start direction.
Right-click to rotate end direction.
Move mouse to drag the end point.
"""

import math
import sys

from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QPainter, QPen, QColor, QPainterPath, QBrush
from PySide6.QtWidgets import QApplication, QGraphicsView, QGraphicsScene, QGraphicsPathItem, QGraphicsLineItem, QGraphicsTextItem


def get_angle(C: QPointF, p: QPointF) -> float:
    """Get angle from center C to point p."""
    return math.atan2(p.y() - C.y(), p.x() - C.x())


def get_arc_points(C: QPointF, phi_start: float, phi_end: float, ccw: bool, R: float, num_points: int = 30) -> list[QPointF]:
    """Get points along an arc."""
    if ccw:
        delta = (phi_end - phi_start + 2 * math.pi) % (2 * math.pi)
        points = []
        for i in range(num_points + 1):
            t = i / num_points * delta
            phi = phi_start + t
            points.append(QPointF(C.x() + R * math.cos(phi), C.y() + R * math.sin(phi)))
    else:
        delta = (phi_start - phi_end + 2 * math.pi) % (2 * math.pi)
        points = []
        for i in range(num_points + 1):
            t = i / num_points * delta
            phi = phi_start - t
            points.append(QPointF(C.x() + R * math.cos(phi), C.y() + R * math.sin(phi)))
    return points


def get_dubins_path(S: QPointF, theta_s: float, E: QPointF, theta_e: float, R: float) -> dict | None:
    """
    Compute optimal Dubins path (circle-line-circle).
    
    S: start point
    theta_s: start direction (radians)
    E: end point  
    theta_e: end direction (radians)
    R: turning radius
    
    Returns dict with path info or None if no valid path.
    """
    us_x, us_y = math.cos(theta_s), math.sin(theta_s)
    ue_x, ue_y = math.cos(theta_e), math.sin(theta_e)
    
    # Circle centers for left (CCW) and right (CW) turns
    # Left turn: center is 90° CCW from direction
    C1L = QPointF(S.x() + R * (-us_y), S.y() + R * us_x)
    # Right turn: center is 90° CW from direction
    C1R = QPointF(S.x() + R * us_y, S.y() + R * (-us_x))
    # Same for end
    C2L = QPointF(E.x() + R * (-ue_y), E.y() + R * ue_x)
    C2R = QPointF(E.x() + R * ue_y, E.y() + R * (-ue_x))
    
    def compute_candidate(C1: QPointF, C2: QPointF, type1: str, type2: str, external: bool) -> dict | None:
        """Compute a candidate path between two circles."""
        V_x = C2.x() - C1.x()
        V_y = C2.y() - C1.y()
        d = math.sqrt(V_x * V_x + V_y * V_y)
        
        if d < 1e-8:
            return None
            
        unit_v_x = V_x / d
        unit_v_y = V_y / d
        
        if external:
            # External tangent (LL or RR)
            if type1 == 'L' and type2 == 'L':
                # Rotate unit_v 90° CW
                n_x, n_y = unit_v_y, -unit_v_x
                P = QPointF(C1.x() + R * n_x, C1.y() + R * n_y)
                Q = QPointF(C2.x() + R * n_x, C2.y() + R * n_y)
                L_str = d
            elif type1 == 'R' and type2 == 'R':
                # Rotate unit_v 90° CCW
                n_x, n_y = -unit_v_y, unit_v_x
                P = QPointF(C1.x() + R * n_x, C1.y() + R * n_y)
                Q = QPointF(C2.x() + R * n_x, C2.y() + R * n_y)
                L_str = d
            else:
                return None
        else:
            # Internal tangent (LR or RL)
            if d < 2 * R:
                return None  # Circles overlap
            
            L_str = math.sqrt(max(0, d * d - 4 * R * R))
            
            # Use complex number math for the tangent direction
            Vc = complex(V_x, V_y)
            if type1 == 'L' and type2 == 'R':
                denom = complex(2 * R, L_str)
            elif type1 == 'R' and type2 == 'L':
                denom = complex(2 * R, -L_str)
            else:
                return None
            
            mc = Vc / denom
            m_norm = abs(mc)
            if m_norm < 1e-8:
                return None
            mc /= m_norm
            m_x, m_y = mc.real, mc.imag
            
            P = QPointF(C1.x() + R * m_x, C1.y() + R * m_y)
            Q = QPointF(C2.x() - R * m_x, C2.y() - R * m_y)
        
        # Compute arc lengths
        phi_s = get_angle(C1, S)
        phi_p = get_angle(C1, P)
        
        if type1 == 'L':
            delta1 = (phi_p - phi_s + 2 * math.pi) % (2 * math.pi)
        else:
            delta1 = (phi_s - phi_p + 2 * math.pi) % (2 * math.pi)
        arc1_len = R * delta1
        
        phi_q = get_angle(C2, Q)
        phi_e = get_angle(C2, E)
        
        if type2 == 'L':
            delta2 = (phi_e - phi_q + 2 * math.pi) % (2 * math.pi)
        else:
            delta2 = (phi_q - phi_e + 2 * math.pi) % (2 * math.pi)
        arc2_len = R * delta2
        
        # Skip degenerate paths
        if arc1_len < 1e-6 or arc2_len < 1e-6:
            return None
        
        total_len = arc1_len + L_str + arc2_len
        
        return {
            'type': type1 + type2,
            'C1': C1, 'phi1_s': phi_s, 'phi1_p': phi_p,
            'P': P, 'Q': Q, 'L_str': L_str,
            'C2': C2, 'phi2_q': phi_q, 'phi2_e': phi_e,
            'total_len': total_len,
            'arc1_len': arc1_len, 'arc2_len': arc2_len,
        }
    
    # Try all 4 combinations
    candidates = [
        compute_candidate(C1L, C2L, 'L', 'L', True),   # External LL
        compute_candidate(C1R, C2R, 'R', 'R', True),   # External RR
        compute_candidate(C1L, C2R, 'L', 'R', False),  # Internal LR
        compute_candidate(C1R, C2L, 'R', 'L', False),  # Internal RL
    ]
    
    valid = [c for c in candidates if c is not None]
    if not valid:
        return None
    
    return min(valid, key=lambda c: c['total_len'])


class ArcTestView(QGraphicsView):
    def __init__(self):
        super().__init__()
        self.scene = QGraphicsScene(self)
        self.scene.setSceneRect(-400, -400, 800, 800)
        self.setScene(self.scene)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setMouseTracking(True)
        
        # Fixed start point and direction
        self.start = QPointF(-100, 0)
        self.start_dir = 0  # radians, pointing RIGHT
        self.end_dir = 0    # absolute end direction
        self.radius = 40
        
        # Draw origin marker
        self.start_marker = self.scene.addEllipse(-5, -5, 10, 10, QPen(Qt.GlobalColor.red), QColor(255, 0, 0))
        self.start_marker.setPos(self.start)
        
        # Draw start direction arrow
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
        self.t1_marker = self.scene.addEllipse(-4, -4, 8, 8, QPen(Qt.GlobalColor.black), QBrush(Qt.GlobalColor.yellow))
        self.t2_marker = self.scene.addEllipse(-4, -4, 8, 8, QPen(Qt.GlobalColor.black), QBrush(Qt.cyan))
        
        # End point marker
        self.end_marker = self.scene.addEllipse(-5, -5, 10, 10, QPen(Qt.blue), QColor(0, 0, 255))
        
        # End direction arrow
        self.end_arrow = QGraphicsLineItem(0, 0, 30, 0)
        self.end_arrow.setPen(QPen(QColor(0, 150, 0), 2))
        self.scene.addItem(self.end_arrow)
        
        # Debug text
        self.debug_text = QGraphicsTextItem()
        self.debug_text.setPos(-380, -380)
        self.debug_text.setDefaultTextColor(QColor(200, 255, 200))
        self.debug_text.setZValue(1000)
        self.scene.addItem(self.debug_text)
        
        # Dark background
        self.scene.setBackgroundBrush(QBrush(QColor(40, 40, 40)))
        
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.start_dir += math.pi / 4
            self._update_arrow()
        elif event.button() == Qt.MouseButton.RightButton:
            self.end_dir += math.pi / 4
        super().mousePressEvent(event)
        
    def _update_arrow(self):
        length = 30
        dx = length * math.cos(self.start_dir)
        dy = length * math.sin(self.start_dir)
        self.dir_arrow.setLine(0, 0, dx, dy)
        
    def mouseMoveEvent(self, event):
        mouse = self.mapToScene(event.pos())
        self._compute_and_draw(mouse)
        super().mouseMoveEvent(event)
    
    def _compute_and_draw(self, end: QPointF):
        # Update end marker and arrow
        self.end_marker.setPos(end)
        self.end_arrow.setPos(end)
        arrow_dx = 30 * math.cos(self.end_dir)
        arrow_dy = 30 * math.sin(self.end_dir)
        self.end_arrow.setLine(0, 0, arrow_dx, arrow_dy)
        
        # Compute Dubins path
        best = get_dubins_path(self.start, self.start_dir, end, self.end_dir, self.radius)
        
        path = QPainterPath()
        path.moveTo(self.start)
        
        if best:
            # Update debug circles
            self.circle1.setPos(best['C1'])
            self.circle2.setPos(best['C2'])
            self.t1_marker.setPos(best['P'])
            self.t2_marker.setPos(best['Q'])
            
            # Draw arc 1
            ccw1 = best['type'][0] == 'L'
            arc1_points = get_arc_points(best['C1'], best['phi1_s'], best['phi1_p'], ccw1, self.radius)
            for p in arc1_points[1:]:
                path.lineTo(p)
            
            # Draw straight line
            path.lineTo(best['Q'])
            
            # Draw arc 2
            ccw2 = best['type'][1] == 'L'
            arc2_points = get_arc_points(best['C2'], best['phi2_q'], best['phi2_e'], ccw2, self.radius)
            for p in arc2_points[1:]:
                path.lineTo(p)
            
            # Debug text
            def deg(r): return f"{math.degrees(r):.0f}°"
            self.debug_text.setPlainText(
                f"start_dir: {deg(self.start_dir)}  end_dir: {deg(self.end_dir)}\n"
                f"path type: {best['type']} ({'external' if best['type'] in ['LL', 'RR'] else 'internal'})\n"
                f"C1: ({best['C1'].x():.0f}, {best['C1'].y():.0f})  C2: ({best['C2'].x():.0f}, {best['C2'].y():.0f})\n"
                f"P: ({best['P'].x():.0f}, {best['P'].y():.0f})  Q: ({best['Q'].x():.0f}, {best['Q'].y():.0f})\n"
                f"arc1: {deg(best['arc1_len']/self.radius)}  line: {best['L_str']:.0f}  arc2: {deg(best['arc2_len']/self.radius)}\n"
                f"total length: {best['total_len']:.0f}"
            )
        else:
            path.lineTo(end)
            self.debug_text.setPlainText("No valid path found")
        
        self.path_item.setPath(path)


def main():
    app = QApplication(sys.argv)
    view = ArcTestView()
    view.setWindowTitle("Dubins Path Test - LEFT=rotate start, RIGHT=rotate end")
    view.resize(800, 800)
    view.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

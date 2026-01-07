"""Belt routing using Dubins paths (circle-line-circle algorithm)."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class Point:
    """A 2D point."""

    x: float
    y: float

    def distance_to(self, other: Point) -> float:
        return math.sqrt((self.x - other.x) ** 2 + (self.y - other.y) ** 2)


@dataclass
class BeltPath:
    """A computed belt path with arcs and lines."""

    path_type: str  # 'LL', 'RR', 'LR', 'RL'

    # Start arc
    start_center: Point
    start_radius: float
    start_angle_begin: float  # radians
    start_angle_end: float

    # Middle line segment
    line_start: Point
    line_end: Point

    # End arc
    end_center: Point
    end_radius: float
    end_angle_begin: float
    end_angle_end: float

    # Total path length
    total_length: float


# Minimum turning radius for belts (in scene units)
MIN_TURN_RADIUS = 25.0


def _get_angle(center: Point, p: Point) -> float:
    """Get angle from center to point p."""
    return math.atan2(p.y - center.y, p.x - center.x)


def compute_belt_path(
    start: Point,
    start_direction: float,  # radians, direction belt leaves start
    end: Point,
    end_direction: float,  # radians, direction belt enters end
    radius: float = MIN_TURN_RADIUS,
) -> BeltPath | None:
    """
    Compute optimal Dubins path (circle-line-circle).

    Tries all 4 path types (LL, RR, LR, RL) and picks the shortest.
    """
    # If points are very close, return None (caller should handle)
    if start.distance_to(end) < radius * 0.1:
        return None

    us_x, us_y = math.cos(start_direction), math.sin(start_direction)
    ue_x, ue_y = math.cos(end_direction), math.sin(end_direction)

    # Circle centers for left (CCW) and right (CW) turns
    # Left turn: center is 90° CCW from direction (rotate by +90°)
    C1L = Point(start.x + radius * (-us_y), start.y + radius * us_x)
    # Right turn: center is 90° CW from direction (rotate by -90°)
    C1R = Point(start.x + radius * us_y, start.y + radius * (-us_x))
    # Same for end
    C2L = Point(end.x + radius * (-ue_y), end.y + radius * ue_x)
    C2R = Point(end.x + radius * ue_y, end.y + radius * (-ue_x))

    def compute_candidate(
        C1: Point, C2: Point, type1: str, type2: str, external: bool
    ) -> BeltPath | None:
        """Compute a candidate path between two circles."""
        V_x = C2.x - C1.x
        V_y = C2.y - C1.y
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
                P = Point(C1.x + radius * n_x, C1.y + radius * n_y)
                Q = Point(C2.x + radius * n_x, C2.y + radius * n_y)
                L_str = d
            elif type1 == 'R' and type2 == 'R':
                # Rotate unit_v 90° CCW
                n_x, n_y = -unit_v_y, unit_v_x
                P = Point(C1.x + radius * n_x, C1.y + radius * n_y)
                Q = Point(C2.x + radius * n_x, C2.y + radius * n_y)
                L_str = d
            else:
                return None
        else:
            # Internal tangent (LR or RL)
            if d < 2 * radius:
                return None  # Circles overlap

            L_str = math.sqrt(max(0, d * d - 4 * radius * radius))

            # Use complex number math for the tangent direction
            Vc = complex(V_x, V_y)
            if type1 == 'L' and type2 == 'R':
                denom = complex(2 * radius, L_str)
            elif type1 == 'R' and type2 == 'L':
                denom = complex(2 * radius, -L_str)
            else:
                return None

            mc = Vc / denom
            m_norm = abs(mc)
            if m_norm < 1e-8:
                return None
            mc /= m_norm
            m_x, m_y = mc.real, mc.imag

            P = Point(C1.x + radius * m_x, C1.y + radius * m_y)
            Q = Point(C2.x - radius * m_x, C2.y - radius * m_y)

        # Compute arc lengths
        phi_s = _get_angle(C1, start)
        phi_p = _get_angle(C1, P)

        if type1 == 'L':
            delta1 = (phi_p - phi_s + 2 * math.pi) % (2 * math.pi)
        else:
            delta1 = (phi_s - phi_p + 2 * math.pi) % (2 * math.pi)
        arc1_len = radius * delta1

        phi_q = _get_angle(C2, Q)
        phi_e = _get_angle(C2, end)

        if type2 == 'L':
            delta2 = (phi_e - phi_q + 2 * math.pi) % (2 * math.pi)
        else:
            delta2 = (phi_q - phi_e + 2 * math.pi) % (2 * math.pi)
        arc2_len = radius * delta2

        # Skip degenerate paths
        if arc1_len < 1e-6 or arc2_len < 1e-6:
            return None

        total_len = arc1_len + L_str + arc2_len

        return BeltPath(
            path_type=type1 + type2,
            start_center=C1,
            start_radius=radius,
            start_angle_begin=phi_s,
            start_angle_end=phi_p,
            line_start=P,
            line_end=Q,
            end_center=C2,
            end_radius=radius,
            end_angle_begin=phi_q,
            end_angle_end=phi_e,
            total_length=total_len,
        )

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

    return min(valid, key=lambda c: c.total_length)


def get_arc_points(
    center: Point,
    phi_start: float,
    phi_end: float,
    ccw: bool,
    radius: float,
    num_points: int = 20
) -> list[Point]:
    """Get points along an arc."""
    points = []
    if ccw:
        delta = (phi_end - phi_start + 2 * math.pi) % (2 * math.pi)
        for i in range(num_points + 1):
            t = i / num_points * delta
            phi = phi_start + t
            points.append(Point(center.x + radius * math.cos(phi),
                               center.y + radius * math.sin(phi)))
    else:
        delta = (phi_start - phi_end + 2 * math.pi) % (2 * math.pi)
        for i in range(num_points + 1):
            t = i / num_points * delta
            phi = phi_start - t
            points.append(Point(center.x + radius * math.cos(phi),
                               center.y + radius * math.sin(phi)))
    return points


def path_to_points(path: BeltPath, segments_per_arc: int = 20) -> list[Point]:
    """Convert a BeltPath to a list of points for drawing."""
    points: list[Point] = []

    # Determine if arcs are CCW based on path type
    ccw1 = path.path_type[0] == 'L'
    ccw2 = path.path_type[1] == 'L'

    # Start arc
    arc1 = get_arc_points(
        path.start_center, path.start_angle_begin, path.start_angle_end,
        ccw1, path.start_radius, segments_per_arc
    )
    points.extend(arc1)

    # Line segment (end point)
    points.append(path.line_end)

    # End arc
    arc2 = get_arc_points(
        path.end_center, path.end_angle_begin, path.end_angle_end,
        ccw2, path.end_radius, segments_per_arc
    )
    points.extend(arc2)

    return points

"""Belt routing using circle-line-circle algorithm."""

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

    # Start arc
    start_center: Point
    start_radius: float
    start_angle_begin: float  # radians
    start_angle_end: float
    start_clockwise: bool

    # Middle line segment
    line_start: Point
    line_end: Point

    # End arc
    end_center: Point
    end_radius: float
    end_angle_begin: float
    end_angle_end: float
    end_clockwise: bool


# Minimum turning radius for belts (in scene units)
MIN_TURN_RADIUS = 25.0


def _normalize_angle(angle: float) -> float:
    """Normalize angle to [-pi, pi]."""
    while angle > math.pi:
        angle -= 2 * math.pi
    while angle < -math.pi:
        angle += 2 * math.pi
    return angle


def compute_belt_path(
    start: Point,
    start_direction: float,  # radians, direction belt leaves start
    end: Point,
    end_direction: float,  # radians, direction belt enters end
    radius: float = MIN_TURN_RADIUS,
) -> BeltPath | None:
    """
    Compute a circle-line-circle path between two points.

    Uses outer tangent lines between the two turning circles.
    Tries all 4 combinations (left/right turn at each end) and picks the shortest.
    """
    # If points are very close, just use straight line
    dist = start.distance_to(end)
    if dist < radius * 0.5:
        return BeltPath(
            start_center=start,
            start_radius=0,
            start_angle_begin=0,
            start_angle_end=0,
            start_clockwise=True,
            line_start=start,
            line_end=end,
            end_center=end,
            end_radius=0,
            end_angle_begin=0,
            end_angle_end=0,
            end_clockwise=True,
        )

    best_path: BeltPath | None = None
    best_length = float("inf")

    # Try all 4 combinations: (start_left, end_left), (start_left, end_right), etc.
    for start_sign in [-1, 1]:  # -1 = left (CCW), 1 = right (CW)
        for end_sign in [-1, 1]:
            path = _compute_single_path(
                start, start_direction, end, end_direction, radius, start_sign, end_sign
            )
            if path:
                length = _path_length(path)
                if length < best_length:
                    best_length = length
                    best_path = path

    return best_path


def _compute_single_path(
    start: Point,
    start_dir: float,
    end: Point,
    end_dir: float,
    radius: float,
    start_sign: int,  # -1 for left/CCW, 1 for right/CW
    end_sign: int,
) -> BeltPath | None:
    """Compute a single circle-line-circle path with given turn directions."""
    # Perpendicular directions for circle centers
    start_perp = start_dir + start_sign * math.pi / 2
    end_perp = end_dir + end_sign * math.pi / 2

    # Circle centers
    c1 = Point(
        start.x + radius * math.cos(start_perp),
        start.y + radius * math.sin(start_perp),
    )
    c2 = Point(
        end.x + radius * math.cos(end_perp),
        end.y + radius * math.sin(end_perp),
    )

    # Distance between centers
    d = c1.distance_to(c2)

    # Angle from c1 to c2
    theta = math.atan2(c2.y - c1.y, c2.x - c1.x)

    # Compute tangent line
    if start_sign == end_sign:
        # Outer tangent (same turn direction)
        if d < 0.001:
            return None  # Centers too close
        # For outer tangent, the tangent line is parallel to the line between centers
        # The tangent points are perpendicular to this line, on opposite sides for CW vs CCW
        # For CW (start_sign=1): tangent is to the RIGHT of the direction from c1 to c2
        # For CCW (start_sign=-1): tangent is to the LEFT
        perp_angle = theta - start_sign * math.pi / 2
        t1 = Point(
            c1.x + radius * math.cos(perp_angle),
            c1.y + radius * math.sin(perp_angle),
        )
        t2 = Point(
            c2.x + radius * math.cos(perp_angle),
            c2.y + radius * math.sin(perp_angle),
        )
    else:
        # Inner tangent (opposite turn directions) - crosses between circles
        if d < 2 * radius:
            return None  # Circles overlap, no inner tangent
        # Angle adjustment for inner tangent
        alpha = math.asin(2 * radius / d)
        if start_sign == 1:  # start CW, end CCW
            tangent_angle = theta + alpha
        else:  # start CCW, end CW
            tangent_angle = theta - alpha
        # Tangent points are perpendicular to the tangent line direction
        t1 = Point(
            c1.x + radius * math.cos(tangent_angle - start_sign * math.pi / 2),
            c1.y + radius * math.sin(tangent_angle - start_sign * math.pi / 2),
        )
        t2 = Point(
            c2.x + radius * math.cos(tangent_angle + math.pi - end_sign * math.pi / 2),
            c2.y + radius * math.sin(tangent_angle + math.pi - end_sign * math.pi / 2),
        )

    # Compute arc angles
    # Start arc: from start point to t1 around c1
    start_angle_begin = math.atan2(start.y - c1.y, start.x - c1.x)
    start_angle_end = math.atan2(t1.y - c1.y, t1.x - c1.x)

    # End arc: from t2 to end point around c2
    end_angle_begin = math.atan2(t2.y - c2.y, t2.x - c2.x)
    end_angle_end = math.atan2(end.y - c2.y, end.x - c2.x)

    return BeltPath(
        start_center=c1,
        start_radius=radius,
        start_angle_begin=start_angle_begin,
        start_angle_end=start_angle_end,
        start_clockwise=(start_sign == 1),
        line_start=t1,
        line_end=t2,
        end_center=c2,
        end_radius=radius,
        end_angle_begin=end_angle_begin,
        end_angle_end=end_angle_end,
        end_clockwise=(end_sign == 1),
    )


def _arc_sweep(angle_begin: float, angle_end: float, clockwise: bool) -> float:
    """Calculate the actual arc sweep, accounting for direction."""
    if clockwise:
        # CW: angle decreases
        sweep = angle_begin - angle_end
        if sweep < 0:
            sweep += 2 * math.pi
    else:
        # CCW: angle increases
        sweep = angle_end - angle_begin
        if sweep < 0:
            sweep += 2 * math.pi
    return sweep


def _path_length(path: BeltPath) -> float:
    """Calculate total path length."""
    length = 0.0

    # Start arc length
    if path.start_radius > 0:
        sweep = _arc_sweep(path.start_angle_begin, path.start_angle_end, path.start_clockwise)
        # Penalize paths that loop more than 180 degrees
        if sweep > math.pi:
            length += sweep * path.start_radius * 3  # Heavy penalty
        else:
            length += sweep * path.start_radius

    # Line segment
    length += path.line_start.distance_to(path.line_end)

    # End arc length
    if path.end_radius > 0:
        sweep = _arc_sweep(path.end_angle_begin, path.end_angle_end, path.end_clockwise)
        # Penalize paths that loop more than 180 degrees
        if sweep > math.pi:
            length += sweep * path.end_radius * 3  # Heavy penalty
        else:
            length += sweep * path.end_radius

    return length


def path_to_points(path: BeltPath, segments_per_arc: int = 8) -> list[Point]:
    """Convert a BeltPath to a list of points for drawing."""
    points: list[Point] = []

    # Start arc (if radius > 0)
    if path.start_radius > 0:
        angle_range = path.start_angle_end - path.start_angle_begin
        for i in range(segments_per_arc + 1):
            t = i / segments_per_arc
            angle = path.start_angle_begin + t * angle_range
            points.append(
                Point(
                    path.start_center.x + path.start_radius * math.cos(angle),
                    path.start_center.y + path.start_radius * math.sin(angle),
                )
            )
    else:
        points.append(path.line_start)

    # Line segment
    points.append(path.line_end)

    # End arc (if radius > 0)
    if path.end_radius > 0:
        angle_range = path.end_angle_end - path.end_angle_begin
        for i in range(segments_per_arc + 1):
            t = i / segments_per_arc
            angle = path.end_angle_begin + t * angle_range
            points.append(
                Point(
                    path.end_center.x + path.end_radius * math.cos(angle),
                    path.end_center.y + path.end_radius * math.sin(angle),
                )
            )

    return points

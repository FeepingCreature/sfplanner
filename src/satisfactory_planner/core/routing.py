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

    # Middle line segment
    line_start: Point
    line_end: Point

    # End arc
    end_center: Point
    end_radius: float
    end_angle_begin: float
    end_angle_end: float


# Minimum turning radius for belts (in scene units)
# TODO: Measure actual in-game radius
MIN_TURN_RADIUS = 30.0


def compute_belt_path(
    start: Point,
    start_direction: float,  # radians, direction belt leaves start
    end: Point,
    end_direction: float,  # radians, direction belt enters end
    radius: float = MIN_TURN_RADIUS,
) -> BeltPath | None:
    """
    Compute a circle-line-circle path between two points.

    This is a simplified implementation. The full algorithm requires:
    1. Compute the two possible tangent circles at start
    2. Compute the two possible tangent circles at end
    3. Find the tangent lines between all combinations
    4. Choose the shortest valid path

    TODO: Implement full circle-line-circle routing
    For now, returns a straight line path.
    """
    # Simplified: just return straight line with placeholder arcs
    return BeltPath(
        start_center=Point(start.x, start.y),
        start_radius=0,
        start_angle_begin=0,
        start_angle_end=0,
        line_start=start,
        line_end=end,
        end_center=Point(end.x, end.y),
        end_radius=0,
        end_angle_begin=0,
        end_angle_end=0,
    )


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

"""Utilities for converting belt paths to Qt painter paths."""

from __future__ import annotations

from PySide6.QtGui import QPainterPath

from satisfactory_planner.core.routing import BeltPath, Point, get_arc_points


def belt_path_to_painter_path(
    start: Point,
    end: Point,
    belt_path: BeltPath | None,
) -> QPainterPath:
    """Convert a BeltPath to a QPainterPath for rendering.

    Args:
        start: Starting point of the path
        end: Ending point of the path
        belt_path: Computed Dubins path, or None for straight line fallback

    Returns:
        QPainterPath ready for drawing
    """
    path = QPainterPath()
    path.moveTo(start.x, start.y)

    if belt_path:
        # Determine arc directions from path type
        ccw1 = belt_path.path_type[0] == "L"
        ccw2 = belt_path.path_type[1] == "L"

        # Draw start arc
        arc1_points = get_arc_points(
            belt_path.start_center,
            belt_path.start_angle_begin,
            belt_path.start_angle_end,
            ccw1,
            belt_path.start_radius,
        )
        for p in arc1_points[1:]:
            path.lineTo(p.x, p.y)

        # Draw line segment
        path.lineTo(belt_path.line_end.x, belt_path.line_end.y)

        # Draw end arc
        arc2_points = get_arc_points(
            belt_path.end_center,
            belt_path.end_angle_begin,
            belt_path.end_angle_end,
            ccw2,
            belt_path.end_radius,
        )
        for p in arc2_points[1:]:
            path.lineTo(p.x, p.y)
    else:
        # Fallback to straight line
        path.lineTo(end.x, end.y)

    return path

"""Shared geometry helpers for PORT building positioning and rotation.

PORT buildings (PORT_IN, PORT_OUT) sit on room edges and require special
handling for rotation and positioning due to Qt's center-based rotation.

This module centralizes the math to avoid duplication and bugs.
"""

from __future__ import annotations

# PORT building dimensions (before rotation)
PORT_BASE_WIDTH = 20  # LOGISTICS_DISPLAY_SIZE // 2
PORT_BASE_HEIGHT = 40  # LOGISTICS_DISPLAY_SIZE

# Rotation angles for each room edge (degrees)
# Orients the PORT so its connector faces INTO the room
EDGE_ROTATIONS: dict[str, int] = {
    "left": 0,  # Port faces right, into room
    "right": 180,  # Port faces left, into room
    "top": 90,  # Port faces down, into room
    "bottom": 270,  # Port faces up, into room
}


def get_rotation_y_offset() -> float:
    """Get the y offset needed to compensate for Qt's center-based rotation.

    When a 20x40 rect rotates 90 degrees around its center (10, 20), the visual
    top-left shifts. This offset makes the VISUAL rect sit correctly on edges.

    Returns:
        The y offset to apply for top/bottom edge positioning.
    """
    return (PORT_BASE_WIDTH - PORT_BASE_HEIGHT) / 2  # -10


def get_rotated_dimensions(rotation: int) -> tuple[int, int]:
    """Get visual dimensions of PORT building after rotation.

    Args:
        rotation: Rotation angle in degrees (0, 90, 180, 270)

    Returns:
        (width, height) of the visual bounding box after rotation
    """
    if rotation in (90, 270):
        return (PORT_BASE_HEIGHT, PORT_BASE_WIDTH)  # 40x20
    return (PORT_BASE_WIDTH, PORT_BASE_HEIGHT)  # 20x40


def get_edge_for_rotation(rotation: int) -> str:
    """Get which edge a PORT is on based on its rotation.

    Args:
        rotation: Rotation angle in degrees

    Returns:
        Edge name: 'left', 'right', 'top', or 'bottom'
    """
    rotation_to_edge = {v: k for k, v in EDGE_ROTATIONS.items()}
    return rotation_to_edge.get(rotation, "left")

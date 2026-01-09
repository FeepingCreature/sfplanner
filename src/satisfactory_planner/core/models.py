"""Core data models for the factory planner."""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, NamedTuple, Protocol, runtime_checkable

if TYPE_CHECKING:
    pass


@runtime_checkable
class Scene(Protocol):
    """Protocol for anything that can contain buildings and belts.

    Both Document and Room implement this protocol.
    """

    buildings: dict[str, Building]
    belts: dict[str, Belt]

    def add_building(self, building: Building) -> None: ...
    def remove_building(self, building_id: str) -> Building | None: ...
    def add_belt(self, belt: Belt) -> None: ...
    def remove_belt(self, belt_id: str) -> Belt | None: ...
    def get_belts_for_building(self, building_id: str) -> list[Belt]: ...
    def is_port_connected(self, building_id: str, port_index: int, is_output: bool) -> bool: ...


class BuildingSpec(NamedTuple):
    """Specification for a building type."""

    width: int
    height: int
    num_inputs: int
    num_outputs: int
    power_mw: float


class RGB(NamedTuple):
    """RGB color tuple."""

    r: int
    g: int
    b: int


class BuildingType(Enum):
    """Types of buildings available."""

    # Production
    SMELTER = "Smelter"
    FOUNDRY = "Foundry"
    CONSTRUCTOR = "Constructor"
    ASSEMBLER = "Assembler"
    MANUFACTURER = "Manufacturer"
    REFINERY = "Refinery"
    PACKAGER = "Packager"
    BLENDER = "Blender"

    # Extraction
    MINER = "Miner"

    # Logistics
    SPLITTER = "Splitter"
    MERGER = "Merger"

    # Room ports (one input, one output each - single item type)
    PORT_IN = "Port (In)"
    PORT_OUT = "Port (Out)"

    # Source/Sink - provide or consume items "by fiat"
    SOURCE = "Source"  # Produces items at configurable rate
    SINK = "Sink"  # Consumes any items at unlimited rate


BUILDING_METADATA: dict[BuildingType, BuildingSpec] = {
    BuildingType.SMELTER: BuildingSpec(80, 60, 1, 1, 4.0),
    BuildingType.FOUNDRY: BuildingSpec(100, 80, 2, 1, 16.0),
    BuildingType.CONSTRUCTOR: BuildingSpec(80, 60, 1, 1, 4.0),
    BuildingType.ASSEMBLER: BuildingSpec(100, 80, 2, 1, 15.0),
    BuildingType.MANUFACTURER: BuildingSpec(120, 100, 4, 1, 55.0),
    BuildingType.REFINERY: BuildingSpec(120, 100, 2, 2, 30.0),
    BuildingType.PACKAGER: BuildingSpec(80, 80, 2, 2, 10.0),
    BuildingType.BLENDER: BuildingSpec(120, 100, 4, 2, 75.0),
    BuildingType.MINER: BuildingSpec(80, 80, 0, 1, 5.0),  # Power varies by tier
    BuildingType.SPLITTER: BuildingSpec(60, 60, 1, 3, 0.0),
    BuildingType.MERGER: BuildingSpec(60, 60, 3, 1, 0.0),
    # Ports: from INSIDE the room's perspective
    # PORT_IN brings items into room = source inside (0 inputs, 1 output)
    # PORT_OUT sends items out of room = sink inside (1 input, 0 outputs)
    # Half-width because they sit ON the room edge
    BuildingType.PORT_IN: BuildingSpec(20, 40, 0, 1, 0.0),
    BuildingType.PORT_OUT: BuildingSpec(20, 40, 1, 0, 0.0),
    BuildingType.SOURCE: BuildingSpec(50, 50, 0, 1, 0.0),
    BuildingType.SINK: BuildingSpec(50, 50, 1, 0, 0.0),
}

# Display size for splitter/merger (smaller than metadata size)
LOGISTICS_DISPLAY_SIZE = 40

# Default grid size for snapping
DEFAULT_GRID_SIZE = 20

# Margin around selection for outline (used for room creation)
SELECTION_MARGIN = 15

# Offset for placing ports at room edges
PORT_EDGE_OFFSET = 30

# Minimum room dimensions
MIN_ROOM_SIZE = 50

BUILDING_COLORS: dict[BuildingType, RGB] = {
    BuildingType.SMELTER: RGB(200, 100, 50),
    BuildingType.FOUNDRY: RGB(180, 80, 40),
    BuildingType.CONSTRUCTOR: RGB(80, 150, 200),
    BuildingType.ASSEMBLER: RGB(100, 180, 100),
    BuildingType.MANUFACTURER: RGB(150, 100, 180),
    BuildingType.REFINERY: RGB(120, 120, 180),
    BuildingType.PACKAGER: RGB(100, 150, 150),
    BuildingType.BLENDER: RGB(180, 150, 100),
    BuildingType.MINER: RGB(150, 120, 80),
    BuildingType.SPLITTER: RGB(200, 200, 100),
    BuildingType.MERGER: RGB(100, 200, 200),
    BuildingType.PORT_IN: RGB(220, 180, 50),  # Yellow-ish (input color)
    BuildingType.PORT_OUT: RGB(50, 200, 100),  # Green-ish (output color)
    BuildingType.SOURCE: RGB(100, 180, 255),  # Blue (infinite source)
    BuildingType.SINK: RGB(180, 100, 180),  # Purple (infinite sink)
}


def get_building_power(building_type: BuildingType) -> float:
    """Get base power consumption for a building type in MW."""
    return BUILDING_METADATA[building_type].power_mw


def get_building_io_counts(building_type: BuildingType) -> tuple[int, int]:
    """Get (num_inputs, num_outputs) for a building type."""
    spec = BUILDING_METADATA[building_type]
    return (spec.num_inputs, spec.num_outputs)


@dataclass
class ItemRate:
    """An item with a rate per minute."""

    item_id: str
    rate: float  # items per minute


@dataclass
class Recipe:
    """A crafting recipe."""

    id: str
    name: str
    building_type: BuildingType
    inputs: list[ItemRate]
    outputs: list[ItemRate]
    power_mw: float
    crafting_time: float  # seconds

    def scaled(self, clock_speed: float) -> Recipe:
        """Return recipe with rates scaled by clock speed."""
        return Recipe(
            id=self.id,
            name=self.name,
            building_type=self.building_type,
            inputs=[ItemRate(i.item_id, i.rate * clock_speed) for i in self.inputs],
            outputs=[ItemRate(o.item_id, o.rate * clock_speed) for o in self.outputs],
            power_mw=self.power_mw * (clock_speed**1.6),  # Power scaling formula
            crafting_time=self.crafting_time / clock_speed,
        )


# Miner output rates by tier (items per minute at 100% clock)
MINER_RATES = {
    1: 60,  # Mk.1
    2: 120,  # Mk.2
    3: 240,  # Mk.3
}

# Miner power by tier (MW)
MINER_POWER = {
    1: 5.0,
    2: 12.0,
    3: 30.0,
}


@dataclass
class Building:
    """A placed building in the factory."""

    id: str
    building_type: BuildingType
    x: float
    y: float
    recipe_id: str | None = None  # For production buildings
    item_id: str | None = None  # For MINER/SOURCE/SINK: the item being produced/consumed
    clock_speed: float = 1.0  # 0.01 to 2.5
    rotation: int = 0  # 0, 90, 180, 270 degrees
    tier: int = 1  # For MINER: 1, 2, or 3
    min_rate: float | None = None  # For SOURCE/SINK: minimum flow rate
    max_rate: float | None = None  # For SOURCE/SINK: maximum flow rate
    port_index: int | None = None  # For PORT_IN/PORT_OUT: which room port this corresponds to

    @property
    def width(self) -> int:
        return BUILDING_METADATA[self.building_type].width

    @property
    def height(self) -> int:
        return BUILDING_METADATA[self.building_type].height

    @property
    def num_inputs(self) -> int:
        return BUILDING_METADATA[self.building_type].num_inputs

    @property
    def num_outputs(self) -> int:
        return BUILDING_METADATA[self.building_type].num_outputs

    def _get_display_size(self) -> tuple[int, int]:
        """Get display size - smaller for logistics buildings.

        Returns the BASE size before rotation. The painter handles visual rotation.
        For bounding/snapping calculations that need rotated dimensions, use
        _get_rotated_display_size() instead.
        """
        # Splitter/Merger display at smaller square size
        if self.building_type in (BuildingType.SPLITTER, BuildingType.MERGER):
            return (LOGISTICS_DISPLAY_SIZE, LOGISTICS_DISPLAY_SIZE)
        # PORT_IN/PORT_OUT use small display size
        if self.building_type in (BuildingType.PORT_IN, BuildingType.PORT_OUT):
            return (LOGISTICS_DISPLAY_SIZE // 2, LOGISTICS_DISPLAY_SIZE)
        return (self.width, self.height)

    def _get_rotated_display_size(self) -> tuple[int, int]:
        """Get display size accounting for rotation (for bounding/snapping).

        For 90°/270° rotations, width and height are swapped.
        """
        w, h = self._get_display_size()
        if self.rotation in (90, 270):
            return (h, w)
        return (w, h)

    def get_port_layout(
        self,
    ) -> tuple[list[tuple[float, float, float]], list[tuple[float, float, float]]]:
        """Get port positions and directions for this building.

        Returns:
            (inputs, outputs) where each is a list of (x, y, angle) tuples.
            x, y are in local building coordinates (0,0 = top-left).
            angle is in degrees (0=right, 90=down, 180=left, 270=up).

        This is the single source of truth for port layout. BuildingItem
        uses this to create PortItems without needing to know building types.
        """
        w, h = self._get_display_size()

        inputs: list[tuple[float, float, float]] = []
        outputs: list[tuple[float, float, float]] = []

        if self.building_type == BuildingType.SPLITTER:
            # 1 input on left, 3 outputs on top/right/bottom
            # Half-circles face INTO building for inputs, OUT for outputs
            inputs.append((0, h / 2, 0))  # left edge, face right (into)
            outputs.append((w / 2, 0, 270))  # top edge, face up (out)
            outputs.append((w, h / 2, 0))  # right edge, face right (out)
            outputs.append((w / 2, h, 90))  # bottom edge, face down (out)

        elif self.building_type == BuildingType.MERGER:
            # 3 inputs on top/left/bottom, 1 output on right
            # Half-circles face INTO building for inputs, OUT for outputs
            inputs.append((w / 2, 0, 90))  # top edge, face down (into)
            inputs.append((0, h / 2, 0))  # left edge, face right (into)
            inputs.append((w / 2, h, 270))  # bottom edge, face up (into)
            outputs.append((w, h / 2, 0))  # right edge, face right (out)

        elif self.building_type == BuildingType.PORT_IN:
            # PORT_IN: brings items INTO the room (0 inputs, 1 output)
            # Building sits on LEFT room edge, output faces RIGHT (into room)
            # Standard layout: output on right edge, faces right
            outputs.append((w, h / 2, 0))  # right edge, center, face right

        elif self.building_type == BuildingType.PORT_OUT:
            # PORT_OUT: sends items OUT of the room (1 input, 0 outputs)
            # The input should be on the INTERIOR side of the building (away from room edge)
            # At rotation 0 (left edge): input on RIGHT side of building (x=w)
            # At rotation 180 (right edge): input on LEFT side (x=0) - but rotation handles this
            # We define at base rotation, then _rotate_port_pos handles the rest
            # Base: building on left edge, input on right side facing left (into building)
            inputs.append(
                (w, h / 2, 180)
            )  # right edge of building, face left (belt enters from right)

        else:
            # Standard layout: inputs on left edge, outputs on right edge
            # Ports are centered ON the edge (not inset)
            num_in = self.num_inputs
            num_out = self.num_outputs

            for i in range(num_in):
                spacing = h / (num_in + 1)
                y = spacing * (i + 1)
                # Input on left edge, half-circle faces RIGHT (into building)
                inputs.append((0, y, 0))

            for i in range(num_out):
                spacing = h / (num_out + 1)
                y = spacing * (i + 1)
                # Output on right edge, half-circle faces RIGHT (out of building)
                outputs.append((w, y, 0))

        return (inputs, outputs)

    def _rotate_point(self, px: float, py: float) -> tuple[float, float]:
        """Rotate a point around the building center by current rotation."""
        if self.rotation == 0:
            return (px, py)
        w, h = self._get_display_size()
        # Center of building in scene coordinates
        cx, cy = self.x + w / 2, self.y + h / 2
        # Translate to origin
        dx, dy = px - cx, py - cy
        # Rotate
        rad = math.radians(self.rotation)
        cos_r, sin_r = math.cos(rad), math.sin(rad)
        rx = dx * cos_r - dy * sin_r
        ry = dx * sin_r + dy * cos_r
        # Translate back
        return (cx + rx, cy + ry)

    def _rotate_direction(self, direction: float) -> float:
        """Rotate a direction (radians) by current rotation."""
        return direction + math.radians(self.rotation)

    def input_port_pos(self, index: int) -> tuple[float, float]:
        """Get position of input port by index (in scene coordinates)."""
        w, h = self._get_display_size()

        if self.building_type == BuildingType.SPLITTER:
            # Splitter: 1 input on left
            base_pos = (self.x, self.y + h / 2)
        elif self.building_type == BuildingType.MERGER:
            # Merger: 3 inputs on top, left, bottom
            positions = [
                (self.x + w / 2, self.y),  # top
                (self.x, self.y + h / 2),  # left
                (self.x + w / 2, self.y + h),  # bottom
            ]
            base_pos = positions[index] if index < len(positions) else positions[0]
        else:
            # Standard: inputs on left
            spacing = h / (self.num_inputs + 1)
            base_pos = (self.x, self.y + spacing * (index + 1))

        return self._rotate_point(*base_pos)

    def input_port_direction(self, index: int) -> float:
        """Get direction (radians) a belt is TRAVELING when it enters this input port."""
        if self.building_type == BuildingType.SPLITTER:
            base_dir = 0.0  # traveling right, into left side
        elif self.building_type == BuildingType.MERGER:
            # top (traveling down), left (traveling right), bottom (traveling up)
            directions = [math.pi / 2, 0.0, -math.pi / 2]
            base_dir = directions[index] if index < len(directions) else 0.0
        else:
            base_dir = 0.0  # traveling right, into left side

        return self._rotate_direction(base_dir)

    def output_port_pos(self, index: int) -> tuple[float, float]:
        """Get position of output port by index (in scene coordinates)."""
        w, h = self._get_display_size()

        if self.building_type == BuildingType.SPLITTER:
            # Splitter: 3 outputs on top, right, bottom
            positions = [
                (self.x + w / 2, self.y),  # top
                (self.x + w, self.y + h / 2),  # right
                (self.x + w / 2, self.y + h),  # bottom
            ]
            base_pos = positions[index] if index < len(positions) else positions[0]
        elif self.building_type == BuildingType.MERGER:
            # Merger: 1 output on right
            base_pos = (self.x + w, self.y + h / 2)
        else:
            # Standard: outputs on right
            spacing = h / (self.num_outputs + 1)
            base_pos = (self.x + w, self.y + spacing * (index + 1))

        return self._rotate_point(*base_pos)

    def output_port_direction(self, index: int) -> float:
        """Get direction (radians) a belt is TRAVELING when it leaves this output port."""
        if self.building_type == BuildingType.SPLITTER:
            # top (traveling up), right (traveling right), bottom (traveling down)
            directions = [-math.pi / 2, 0.0, math.pi / 2]
            base_dir = directions[index] if index < len(directions) else 0.0
        elif self.building_type == BuildingType.MERGER:
            base_dir = 0.0  # traveling right
        else:
            base_dir = 0.0  # traveling right

        return self._rotate_direction(base_dir)


# Belt capacity by tier (items per minute)
BELT_CAPACITIES = {
    1: 60,
    2: 120,
    3: 270,
    4: 480,
    5: 780,
    6: 1200,
}


@dataclass
class Belt:
    """A belt connecting two buildings."""

    id: str
    tier: int  # 1-6
    source_building_id: str
    source_port_index: int
    dest_building_id: str
    dest_port_index: int
    item_id: str | None = None  # Inferred from source

    @property
    def capacity(self) -> float:
        return BELT_CAPACITIES.get(self.tier, 60)


@dataclass
class Room:
    """A room is both a positionable item and a container (scene) for buildings.

    Rooms implement the Scene protocol - they can contain buildings, belts, and
    nested rooms. Ports are stored as buildings with PORT_IN/PORT_OUT type.
    """

    id: str
    name: str
    width: float
    height: float

    # Scene contents (coordinates relative to room origin)
    buildings: dict[str, Building] = field(default_factory=dict)
    belts: dict[str, Belt] = field(default_factory=dict)
    rooms: dict[str, Room] = field(default_factory=dict)  # Nested rooms

    def add_building(self, building: Building) -> None:
        """Add a building to this room."""
        self.buildings[building.id] = building

    def remove_building(self, building_id: str) -> Building | None:
        """Remove a building and return it."""
        return self.buildings.pop(building_id, None)

    def add_belt(self, belt: Belt) -> None:
        """Add a belt to this room."""
        self.belts[belt.id] = belt

    def remove_belt(self, belt_id: str) -> Belt | None:
        """Remove a belt and return it."""
        return self.belts.pop(belt_id, None)

    def get_belts_for_building(self, building_id: str) -> list[Belt]:
        """Get all belts connected to a building in this room."""
        return [
            b
            for b in self.belts.values()
            if b.source_building_id == building_id or b.dest_building_id == building_id
        ]

    def is_port_connected(self, building_id: str, port_index: int, is_output: bool) -> bool:
        """Check if a port already has a belt connected."""
        for belt in self.belts.values():
            if is_output:
                if belt.source_building_id == building_id and belt.source_port_index == port_index:
                    return True
            else:
                if belt.dest_building_id == building_id and belt.dest_port_index == port_index:
                    return True
        return False

    def get_belt_at_port(self, building_id: str, port_index: int, is_output: bool) -> Belt | None:
        """Get the belt connected to a specific port, or None."""
        for belt in self.belts.values():
            if is_output:
                if belt.source_building_id == building_id and belt.source_port_index == port_index:
                    return belt
            else:
                if belt.dest_building_id == building_id and belt.dest_port_index == port_index:
                    return belt
        return None

    def get_ports(self) -> list[Building]:
        """Get all port buildings in this room."""
        return [
            b
            for b in self.buildings.values()
            if b.building_type in (BuildingType.PORT_IN, BuildingType.PORT_OUT)
        ]

    def get_input_ports(self) -> list[Building]:
        """Get all PORT_IN buildings, sorted by port_index."""
        ports = [b for b in self.buildings.values() if b.building_type == BuildingType.PORT_IN]
        return sorted(ports, key=lambda p: p.port_index if p.port_index is not None else 0)

    def get_output_ports(self) -> list[Building]:
        """Get all PORT_OUT buildings, sorted by port_index."""
        ports = [b for b in self.buildings.values() if b.building_type == BuildingType.PORT_OUT]
        return sorted(ports, key=lambda p: p.port_index if p.port_index is not None else 0)

    def get_port_by_index(self, port_index: int, is_output: bool) -> Building | None:
        """Get a port building by its port_index."""
        target_type = BuildingType.PORT_OUT if is_output else BuildingType.PORT_IN
        for b in self.buildings.values():
            if b.building_type == target_type and b.port_index == port_index:
                return b
        return None

    @property
    def num_inputs(self) -> int:
        """Number of input ports on this room."""
        return len(self.get_input_ports())

    @property
    def num_outputs(self) -> int:
        """Number of output ports on this room."""
        return len(self.get_output_ports())

    def input_port_pos(self, index: int) -> tuple[float, float]:
        """Get position of input port by index (in room-local coordinates)."""
        port = self.get_port_by_index(index, is_output=False)
        if port:
            base_w, base_h = port._get_display_size()

            if port.rotation == 0:
                # Left edge
                return (port.x, port.y + base_h / 2)
            elif port.rotation == 180:
                # Right edge
                return (port.x + base_w, port.y + base_h / 2)
            elif port.rotation == 90:
                # Top edge - use same formula as _get_room_port_position
                return (port.x + base_w / 2, 0)
            else:  # 270
                # Bottom edge - use same formula as _get_room_port_position
                return (port.x + base_w / 2, self.height)
        # Fallback: distribute evenly on left edge
        spacing = self.height / (self.num_inputs + 1) if self.num_inputs > 0 else self.height / 2
        return (0, spacing * (index + 1))

    def output_port_pos(self, index: int) -> tuple[float, float]:
        """Get position of output port by index (in room-local coordinates)."""
        port = self.get_port_by_index(index, is_output=True)
        if port:
            base_w, base_h = port._get_display_size()

            if port.rotation == 0:
                # Left edge
                return (port.x, port.y + base_h / 2)
            elif port.rotation == 180:
                # Right edge
                return (port.x + base_w, port.y + base_h / 2)
            elif port.rotation == 90:
                # Top edge - use same formula as _get_room_port_position
                return (port.x + base_w / 2, 0)
            else:  # 270
                # Bottom edge - use same formula as _get_room_port_position
                return (port.x + base_w / 2, self.height)
        # Fallback: distribute evenly on right edge
        spacing = self.height / (self.num_outputs + 1) if self.num_outputs > 0 else self.height / 2
        return (self.width, spacing * (index + 1))


@dataclass
class RoomPlacement:
    """A placement of a room in a scene.

    Multiple placements can reference the same Room, creating "linked instances".
    The Room contains the content; the placement says where to render it.

    From the outside, a RoomPlacement acts like a Building - it has ports that
    belts can connect to. The port positions come from the PORT_IN/PORT_OUT
    buildings inside the room, offset by the placement position.
    """

    id: str
    room_id: str  # References a Room in document.rooms
    x: float  # Position in parent scene
    y: float

    # The parent scene - None means root document, otherwise a room_id
    parent_room_id: str | None = None

    # Cache reference to room (set by document when needed)
    _room: Room | None = None

    def get_room(self, document: Document) -> Room | None:
        """Get the Room this placement references."""
        if self._room is None or self._room.id != self.room_id:
            self._room = document.rooms.get(self.room_id)
        return self._room

    def num_inputs(self, document: Document) -> int:
        """Number of input ports on this room."""
        room = self.get_room(document)
        return room.num_inputs if room else 0

    def num_outputs(self, document: Document) -> int:
        """Number of output ports on this room."""
        room = self.get_room(document)
        return room.num_outputs if room else 0

    def input_port_pos(self, index: int, document: Document) -> tuple[float, float]:
        """Get position of input port by index (in parent scene coordinates)."""
        room = self.get_room(document)
        if room:
            local_pos = room.input_port_pos(index)
            return (self.x + local_pos[0], self.y + local_pos[1])
        return (self.x, self.y)

    def output_port_pos(self, index: int, document: Document) -> tuple[float, float]:
        """Get position of output port by index (in parent scene coordinates)."""
        room = self.get_room(document)
        if room:
            local_pos = room.output_port_pos(index)
            return (self.x + local_pos[0], self.y + local_pos[1])
        return (self.x, self.y)

    def input_port_direction(self, index: int, document: Document) -> float:
        """Get direction (radians) a belt is TRAVELING when it enters this input port."""
        import math

        room = self.get_room(document)
        if room:
            port = room.get_port_by_index(index, is_output=False)
            if port:
                # Direction based on PORT rotation (which edge it's on)
                # 0° = left edge, belt travels right (0)
                # 180° = right edge, belt travels left (π)
                # 90° = top edge, belt travels down (π/2)
                # 270° = bottom edge, belt travels up (-π/2)
                rotation_to_dir = {
                    0: 0.0,
                    180: math.pi,
                    90: math.pi / 2,
                    270: -math.pi / 2,
                }
                return rotation_to_dir.get(port.rotation, 0.0)
        return 0.0  # Fallback: traveling right

    def output_port_direction(self, index: int, document: Document) -> float:
        """Get direction (radians) a belt is TRAVELING when it leaves this output port."""
        import math

        room = self.get_room(document)
        if room:
            port = room.get_port_by_index(index, is_output=True)
            if port:
                # Direction based on PORT rotation (which edge it's on)
                # 0° = left edge, belt travels left (-π, away from room)
                # 180° = right edge, belt travels right (0, away from room)
                # 90° = top edge, belt travels up (-π/2, away from room)
                # 270° = bottom edge, belt travels down (π/2, away from room)
                rotation_to_dir = {
                    0: math.pi,  # Left edge, output goes left (out of room)
                    180: 0.0,  # Right edge, output goes right (out of room)
                    90: -math.pi / 2,  # Top edge, output goes up (out of room)
                    270: math.pi / 2,  # Bottom edge, output goes down (out of room)
                }
                return rotation_to_dir.get(port.rotation, 0.0)
        return 0.0  # Fallback: traveling right


@dataclass
class Document:
    """The root document containing all factory data.

    Document implements the Scene protocol - it can contain buildings, belts,
    and room placements at the top level.
    """

    buildings: dict[str, Building] = field(default_factory=dict)
    belts: dict[str, Belt] = field(default_factory=dict)
    recipes: dict[str, Recipe] = field(default_factory=dict)

    # Rooms and their placements
    rooms: dict[str, Room] = field(default_factory=dict)  # Room definitions
    room_placements: dict[str, RoomPlacement] = field(default_factory=dict)  # Where rooms appear

    def add_building(self, building: Building) -> None:
        """Add a building to the document."""
        self.buildings[building.id] = building

    def remove_building(self, building_id: str) -> Building | None:
        """Remove a building and return it."""
        return self.buildings.pop(building_id, None)

    def add_belt(self, belt: Belt) -> None:
        """Add a belt to the document."""
        self.belts[belt.id] = belt

    def remove_belt(self, belt_id: str) -> Belt | None:
        """Remove a belt and return it."""
        return self.belts.pop(belt_id, None)

    def get_belts_for_building(self, building_id: str) -> list[Belt]:
        """Get all belts connected to a building."""
        return [
            b
            for b in self.belts.values()
            if b.source_building_id == building_id or b.dest_building_id == building_id
        ]

    def is_port_connected(self, building_id: str, port_index: int, is_output: bool) -> bool:
        """Check if a port already has a belt connected."""
        for belt in self.belts.values():
            if is_output:
                if belt.source_building_id == building_id and belt.source_port_index == port_index:
                    return True
            else:
                if belt.dest_building_id == building_id and belt.dest_port_index == port_index:
                    return True
        return False

    def get_belt_at_port(self, building_id: str, port_index: int, is_output: bool) -> Belt | None:
        """Get the belt connected to a specific port, or None."""
        for belt in self.belts.values():
            if is_output:
                if belt.source_building_id == building_id and belt.source_port_index == port_index:
                    return belt
            else:
                if belt.dest_building_id == building_id and belt.dest_port_index == port_index:
                    return belt
        return None

    def get_placements_for_room(self, room_id: str) -> list[RoomPlacement]:
        """Get all placements of a room."""
        return [p for p in self.room_placements.values() if p.room_id == room_id]

    def get_all_rooms(self) -> list[Room]:
        """Get all rooms recursively (including nested rooms)."""
        result: list[Room] = []

        def collect(rooms: dict[str, Room]) -> None:
            for room in rooms.values():
                result.append(room)
                collect(room.rooms)

        collect(self.rooms)
        return result

    def find_building(self, building_id: str) -> Building | None:
        """Find a building by ID, searching document and all rooms."""
        # Check document first
        if building_id in self.buildings:
            return self.buildings[building_id]
        # Search all rooms
        for room in self.get_all_rooms():
            if building_id in room.buildings:
                return room.buildings[building_id]
        return None

    def find_belt(self, belt_id: str) -> Belt | None:
        """Find a belt by ID, searching document and all rooms."""
        # Check document first
        if belt_id in self.belts:
            return self.belts[belt_id]
        # Search all rooms
        for room in self.get_all_rooms():
            if belt_id in room.belts:
                return room.belts[belt_id]
        return None


def generate_id() -> str:
    """Generate a unique ID."""
    return str(uuid.uuid4())[:8]


def snap_port_to_room_edge(
    port_type: BuildingType,
    room_width: float,
    room_height: float,
    target_x: float,
    target_y: float,
) -> tuple[float, float, str]:
    """Snap a port building position to the nearest room edge.

    The building's top-left corner is positioned so the building sits ON the edge:
    - Left edge: x=0
    - Right edge: x=room_width-w
    - Top edge: y=0
    - Bottom edge: y=room_height-h

    Args:
        port_type: BuildingType.PORT_IN or PORT_OUT
        room_width: Width of the room
        room_height: Height of the room
        target_x: Desired x position (building top-left)
        target_y: Desired y position (building top-left)

    Returns:
        (x, y, edge) where edge is 'left', 'right', 'top', or 'bottom'
    """
    # Base display size for PORT buildings (before rotation)
    base_w, base_h = LOGISTICS_DISPLAY_SIZE // 2, LOGISTICS_DISPLAY_SIZE

    # Calculate distances to each edge (from approximate center)
    center_x, center_y = target_x + base_w / 2, target_y + base_h / 2
    dist_left = abs(center_x)
    dist_right = abs(center_x - room_width)
    dist_top = abs(center_y)
    dist_bottom = abs(center_y - room_height)

    min_dist = min(dist_left, dist_right, dist_top, dist_bottom)

    # On left/right edges: use normal orientation (base_w x base_h)
    # On top/bottom edges: rotated 90°/270°, so visual size is (base_h x base_w)
    if min_dist == dist_left:
        w, h = base_w, base_h
        clamped_y = max(0, min(target_y, room_height - h))
        return (0, clamped_y, "left")
    elif min_dist == dist_right:
        w, h = base_w, base_h
        clamped_y = max(0, min(target_y, room_height - h))
        return (room_width - w, clamped_y, "right")
    elif min_dist == dist_top:
        # Rotated 90°, visual dimensions swap: w=base_h, h=base_w
        w, h = base_h, base_w
        # !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
        # WARNING: DO NOT TOUCH THIS OFFSET LOGIC. IT IS CORRECT.
        # The y_offset compensates for Qt's paint rotation around (base_w/2, base_h/2).
        # When a 20x40 rect rotates 90° around its center (10, 20), the visual
        # top-left shifts. This offset makes the VISUAL rect sit on the edge.
        # It took many painful iterations to get this right. LEAVE IT ALONE.
        # !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
        y_offset = (base_w - base_h) / 2
        clamped_x = max(0, min(target_x, room_width - w))
        return (clamped_x, y_offset, "top")
    else:  # dist_bottom
        # Rotated 270°, visual dimensions swap: w=base_h, h=base_w
        w, h = base_h, base_w
        # !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
        # WARNING: DO NOT TOUCH THIS OFFSET LOGIC. IT IS CORRECT.
        # Same rotation compensation as top edge. See comment above.
        # !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
        y_offset = (base_w - base_h) / 2
        clamped_x = max(0, min(target_x, room_width - w))
        return (clamped_x, room_height - h + y_offset, "bottom")

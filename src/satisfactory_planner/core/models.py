"""Core data models for the factory planner."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING
import uuid

if TYPE_CHECKING:
    pass


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
    MINER_MK1 = "Miner Mk.1"
    MINER_MK2 = "Miner Mk.2"
    MINER_MK3 = "Miner Mk.3"

    # Logistics
    SPLITTER = "Splitter"
    MERGER = "Merger"


# Building metadata: (width, height, num_inputs, num_outputs, power_mw)
BUILDING_METADATA: dict[BuildingType, tuple[int, int, int, int, float]] = {
    BuildingType.SMELTER: (80, 60, 1, 1, 4.0),
    BuildingType.FOUNDRY: (100, 80, 2, 1, 16.0),
    BuildingType.CONSTRUCTOR: (80, 60, 1, 1, 4.0),
    BuildingType.ASSEMBLER: (100, 80, 2, 1, 15.0),
    BuildingType.MANUFACTURER: (120, 100, 4, 1, 55.0),
    BuildingType.REFINERY: (120, 100, 2, 2, 30.0),
    BuildingType.PACKAGER: (80, 80, 2, 2, 10.0),
    BuildingType.BLENDER: (120, 100, 4, 2, 75.0),
    BuildingType.MINER_MK1: (80, 80, 0, 1, 5.0),
    BuildingType.MINER_MK2: (80, 80, 0, 1, 12.0),
    BuildingType.MINER_MK3: (80, 80, 0, 1, 30.0),
    BuildingType.SPLITTER: (60, 60, 1, 3, 0.0),
    BuildingType.MERGER: (60, 60, 3, 1, 0.0),
}


def get_building_power(building_type: BuildingType) -> float:
    """Get base power consumption for a building type in MW."""
    return BUILDING_METADATA[building_type][4]


def get_building_io_counts(building_type: BuildingType) -> tuple[int, int]:
    """Get (num_inputs, num_outputs) for a building type."""
    meta = BUILDING_METADATA[building_type]
    return (meta[2], meta[3])


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


@dataclass
class Building:
    """A placed building in the factory."""

    id: str
    building_type: BuildingType
    x: float
    y: float
    recipe_id: str | None = None
    clock_speed: float = 1.0  # 0.01 to 2.5

    @property
    def width(self) -> int:
        return BUILDING_METADATA[self.building_type][0]

    @property
    def height(self) -> int:
        return BUILDING_METADATA[self.building_type][1]

    @property
    def num_inputs(self) -> int:
        return BUILDING_METADATA[self.building_type][2]

    @property
    def num_outputs(self) -> int:
        return BUILDING_METADATA[self.building_type][3]

    def _get_display_size(self) -> tuple[int, int]:
        """Get display size - smaller for logistics."""
        # Splitter/Merger display at 40x40, not the metadata 60x60
        if self.building_type in (BuildingType.SPLITTER, BuildingType.MERGER):
            return (40, 40)
        return (self.width, self.height)

    def input_port_pos(self, index: int) -> tuple[float, float]:
        """Get position of input port by index (in scene coordinates)."""
        w, h = self._get_display_size()
        
        if self.building_type == BuildingType.SPLITTER:
            # Splitter: 1 input on left
            return (self.x, self.y + h / 2)
        elif self.building_type == BuildingType.MERGER:
            # Merger: 3 inputs on top, left, bottom
            positions = [
                (self.x + w / 2, self.y),      # top
                (self.x, self.y + h / 2),       # left
                (self.x + w / 2, self.y + h),   # bottom
            ]
            return positions[index] if index < len(positions) else positions[0]
        else:
            # Standard: inputs on left
            spacing = h / (self.num_inputs + 1)
            return (self.x, self.y + spacing * (index + 1))

    def input_port_direction(self, index: int) -> float:
        """Get direction (radians) a belt is TRAVELING when it enters this input port."""
        import math
        if self.building_type == BuildingType.SPLITTER:
            return 0  # traveling right, into left side
        elif self.building_type == BuildingType.MERGER:
            # top (traveling down), left (traveling right), bottom (traveling up)
            directions = [math.pi / 2, 0, -math.pi / 2]
            return directions[index] if index < len(directions) else 0
        else:
            return 0  # traveling right, into left side

    def output_port_pos(self, index: int) -> tuple[float, float]:
        """Get position of output port by index (in scene coordinates)."""
        w, h = self._get_display_size()
        
        if self.building_type == BuildingType.SPLITTER:
            # Splitter: 3 outputs on top, right, bottom
            positions = [
                (self.x + w / 2, self.y),      # top
                (self.x + w, self.y + h / 2),   # right
                (self.x + w / 2, self.y + h),   # bottom
            ]
            return positions[index] if index < len(positions) else positions[0]
        elif self.building_type == BuildingType.MERGER:
            # Merger: 1 output on right
            return (self.x + w, self.y + h / 2)
        else:
            # Standard: outputs on right
            spacing = h / (self.num_outputs + 1)
            return (self.x + w, self.y + spacing * (index + 1))

    def output_port_direction(self, index: int) -> float:
        """Get direction (radians) a belt is TRAVELING when it leaves this output port."""
        import math
        if self.building_type == BuildingType.SPLITTER:
            # top (traveling up), right (traveling right), bottom (traveling down)
            directions = [-math.pi / 2, 0, math.pi / 2]
            return directions[index] if index < len(directions) else 0
        elif self.building_type == BuildingType.MERGER:
            return 0  # traveling right
        else:
            return 0  # traveling right


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
class Connector:
    """A connector on a building outline boundary."""

    id: str
    outline_id: str
    edge: str  # "top", "bottom", "left", "right"
    position: float  # 0.0 - 1.0 along edge
    direction: str  # "in" or "out"
    connected_belt_inside: str | None = None
    connected_belt_outside: str | None = None


@dataclass
class Outline:
    """A building outline / sub-factory boundary."""

    id: str
    x: float
    y: float
    width: float
    height: float
    children: list[str] = field(default_factory=list)  # IDs of contained items
    connectors: list[Connector] = field(default_factory=list)


@dataclass
class Document:
    """The root document containing all factory data."""

    buildings: dict[str, Building] = field(default_factory=dict)
    belts: dict[str, Belt] = field(default_factory=dict)
    outlines: dict[str, Outline] = field(default_factory=dict)
    recipes: dict[str, Recipe] = field(default_factory=dict)

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

    def is_port_connected(
        self, building_id: str, port_index: int, is_output: bool
    ) -> bool:
        """Check if a port already has a belt connected."""
        for belt in self.belts.values():
            if is_output:
                if (
                    belt.source_building_id == building_id
                    and belt.source_port_index == port_index
                ):
                    return True
            else:
                if (
                    belt.dest_building_id == building_id
                    and belt.dest_port_index == port_index
                ):
                    return True
        return False


def generate_id() -> str:
    """Generate a unique ID."""
    return str(uuid.uuid4())[:8]

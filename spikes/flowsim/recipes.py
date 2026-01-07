"""Recipe and item definitions for flow simulation."""

from dataclasses import dataclass
from enum import Enum


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


@dataclass
class Item:
    """An item type in the game."""

    id: str
    name: str
    is_fluid: bool = False


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

    def scaled(self, clock_speed: float) -> "Recipe":
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


# Belt capacity by tier (items per minute)
BELT_CAPACITIES = {
    1: 60,
    2: 120,
    3: 270,
    4: 480,
    5: 780,
    6: 1200,
}


# =============================================================================
# Example Items
# =============================================================================

ITEMS: dict[str, Item] = {
    # Ores
    "Iron Ore": Item("Iron Ore", "Iron Ore"),
    "Copper Ore": Item("Copper Ore", "Copper Ore"),
    # Ingots
    "Iron Ingot": Item("Iron Ingot", "Iron Ingot"),
    "Copper Ingot": Item("Copper Ingot", "Copper Ingot"),
    # Basic parts
    "Iron Plate": Item("Iron Plate", "Iron Plate"),
    "Iron Rod": Item("Iron Rod", "Iron Rod"),
    "Screw": Item("Screw", "Screw"),
    # Intermediate
    "Reinforced Iron Plate": Item("Reinforced Iron Plate", "Reinforced Iron Plate"),
    "Rotor": Item("Rotor", "Rotor"),
    "Modular Frame": Item("Modular Frame", "Modular Frame"),
    # Fluids
    "Water": Item("Water", "Water", is_fluid=True),
    "Crude Oil": Item("Crude Oil", "Crude Oil", is_fluid=True),
}


# =============================================================================
# Example Recipes
# =============================================================================

RECIPES: dict[str, Recipe] = {
    "Iron Ingot": Recipe(
        id="Iron Ingot",
        name="Iron Ingot",
        building_type=BuildingType.SMELTER,
        inputs=[ItemRate("Iron Ore", 30)],
        outputs=[ItemRate("Iron Ingot", 30)],
        power_mw=4,
        crafting_time=2,
    ),
    "Copper Ingot": Recipe(
        id="Copper Ingot",
        name="Copper Ingot",
        building_type=BuildingType.SMELTER,
        inputs=[ItemRate("Copper Ore", 30)],
        outputs=[ItemRate("Copper Ingot", 30)],
        power_mw=4,
        crafting_time=2,
    ),
    "Iron Plate": Recipe(
        id="Iron Plate",
        name="Iron Plate",
        building_type=BuildingType.CONSTRUCTOR,
        inputs=[ItemRate("Iron Ingot", 30)],
        outputs=[ItemRate("Iron Plate", 20)],
        power_mw=4,
        crafting_time=6,
    ),
    "Iron Rod": Recipe(
        id="Iron Rod",
        name="Iron Rod",
        building_type=BuildingType.CONSTRUCTOR,
        inputs=[ItemRate("Iron Ingot", 15)],
        outputs=[ItemRate("Iron Rod", 15)],
        power_mw=4,
        crafting_time=4,
    ),
    "Screw": Recipe(
        id="Screw",
        name="Screw",
        building_type=BuildingType.CONSTRUCTOR,
        inputs=[ItemRate("Iron Rod", 10)],
        outputs=[ItemRate("Screw", 40)],
        power_mw=4,
        crafting_time=6,
    ),
    "Reinforced Iron Plate": Recipe(
        id="Reinforced Iron Plate",
        name="Reinforced Iron Plate",
        building_type=BuildingType.ASSEMBLER,
        inputs=[
            ItemRate("Iron Plate", 30),
            ItemRate("Screw", 60),
        ],
        outputs=[ItemRate("Reinforced Iron Plate", 5)],
        power_mw=15,
        crafting_time=12,
    ),
    "Rotor": Recipe(
        id="Rotor",
        name="Rotor",
        building_type=BuildingType.ASSEMBLER,
        inputs=[
            ItemRate("Iron Rod", 20),
            ItemRate("Screw", 100),
        ],
        outputs=[ItemRate("Rotor", 4)],
        power_mw=15,
        crafting_time=15,
    ),
    "Modular Frame": Recipe(
        id="Modular Frame",
        name="Modular Frame",
        building_type=BuildingType.ASSEMBLER,
        inputs=[
            ItemRate("Reinforced Iron Plate", 3),
            ItemRate("Iron Rod", 12),
        ],
        outputs=[ItemRate("Modular Frame", 2)],
        power_mw=15,
        crafting_time=60,
    ),
}

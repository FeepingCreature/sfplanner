"""Core data models and logic.

Note: Commands have been moved to ui.commands as they are a UI concern (undo/redo).
"""

from satisfactory_planner.core.flow_models import (
    BOTTLENECK_TOLERANCE,
    FLOW_TOLERANCE,
    INFINITE_RATE,
    BuildingEfficiency,
    FlowEdge,
    FlowGraph,
    FlowNode,
    FlowPort,
    LimitingFactor,
    NodeType,
)
from satisfactory_planner.core.flow_solver import FlowSolver, Warning, WarningType
from satisfactory_planner.core.item_key import ItemKey
from satisfactory_planner.core.models import (
    BELT_CAPACITIES,
    BUILDING_COLORS,
    BUILDING_METADATA,
    DEFAULT_GRID_SIZE,
    LOGISTICS_DISPLAY_SIZE,
    MIN_ROOM_SIZE,
    PORT_EDGE_OFFSET,
    RGB,
    SELECTION_MARGIN,
    Belt,
    Building,
    BuildingSpec,
    BuildingType,
    Document,
    ItemId,
    ItemRate,
    Recipe,
    RecipeId,
    Room,
    RoomPlacement,
    Scene,
)

# VisualContainer is imported where needed, not re-exported from core
from satisfactory_planner.core.persistence import (
    delete_blueprint,
    load_all_recipes,
    load_base_recipes,
    load_blueprint,
    load_blueprints,
    load_document,
    load_user_recipes,
    save_blueprint,
    save_document,
    save_user_recipes,
)

__all__ = [
    # Constants
    "BELT_CAPACITIES",
    "BOTTLENECK_TOLERANCE",
    "BUILDING_COLORS",
    "BUILDING_METADATA",
    "DEFAULT_GRID_SIZE",
    "FLOW_TOLERANCE",
    "INFINITE_RATE",
    "LOGISTICS_DISPLAY_SIZE",
    "MIN_ROOM_SIZE",
    "PORT_EDGE_OFFSET",
    "SELECTION_MARGIN",
    # Models
    "Belt",
    "Building",
    "BuildingEfficiency",
    "BuildingSpec",
    "BuildingType",
    "Document",
    "FlowEdge",
    "FlowGraph",
    "ItemKey",
    "FlowNode",
    "FlowPort",
    "FlowSolver",
    "ItemId",
    "ItemRate",
    "LimitingFactor",
    "NodeType",
    "Recipe",
    "RecipeId",
    "RGB",
    "Room",
    "RoomPlacement",
    "Scene",
    "Warning",
    "WarningType",
    # Persistence
    "delete_blueprint",
    "load_all_recipes",
    "load_base_recipes",
    "load_blueprint",
    "load_blueprints",
    "load_document",
    "load_user_recipes",
    "save_blueprint",
    "save_document",
    "save_user_recipes",
]

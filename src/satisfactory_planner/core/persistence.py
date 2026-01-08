"""Persistence utilities for saving/loading documents and user data."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from satisfactory_planner.core.models import (
    Belt,
    Building,
    BuildingType,
    Document,
    ItemRate,
    Recipe,
    Room,
    RoomPlacement,
)


def get_user_data_dir() -> Path:
    """Get XDG user data directory for the application."""
    xdg_data_home = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg_data_home) if xdg_data_home else Path.home() / ".local" / "share"

    app_dir = base / "satisfactory-planner"
    app_dir.mkdir(parents=True, exist_ok=True)
    return app_dir


def get_user_recipes_path() -> Path:
    """Get path to user recipes file."""
    return get_user_data_dir() / "user_recipes.json"


# --- Recipe Serialization ---


def recipe_to_dict(recipe: Recipe) -> dict[str, Any]:
    """Serialize a Recipe to a dictionary."""
    return {
        "id": recipe.id,
        "name": recipe.name,
        "building_type": recipe.building_type.value,
        "inputs": [{"item_id": ir.item_id, "rate": ir.rate} for ir in recipe.inputs],
        "outputs": [{"item_id": ir.item_id, "rate": ir.rate} for ir in recipe.outputs],
        "power_mw": recipe.power_mw,
        "crafting_time": recipe.crafting_time,
    }


def dict_to_recipe(data: dict[str, Any]) -> Recipe:
    """Deserialize a Recipe from a dictionary."""
    # Find building type by value
    building_type = BuildingType.SMELTER  # default
    for bt in BuildingType:
        if bt.value == data["building_type"]:
            building_type = bt
            break

    return Recipe(
        id=data["id"],
        name=data["name"],
        building_type=building_type,
        inputs=[ItemRate(ir["item_id"], ir["rate"]) for ir in data.get("inputs", [])],
        outputs=[ItemRate(ir["item_id"], ir["rate"]) for ir in data.get("outputs", [])],
        power_mw=data.get("power_mw", 0),
        crafting_time=data.get("crafting_time", 1.0),
    )


def load_base_recipes() -> dict[str, Recipe]:
    """Load base game recipes from recipes.json."""
    import importlib.resources

    try:
        # Load from package data
        files = importlib.resources.files("satisfactory_planner.data")
        recipes_file = files.joinpath("recipes.json")
        data = json.loads(recipes_file.read_text())

        recipes = {}
        for recipe_data in data.get("recipes", []):
            recipe = dict_to_recipe(recipe_data)
            recipes[recipe.id] = recipe
        return recipes
    except (json.JSONDecodeError, KeyError, TypeError, FileNotFoundError):
        return {}


def load_user_recipes() -> dict[str, Recipe]:
    """Load user recipes from XDG data directory."""
    path = get_user_recipes_path()
    if not path.exists():
        return {}

    try:
        data = json.loads(path.read_text())
        recipes = {}
        for recipe_data in data.get("recipes", []):
            recipe = dict_to_recipe(recipe_data)
            recipes[recipe.id] = recipe
        return recipes
    except (json.JSONDecodeError, KeyError, TypeError):
        return {}


def load_all_recipes() -> dict[str, Recipe]:
    """Load all recipes (base game + user recipes).

    User recipes override base recipes with the same ID.
    """
    recipes = load_base_recipes()
    recipes.update(load_user_recipes())
    return recipes


def save_user_recipes(recipes: dict[str, Recipe]) -> None:
    """Save user recipes to XDG data directory."""
    path = get_user_recipes_path()
    data = {
        "version": 1,
        "recipes": [recipe_to_dict(r) for r in recipes.values()],
    }
    path.write_text(json.dumps(data, indent=2))


# --- Building Serialization ---


def building_to_dict(building: Building) -> dict[str, Any]:
    """Serialize a Building to a dictionary."""
    return {
        "id": building.id,
        "building_type": building.building_type.value,
        "x": building.x,
        "y": building.y,
        "recipe_id": building.recipe_id,
        "clock_speed": building.clock_speed,
        "rotation": building.rotation,
    }


def dict_to_building(data: dict[str, Any]) -> Building:
    """Deserialize a Building from a dictionary."""
    building_type = BuildingType.SMELTER
    for bt in BuildingType:
        if bt.value == data["building_type"]:
            building_type = bt
            break

    return Building(
        id=data["id"],
        building_type=building_type,
        x=data["x"],
        y=data["y"],
        recipe_id=data.get("recipe_id"),
        clock_speed=data.get("clock_speed", 1.0),
        rotation=data.get("rotation", 0),
    )


# --- Belt Serialization ---


def belt_to_dict(belt: Belt) -> dict[str, Any]:
    """Serialize a Belt to a dictionary."""
    return {
        "id": belt.id,
        "tier": belt.tier,
        "source_building_id": belt.source_building_id,
        "source_port_index": belt.source_port_index,
        "dest_building_id": belt.dest_building_id,
        "dest_port_index": belt.dest_port_index,
        "item_id": belt.item_id,
    }


def dict_to_belt(data: dict[str, Any]) -> Belt:
    """Deserialize a Belt from a dictionary."""
    return Belt(
        id=data["id"],
        tier=data.get("tier", 1),
        source_building_id=data["source_building_id"],
        source_port_index=data["source_port_index"],
        dest_building_id=data["dest_building_id"],
        dest_port_index=data["dest_port_index"],
        item_id=data.get("item_id"),
    )


# --- Document Serialization ---


def document_to_dict(
    document: Document, view_state: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Serialize a Document to a dictionary."""
    data: dict[str, Any] = {
        "version": 2,
        "buildings": [building_to_dict(b) for b in document.buildings.values()],
        "belts": [belt_to_dict(b) for b in document.belts.values()],
        "recipes": [recipe_to_dict(r) for r in document.recipes.values()],
        "rooms": {rid: room_to_dict(r) for rid, r in document.rooms.items()},
        "room_placements": {
            pid: placement_to_dict(p) for pid, p in document.room_placements.items()
        },
    }
    if view_state:
        data["view"] = view_state
    return data


def dict_to_document(data: dict[str, Any]) -> tuple[Document, dict[str, Any] | None]:
    """Deserialize a Document from a dictionary.

    Returns:
        Tuple of (document, view_state) where view_state may be None.
    """
    doc = Document()

    for building_data in data.get("buildings", []):
        building = dict_to_building(building_data)
        doc.buildings[building.id] = building

    for belt_data in data.get("belts", []):
        belt = dict_to_belt(belt_data)
        doc.belts[belt.id] = belt

    for recipe_data in data.get("recipes", []):
        recipe = dict_to_recipe(recipe_data)
        doc.recipes[recipe.id] = recipe

    # v2+: load rooms and placements
    for rid, room_data in data.get("rooms", {}).items():
        doc.rooms[rid] = dict_to_room(room_data)

    for pid, placement_data in data.get("room_placements", {}).items():
        doc.room_placements[pid] = dict_to_placement(placement_data)

    view_state = data.get("view")
    return doc, view_state


def save_document(
    document: Document, path: Path | str, view_state: dict[str, Any] | None = None
) -> None:
    """Save a document to a .sfp file."""
    path = Path(path)
    data = document_to_dict(document, view_state)
    path.write_text(json.dumps(data, indent=2))


def load_document(path: Path | str) -> tuple[Document, dict[str, Any] | None]:
    """Load a document from a .sfp file.

    Returns:
        Tuple of (document, view_state) where view_state may be None.
    """
    path = Path(path)
    data = json.loads(path.read_text())
    return dict_to_document(data)


# --- Room Serialization ---


def room_to_dict(room: Room) -> dict[str, Any]:
    """Serialize a Room to a dictionary (recursive for nested rooms)."""
    return {
        "id": room.id,
        "name": room.name,
        "width": room.width,
        "height": room.height,
        "buildings": {bid: building_to_dict(b) for bid, b in room.buildings.items()},
        "belts": {bid: belt_to_dict(b) for bid, b in room.belts.items()},
        "rooms": {rid: room_to_dict(r) for rid, r in room.rooms.items()},
    }


def dict_to_room(data: dict[str, Any]) -> Room:
    """Deserialize a Room from a dictionary."""
    room = Room(
        id=data["id"],
        name=data["name"],
        width=data["width"],
        height=data["height"],
    )
    for bid, bdata in data.get("buildings", {}).items():
        room.buildings[bid] = dict_to_building(bdata)
    for bid, bdata in data.get("belts", {}).items():
        room.belts[bid] = dict_to_belt(bdata)
    for rid, rdata in data.get("rooms", {}).items():
        room.rooms[rid] = dict_to_room(rdata)
    return room


def placement_to_dict(placement: RoomPlacement) -> dict[str, Any]:
    """Serialize a RoomPlacement to a dictionary."""
    return {
        "id": placement.id,
        "room_id": placement.room_id,
        "x": placement.x,
        "y": placement.y,
        "parent_room_id": placement.parent_room_id,
    }


def dict_to_placement(data: dict[str, Any]) -> RoomPlacement:
    """Deserialize a RoomPlacement from a dictionary."""
    return RoomPlacement(
        id=data["id"],
        room_id=data["room_id"],
        x=data["x"],
        y=data["y"],
        parent_room_id=data.get("parent_room_id"),
    )


# --- Blueprint Library ---


def get_blueprints_dir() -> Path:
    """Get directory for blueprint files."""
    blueprints_dir = get_user_data_dir() / "blueprints"
    blueprints_dir.mkdir(parents=True, exist_ok=True)
    return blueprints_dir


def _sanitize_filename(name: str) -> str:
    """Sanitize a name for use as a filename."""
    # Replace problematic characters with underscores
    invalid_chars = '<>:"/\\|?*'
    result = name
    for char in invalid_chars:
        result = result.replace(char, "_")
    # Collapse multiple underscores and strip
    while "__" in result:
        result = result.replace("__", "_")
    return result.strip("_") or "blueprint"


def save_blueprint(room: Room, name: str | None = None) -> Path:
    """Save a room as a blueprint to user library.

    Args:
        room: The room to save as a blueprint
        name: Optional name override (defaults to room.name)

    Returns:
        Path to the saved blueprint file
    """
    blueprint_name = name or room.name
    filename = _sanitize_filename(blueprint_name) + ".json"
    path = get_blueprints_dir() / filename

    # Handle name collisions by appending number
    counter = 1
    while path.exists():
        filename = f"{_sanitize_filename(blueprint_name)}_{counter}.json"
        path = get_blueprints_dir() / filename
        counter += 1

    data = {
        "version": "1.0.0",
        "name": blueprint_name,
        "room": room_to_dict(room),
    }
    path.write_text(json.dumps(data, indent=2))
    return path


def load_blueprint(path: Path) -> tuple[Room, str]:
    """Load a single blueprint from a file.

    Returns:
        Tuple of (room, display_name)
    """
    data = json.loads(path.read_text())
    room = dict_to_room(data["room"])
    name = data.get("name", room.name)
    return room, name


def load_blueprints() -> list[tuple[Room, str, Path]]:
    """Load all blueprints from user library.

    Returns:
        List of (room, display_name, file_path) tuples
    """
    blueprints_dir = get_blueprints_dir()
    blueprints: list[tuple[Room, str, Path]] = []

    for path in sorted(blueprints_dir.glob("*.json")):
        try:
            room, name = load_blueprint(path)
            blueprints.append((room, name, path))
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            # Skip invalid blueprint files
            import logging

            logging.getLogger(__name__).warning(f"Failed to load blueprint {path}: {e}")

    return blueprints


def delete_blueprint(path: Path) -> bool:
    """Delete a blueprint file.

    Returns:
        True if deleted, False if file didn't exist
    """
    if path.exists():
        path.unlink()
        return True
    return False

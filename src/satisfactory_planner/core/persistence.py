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
)


def get_user_data_dir() -> Path:
    """Get XDG user data directory for the application."""
    xdg_data_home = os.environ.get("XDG_DATA_HOME")
    if xdg_data_home:
        base = Path(xdg_data_home)
    else:
        base = Path.home() / ".local" / "share"

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

def document_to_dict(document: Document, view_state: dict[str, Any] | None = None) -> dict[str, Any]:
    """Serialize a Document to a dictionary."""
    data: dict[str, Any] = {
        "version": 1,
        "buildings": [building_to_dict(b) for b in document.buildings.values()],
        "belts": [belt_to_dict(b) for b in document.belts.values()],
        "recipes": [recipe_to_dict(r) for r in document.recipes.values()],
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

    view_state = data.get("view")
    return doc, view_state


def save_document(document: Document, path: Path | str, view_state: dict[str, Any] | None = None) -> None:
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

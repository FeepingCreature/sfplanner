"""Recipe definition."""

from dataclasses import dataclass, field
from typing import Optional
import json


@dataclass
class Recipe:
    """
    Represents a production recipe.
    
    Recipes transform inputs into outputs at specified rates.
    Rates are in items per minute.
    """
    name: str
    inputs: dict[str, float] = field(default_factory=dict)   # item_name -> items/min
    outputs: dict[str, float] = field(default_factory=dict)  # item_name -> items/min
    description: str = ""
    
    def __hash__(self):
        return hash(self.name)
    
    def __eq__(self, other):
        if isinstance(other, Recipe):
            return self.name == other.name
        return False
    
    def scaled(self, factor: float) -> 'Recipe':
        """Return a copy of this recipe with rates scaled by factor."""
        return Recipe(
            name=self.name,
            inputs={k: v * factor for k, v in self.inputs.items()},
            outputs={k: v * factor for k, v in self.outputs.items()},
            description=self.description,
        )
    
    def to_dict(self) -> dict:
        return {
            'name': self.name,
            'inputs': self.inputs.copy(),
            'outputs': self.outputs.copy(),
            'description': self.description,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Recipe':
        return cls(
            name=data['name'],
            inputs=data.get('inputs', {}),
            outputs=data.get('outputs', {}),
            description=data.get('description', ''),
        )


class RecipeRegistry:
    """Central registry for all recipes."""
    
    def __init__(self):
        self._recipes: dict[str, Recipe] = {}
        self._disabled: set[str] = set()  # Names of disabled recipes
    
    def is_disabled(self, name: str) -> bool:
        """Check if a recipe is disabled."""
        return name in self._disabled
    
    def set_disabled(self, name: str, disabled: bool) -> None:
        """Enable or disable a recipe."""
        if disabled:
            self._disabled.add(name)
        else:
            self._disabled.discard(name)
    
    def enabled_recipes(self) -> list[Recipe]:
        """Return all enabled (non-disabled) recipes."""
        return [r for r in self._recipes.values() if r.name not in self._disabled]
    
    def disabled_recipe_names(self) -> set[str]:
        """Return names of all disabled recipes."""
        return self._disabled.copy()
    
    def register(self, recipe: Recipe) -> None:
        """Register a recipe."""
        self._recipes[recipe.name] = recipe
    
    def unregister(self, name: str) -> None:
        """Remove a recipe."""
        if name in self._recipes:
            del self._recipes[name]
    
    def get(self, name: str) -> Optional[Recipe]:
        """Get a recipe by name."""
        return self._recipes.get(name)
    
    def all_recipes(self) -> list[Recipe]:
        """Return all registered recipes."""
        return list(self._recipes.values())
    
    def recipes_producing(self, item_name: str) -> list[Recipe]:
        """Find all recipes that produce a given item."""
        return [r for r in self._recipes.values() if item_name in r.outputs]
    
    def recipes_consuming(self, item_name: str) -> list[Recipe]:
        """Find all recipes that consume a given item."""
        return [r for r in self._recipes.values() if item_name in r.inputs]
    
    def to_list(self) -> list[dict]:
        return [recipe.to_dict() for recipe in self._recipes.values()]
    
    def load_from_list(self, data: list[dict]) -> None:
        self._recipes.clear()
        for recipe_data in data:
            recipe = Recipe.from_dict(recipe_data)
            self._recipes[recipe.name] = recipe
        # Clean up disabled set to only include recipes that still exist
        self._disabled = self._disabled & set(self._recipes.keys())
    
    def save_to_file(self, filepath: str) -> None:
        """Save recipes to a JSON file."""
        with open(filepath, 'w') as f:
            json.dump(self.to_list(), f, indent=2)
    
    def load_from_file(self, filepath: str) -> None:
        """Load recipes from a JSON file."""
        with open(filepath, 'r') as f:
            data = json.load(f)
        self.load_from_list(data)

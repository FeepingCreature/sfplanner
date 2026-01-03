"""Item type definition."""

from dataclasses import dataclass, field
from typing import Optional
import json


@dataclass
class Item:
    """Represents an item type in Satisfactory."""
    name: str
    description: str = ""
    
    def __hash__(self):
        return hash(self.name)
    
    def __eq__(self, other):
        if isinstance(other, Item):
            return self.name == other.name
        return False
    
    def to_dict(self) -> dict:
        return {
            'name': self.name,
            'description': self.description,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Item':
        return cls(
            name=data['name'],
            description=data.get('description', ''),
        )


class ItemRegistry:
    """Central registry for all item types."""
    
    def __init__(self):
        self._items: dict[str, Item] = {}
    
    def register(self, item: Item) -> None:
        """Register an item type."""
        self._items[item.name] = item
    
    def get(self, name: str) -> Optional[Item]:
        """Get an item by name."""
        return self._items.get(name)
    
    def get_or_create(self, name: str) -> Item:
        """Get an item by name, creating it if it doesn't exist."""
        if name not in self._items:
            self._items[name] = Item(name=name)
        return self._items[name]
    
    def all_items(self) -> list[Item]:
        """Return all registered items."""
        return list(self._items.values())
    
    def to_list(self) -> list[dict]:
        return [item.to_dict() for item in self._items.values()]
    
    def load_from_list(self, data: list[dict]) -> None:
        self._items.clear()
        for item_data in data:
            item = Item.from_dict(item_data)
            self._items[item.name] = item

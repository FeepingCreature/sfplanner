# Room & Blueprint System Design

## Overview

Rooms are groupings of buildings that act as a single movable unit while remaining transparent - you can see and interact with their contents directly. A Room is simultaneously a **Building** (has position, can be moved, has ports) and a **Scene** (contains buildings, belts, handles its own events).

**Key insight**: A room is a "window into a different scene." When you interact with items inside a room, you're interacting with that scene. Belts cannot cross room boundaries - they must go through Ports.

## Key Design Principles

1. **Ports are buildings inside the room** - From inside, a port is a building you connect belts to. From outside, ports are properties of the RoomItem that appear on its boundary.

2. **Commands receive document at execute time** - Commands don't store `document` as a field. They store a `scene_room_id` and receive `document` as an argument to `execute(document)`/`undo(document)`. This keeps commands serializable and avoids stale references. Commands close over the canvas (for UI updates) but look up data through the document.

3. **Linked rooms are ONE room rendered multiple times** - There's only one Room object in the data model. Each "instance" is a `RoomPlacement` that says where to render that room. Edits happen once to the single Room. Flow analysis later disaggregates for solving (that's why flow results are shown as an overlay - flow analysis ignores room structure).

4. **Room names are just the name** - No instance numbers in the data model. Delinking creates "Copy of {name}" Windows-style.

## Core Concepts

### Scene Protocol

Both `Document` and `Room` implement a common `Scene` interface:

```python
class Scene(Protocol):
    """Anything that can contain buildings and belts."""
    buildings: dict[str, Building]
    belts: dict[str, Belt]
    rooms: dict[str, Room]
    
    def add_building(self, building: Building) -> None: ...
    def remove_building(self, building_id: str) -> Building | None: ...
    def add_belt(self, belt: Belt) -> None: ...
    def remove_belt(self, belt_id: str) -> Belt | None: ...
    def get_belts_for_building(self, building_id: str) -> list[Belt]: ...
```

### Scene-Local Operations

**All operations are scene-local.** A building belongs to exactly one scene. A belt connects two buildings in the same scene. You cannot:
- Select items across different scenes
- Draw a belt from a building in one scene to a building in another
- Move a building from one scene to another (except via room creation/dissolution)

This simplifies everything - no cross-scene coordination needed.

### Items Know Their Scene

Every graphics item knows which scene it belongs to:

```python
class BuildingItem(QGraphicsRectItem):
    def __init__(self, building: Building, scene: Scene, canvas: FactoryCanvas):
        self.building = building
        self.scene = scene  # Room or Document - where this building lives
        self.canvas = canvas  # For screen-space stuff (grid snap, etc.)
```

When a building moves, it asks its scene for connected belts:

```python
# In BuildingItem.itemChange (after position changes):
self.canvas.update_belts_for_building(self.building.id, self.scene)
```

And the canvas method is scene-aware:

```python
def update_belts_for_building(self, building_id: str, scene: Scene) -> None:
    """Redraw belts connected to a building within its scene."""
    for belt in scene.get_belts_for_building(building_id):
        belt_item = self._belt_items.get(belt.id)
        if belt_item:
            source = scene.buildings.get(belt.source_building_id)
            dest = scene.buildings.get(belt.dest_building_id)
            if source and dest:
                belt_item.update_path(source, dest)
```

## Data Model

### Room

```python
@dataclass
class Room:
    """A room is both a positionable item and a container (scene) for buildings."""
    id: str
    name: str
    width: float
    height: float
    
    # Scene contents (coordinates relative to room origin)
    buildings: dict[str, Building] = field(default_factory=dict)
    belts: dict[str, Belt] = field(default_factory=dict)
    rooms: dict[str, Room] = field(default_factory=dict)  # Nested rooms
    
    # Ports are buildings inside the room, stored in buildings dict
    # They have a special BuildingType.PORT type
    
    # Scene protocol methods
    def add_building(self, building: Building) -> None:
        self.buildings[building.id] = building
    
    def remove_building(self, building_id: str) -> Building | None:
        return self.buildings.pop(building_id, None)
    
    def add_belt(self, belt: Belt) -> None:
        self.belts[belt.id] = belt
    
    def remove_belt(self, belt_id: str) -> Belt | None:
        return self.belts.pop(belt_id, None)
    
    def get_belts_for_building(self, building_id: str) -> list[Belt]:
        return [
            b for b in self.belts.values()
            if b.source_building_id == building_id or b.dest_building_id == building_id
        ]
```

### Port (as Building)

Ports are buildings with `BuildingType.PORT`. They live inside the room's `buildings` dict like any other building, but have special behavior:

```python
# In BuildingType enum:
PORT_IN = "Port (In)"    # Flow enters room
PORT_OUT = "Port (Out)"  # Flow exits room

# Port buildings have these properties:
# - Constrained to room boundary (edge + position along edge)
# - One input port, one output port (opposite sides)
# - From inside: connect belt to port like any building
# - From outside: RoomItem exposes ports on its boundary
```

Port position is stored in the Building's x,y but constrained to the boundary. The `edge` and `position` can be computed from x,y given the room dimensions, or stored as extra fields.

### RoomPlacement

Since linked rooms are ONE room rendered multiple times, we separate the Room (content) from its placements:

```python
@dataclass
class RoomPlacement:
    """A placement of a room in a scene. Multiple placements can reference the same Room."""
    id: str
    room_id: str  # References a Room in document.rooms
    x: float      # Position in parent scene
    y: float
    
    # The parent scene - None means root document
    parent_scene_id: str | None = None
```

### Document Updates

```python
@dataclass
class Document:
    """Root document - implements Scene protocol."""
    buildings: dict[str, Building] = field(default_factory=dict)
    belts: dict[str, Belt] = field(default_factory=dict)
    recipes: dict[str, Recipe] = field(default_factory=dict)
    
    # Rooms are stored separately from their placements
    rooms: dict[str, Room] = field(default_factory=dict)  # Room definitions
    room_placements: dict[str, RoomPlacement] = field(default_factory=dict)  # Where rooms appear
    
    # Scene protocol methods (same as Room)
    def add_building(self, building: Building) -> None: ...
    def remove_building(self, building_id: str) -> Building | None: ...
    def add_belt(self, belt: Belt) -> None: ...
    def remove_belt(self, belt_id: str) -> Belt | None: ...
    def get_belts_for_building(self, building_id: str) -> list[Belt]: ...
    
    def get_placements_for_room(self, room_id: str) -> list[RoomPlacement]:
        """Get all placements of a room."""
        return [p for p in self.room_placements.values() if p.room_id == room_id]
```

## UI Architecture

### RoomItem

A `RoomItem` renders a `RoomPlacement`. It displays the Room's contents at the placement's position.

```python
class RoomItem(QGraphicsRectItem):
    """A room placement on the canvas - contains child items for its contents."""
    
    def __init__(self, placement: RoomPlacement, room: Room, parent_scene: Scene, canvas: FactoryCanvas):
        super().__init__()
        self.placement = placement  # Where this instance is positioned
        self.room = room            # The room content (may be shared by multiple RoomItems)
        self.parent_scene = parent_scene
        self.canvas = canvas
        
        # Visual setup - rect is in local coords (0,0 to width,height)
        self.setRect(0, 0, room.width, room.height)
        self.setPos(placement.x, placement.y)  # Position from placement, not room
        
        # Flags for selection/movement in parent scene
        self.setFlag(ItemIsSelectable)
        self.setFlag(ItemIsMovable)
        
        # Child items (all parented to this item for coordinate transform)
        self._building_items: dict[str, BuildingItem] = {}
        self._belt_items: dict[str, BeltItem] = {}
        self._room_items: dict[str, RoomItem] = {}
        self._port_items: dict[str, PortItem] = {}
        
        self._populate_children()
    
    def _populate_children(self):
        """Create child graphics items for room contents."""
        # Buildings - note: scene=self.room, not self.parent_scene
        for building in self.room.buildings.values():
            item = BuildingItem(building, scene=self.room, canvas=self.canvas)
            item.setParentItem(self)  # Qt parent = coordinate transform
            self._building_items[building.id] = item
        
        # Belts
        for belt in self.room.belts.values():
            source = self.room.buildings.get(belt.source_building_id)
            dest = self.room.buildings.get(belt.dest_building_id)
            if source and dest:
                item = BeltItem(belt, source, dest)
                item.setParentItem(self)
                self._belt_items[belt.id] = item
        
        # Nested room placements (recursive)
        # Note: nested placements reference rooms in document.rooms
        for placement in self._get_nested_placements():
            nested_room = self.canvas.document.rooms[placement.room_id]
            item = RoomItem(placement, nested_room, parent_scene=self.room, canvas=self.canvas)
            item.setParentItem(self)
            self._room_items[placement.id] = item
        
        # Ports are just buildings with PORT type - already handled above
        # They render specially via BuildingItem/PortItem
```

### Event Routing (Transparent Rooms)

Qt's event system gives us transparent rooms for free:

1. User clicks at a screen position
2. Qt finds the topmost item at that point
3. If it's a `BuildingItem` inside a room, that item handles the event
4. The `RoomItem` parent doesn't intercept it

So clicking a building inside a room selects that building, not the room. The room is transparent.

**To select the room itself**: Click on the room boundary (not on any child item) or use a modifier key.

### Selection is Scene-Local

Selection cannot span scenes. When you click a building inside a room:
- The building is selected (in the room's scene)
- Any previously selected items in OTHER scenes are deselected

This is enforced by tracking the "active scene" based on what was last clicked:

```python
class FactoryCanvas:
    def __init__(self, ...):
        self._selection_scene: Scene | None = None  # Which scene has selection
    
    def _on_item_selected(self, item: BuildingItem | RoomItem):
        """Called when an item is selected."""
        if item.scene != self._selection_scene:
            # Clear selection in old scene
            self._clear_selection_in_scene(self._selection_scene)
            self._selection_scene = item.scene
```

### Canvas Item Tracking

The canvas maintains flat dictionaries for O(1) lookup by ID, even though items are hierarchically parented:

```python
class FactoryCanvas:
    _building_items: dict[str, BuildingItem] = {}  # All buildings, any scene
    _belt_items: dict[str, BeltItem] = {}          # All belts, any scene
    _room_items: dict[str, RoomItem] = {}          # All rooms, any scene
```

When adding a room, we recursively register all its contents:

```python
def add_room_item(self, room: Room, parent_scene: Scene) -> RoomItem:
    """Add a room and register all its contents for lookup."""
    item = RoomItem(room, parent_scene, self)
    
    # Add to parent (scene or another room)
    if isinstance(parent_scene, Document):
        self._scene.addItem(item)
    else:
        parent_room_item = self._room_items[parent_scene.id]
        item.setParentItem(parent_room_item)
    
    # Register for lookup
    self._room_items[room.id] = item
    for building_id, building_item in item._building_items.items():
        self._building_items[building_id] = building_item
    for belt_id, belt_item in item._belt_items.items():
        self._belt_items[belt_id] = belt_item
    # Recurse for nested rooms
    for nested_id, nested_item in item._room_items.items():
        self._room_items[nested_id] = nested_item
        # ... register nested contents
    
    return item
```

## Commands

### Command Signature Change

Commands receive `document` as an argument to `execute()`/`undo()`, not as a stored field. This keeps commands serializable and avoids stale references:

```python
class Command(ABC):
    """Base class for undoable commands."""
    
    @abstractmethod
    def execute(self, document: Document) -> None:
        """Execute the command."""
        ...
    
    @abstractmethod
    def undo(self, document: Document) -> None:
        """Undo the command."""
        ...

class CommandStack:
    def __init__(self, document: Document):
        self.document = document  # Stack owns the document reference
        self.undo_stack: list[Command] = []
        self.redo_stack: list[Command] = []
    
    def execute(self, cmd: Command) -> None:
        cmd.execute(self.document)
        # ... merge logic, stack management
    
    def undo(self) -> None:
        if self.undo_stack:
            cmd = self.undo_stack.pop()
            cmd.undo(self.document)
            self.redo_stack.append(cmd)
```

### Scene-Aware Commands

Commands store `scene_room_id` and look up the scene from the document at execute time:

```python
@dataclass(frozen=True)
class PlaceBuildingCommand(Command):
    """Command to place a building in a scene."""
    scene_room_id: str | None  # None = root document, else room ID
    building: Building
    canvas: FactoryCanvas
    
    def _get_scene(self, document: Document) -> Scene:
        if self.scene_room_id is None:
            return document
        return document.rooms[self.scene_room_id]
    
    def execute(self, document: Document) -> None:
        scene = self._get_scene(document)
        scene.add_building(self.building)
        # ... add to canvas

    def undo(self, document: Document) -> None:
        scene = self._get_scene(document)
        scene.remove_building(self.building.id)
        # ... remove from canvas
```

### Linked Room Commands (Not Needed!)

Since linked rooms are ONE Room object rendered multiple times, there's no "propagation" needed. When you modify a building in a Room, you're modifying the single Room object. All RoomItems that render that Room will see the change automatically on their next paint.

```python
@dataclass(frozen=True)
class SetRecipeCommand(Command):
    scene_room_id: str | None
    building_id: str
    old_recipe_id: str | None
    new_recipe_id: str | None
    canvas: FactoryCanvas
    
    def execute(self, document: Document) -> None:
        scene = self._get_scene(document)
        building = scene.buildings[self.building_id]
        building.recipe_id = self.new_recipe_id
        
        # Refresh ALL RoomItems that display this room
        # (canvas tracks which placements exist)
        self.canvas.refresh_building_in_room(self.building_id, self.scene_room_id)
        self.canvas.notify_mutation()
```

### Move Bounds Checking

Buildings inside a room cannot be dragged outside:

```python
class BuildingItem:
    def itemChange(self, change, value):
        if change == ItemPositionChange:
            new_pos = value
            
            # If we're in a room, clamp to room bounds
            if isinstance(self.scene, Room):
                w, h = self._get_display_size()
                room = self.scene
                # Clamp position to keep building inside room
                x = max(0, min(new_pos.x(), room.width - w))
                y = max(0, min(new_pos.y(), room.height - h))
                new_pos = QPointF(x, y)
            
            # Grid snap (screen-space concern, via canvas)
            if self.canvas.grid_snap:
                # ... snap logic
            
            return new_pos
```

## Room Creation

### Tool Flow

1. User clicks "Create Room" tool (one-shot)
2. User drags a rectangle on canvas
3. On release, validate and create:

```python
def _complete_room_creation(self, rect: QRectF) -> None:
    # Determine which scene we're creating in
    # (based on where the drag started - must be in one scene)
    scene = self._get_scene_at(rect.topLeft())
    
    # Validate: no buildings intersected (partially inside)
    for building in scene.buildings.values():
        building_rect = self._get_building_rect(building)
        if rect.intersects(building_rect) and not rect.contains(building_rect):
            self._show_error("Room boundary cannot intersect buildings")
            return
    
    # Collect buildings completely inside
    contained_building_ids = []
    for building in scene.buildings.values():
        if rect.contains(self._get_building_rect(building)):
            contained_building_ids.append(building.id)
    
    # Collect belts where BOTH endpoints are inside
    contained_belt_ids = []
    crossing_belt_ids = []  # One endpoint inside, one outside
    for belt in scene.belts.values():
        source_inside = belt.source_building_id in contained_building_ids
        dest_inside = belt.dest_building_id in contained_building_ids
        if source_inside and dest_inside:
            contained_belt_ids.append(belt.id)
        elif source_inside or dest_inside:
            crossing_belt_ids.append(belt.id)
    
    # Create command
    cmd = CreateRoomCommand(
        document=self.document,
        parent_scene_room_id=scene.id if isinstance(scene, Room) else None,
        rect=(rect.x(), rect.y(), rect.width(), rect.height()),
        building_ids=tuple(contained_building_ids),
        belt_ids=tuple(contained_belt_ids),
        crossing_belt_ids=tuple(crossing_belt_ids),
        canvas=self,
    )
    self.command_stack.execute(cmd)
```

### CreateRoomCommand

```python
@dataclass(frozen=True)
class CreateRoomCommand(Command):
    parent_scene_room_id: str | None
    rect: tuple[float, float, float, float]
    building_ids: tuple[str, ...]
    belt_ids: tuple[str, ...]
    crossing_belt_ids: tuple[str, ...]
    canvas: FactoryCanvas
    
    # Captured state for undo
    created_room_id: str = field(default_factory=generate_id)
    created_placement_id: str = field(default_factory=generate_id)
    
    def execute(self, document: Document) -> None:
        parent = self._get_parent_scene(document)
        x, y, w, h = self.rect
        
        # Create room
        room = Room(
            id=self.created_room_id,
            name=f"Room {len(document.rooms) + 1}",
            width=w, height=h,
        )
        
        # Move buildings into room (translate to room-relative coords)
        for building_id in self.building_ids:
            building = parent.remove_building(building_id)
            building.x -= x
            building.y -= y
            room.add_building(building)
            # Update canvas item's scene reference
            item = self.canvas._building_items[building_id]
            item.scene = room
        
        # Move internal belts
        for belt_id in self.belt_ids:
            belt = parent.remove_belt(belt_id)
            room.add_belt(belt)
        
        # Handle crossing belts: create ports, split belts
        for belt_id in self.crossing_belt_ids:
            self._handle_crossing_belt(parent, room, belt_id)
        
        # Add room to parent
        parent.rooms[room.id] = room
        
        # Update canvas
        self.canvas.add_room_item(room, parent)
        self.canvas.notify_mutation()
```

## Belt Drawing Across Boundaries

When user tries to draw a belt from inside a room to outside (or vice versa), it's blocked:

```python
def complete_belt_connection(self, dest_building_id: str, dest_port_index: int):
    source_item = self._building_items[self._connect_start_building]
    dest_item = self._building_items[dest_building_id]
    
    if source_item.scene != dest_item.scene:
        # Different scenes - cannot connect directly
        self._show_error("Cannot connect buildings in different rooms. Use ports.")
        self.cancel_belt_connection()
        return
    
    # Same scene - normal connection
    scene = source_item.scene
    belt = Belt(
        id=generate_id(),
        tier=self._current_belt_tier,
        source_building_id=self._connect_start_building,
        source_port_index=self._connect_start_port,
        dest_building_id=dest_building_id,
        dest_port_index=dest_port_index,
    )
    cmd = ConnectBeltCommand(
        document=self.document,
        scene_room_id=scene.id if isinstance(scene, Room) else None,
        belt=belt,
        canvas=self,
    )
    self.command_stack.execute(cmd)
```

**To connect across boundaries**, user must:
1. Create a Port on the room boundary (or have one auto-created during room creation)
2. Connect inside building → port (inside belt)
3. Connect port → outside building (outside belt)

## Linked Instances

### How Linking Works

Linking is simple: multiple `RoomPlacement`s reference the same `Room`. There's no special "link" field - the link IS the shared reference.

```python
# Two placements of the same room = "linked instances"
room = Room(id="room-1", name="Iron Smeltery", ...)
document.rooms["room-1"] = room

placement1 = RoomPlacement(id="p1", room_id="room-1", x=100, y=100)
placement2 = RoomPlacement(id="p2", room_id="room-1", x=500, y=100)
document.room_placements["p1"] = placement1
document.room_placements["p2"] = placement2

# Both render the same room - edits to the room affect both
```

### Creating from Library

When instantiating from the blueprint library, we add the Room to the document (if not already there) and create a placement:

```python
def instantiate_blueprint(self, room: Room, position: QPointF) -> RoomPlacement:
    # Add room to document if not already present
    if room.id not in self.document.rooms:
        self.document.rooms[room.id] = room
    
    # Create a placement
    placement = RoomPlacement(
        id=generate_id(),
        room_id=room.id,
        x=position.x(),
        y=position.y(),
    )
    self.document.room_placements[placement.id] = placement
    return placement
```

### Delink

Delinking creates a deep copy of the Room and assigns a new name:

```python
@dataclass(frozen=True)
class DelinkRoomCommand(Command):
    placement_id: str  # The placement being delinked
    canvas: FactoryCanvas
    
    # Captured at construction for undo
    old_room_id: str = ""
    new_room_id: str = field(default_factory=generate_id)
    
    def execute(self, document: Document) -> None:
        placement = document.room_placements[self.placement_id]
        old_room = document.rooms[placement.room_id]
        
        # Deep copy the room
        new_room = copy.deepcopy(old_room)
        new_room.id = self.new_room_id
        
        # Windows-style naming: "Copy of X", "Copy of Copy of X", etc.
        new_room.name = f"Copy of {old_room.name}"
        
        # Regenerate all internal IDs (buildings, belts, nested rooms)
        self._regenerate_ids(new_room)
        
        # Add new room to document
        document.rooms[new_room.id] = new_room
        
        # Point this placement at the new room
        placement.room_id = new_room.id
        
        self.canvas.refresh_placement(self.placement_id)
        self.canvas.notify_mutation()
```

## Rendering

### RoomItem Paint

```python
class RoomItem(QGraphicsRectItem):
    def paint(self, painter, option, widget):
        # Room boundary - color indicates if room has multiple placements
        placements = self.canvas.document.get_placements_for_room(self.room.id)
        if len(placements) > 1:
            # Multiple placements = "linked" - use distinct color
            color = self._color_for_room(self.room.id)
            pen = QPen(color, 2, Qt.SolidLine)
        else:
            pen = QPen(QColor(100, 100, 100), 2, Qt.DashLine)
        
        painter.setPen(pen)
        painter.setBrush(QBrush(QColor(50, 50, 55, 100)))
        painter.drawRect(self.rect())
        
        # Room name (just the name, no instance numbers)
        painter.drawText(self.rect(), Qt.AlignTop | Qt.AlignHCenter, self.room.name)
        
        # Children render themselves (Qt handles this)
```

---

## Implementation Sequence

Each phase is independently testable:

### Phase 1: Data Model
1. Add `Room` dataclass with Scene protocol methods
2. Add `Port` dataclass  
3. Update `Document` to have `rooms: dict[str, Room]` and Scene protocol
4. Update persistence to save/load rooms and ports
5. **Test**: Create Room in code, add buildings, serialize/deserialize

### Phase 2: RoomItem Graphics
6. Create `RoomItem(QGraphicsRectItem)` class
7. RoomItem creates child BuildingItems with `scene=self.room`
8. RoomItem creates child BeltItems
9. **Test**: Manually create Room with buildings, add to canvas, verify rendering

### Phase 3: Scene-Aware Items
10. Update `BuildingItem.__init__` to take `scene: Scene` parameter
11. Update `BuildingItem.itemChange` to call `canvas.update_belts_for_building(id, scene)`
12. Update `canvas.update_belts_for_building` to take scene parameter
13. **Test**: Move building in room, verify belt updates

### Phase 4: Scene-Local Selection
14. Track `_selection_scene` in canvas
15. Clear selection when clicking item in different scene
16. Prevent box-select across scene boundaries
17. **Test**: Click in room, then click in root - verify selection clears

### Phase 5: Scene-Aware Commands
18. Update `PlaceBuildingCommand` with `scene_room_id`
19. Update `ConnectBeltCommand` with `scene_room_id`
20. Update `DeleteItemsCommand` to work within a scene
21. **Test**: Place building in room via command, undo, verify

### Phase 6: Room Creation Tool
22. Add "Create Room" tool to toolbar
23. Implement rectangle drag
24. Validate no building intersections
25. `CreateRoomCommand`: move buildings/belts into room
26. **Test**: Create room around buildings, verify hierarchy

### Phase 7: Ports
27. Create `RoomPortItem` class
28. Port rendering on room boundary
29. Port drag along edge
30. Connect belts to ports
31. **Test**: Create port, connect belt to it

### Phase 8: Room Movement
32. RoomItem movement in parent scene
33. Moving room moves all children (Qt handles this)
34. `MoveRoomCommand` for undo/redo
35. **Test**: Move room, verify children follow, undo

### Phase 9: Linked Instances (via RoomPlacement)
36. Add `RoomPlacement` dataclass
37. Update Document to have `room_placements` dict
38. Canvas tracks RoomItems by placement_id, not room_id
39. Linked room rendering (color for rooms with multiple placements)
40. **Test**: Create two placements of same room, modify room, verify both update

### Phase 10: Delink
40. `DelinkRoomCommand`
41. Verify independence after delink
42. **Test**: Delink room, modify, verify no sync

### Phase 11: Blueprint Library
43. Save room to library (XDG dir)
44. Load blueprints into library panel
45. Instantiate from library (deep copy with new IDs)
46. **Test**: Save blueprint, reload app, instantiate

### Phase 12: Properties Panel
47. Room properties: name, link status, placement count
48. "Save to Library" button
49. "Delink" button
50. **Test**: Select room, verify properties display

---

## Document Save/Load

### File Format Changes

The `.sfp` file format (JSON) needs to accommodate rooms and placements:

```json
{
  "version": "0.2.0",
  "buildings": { ... },
  "belts": { ... },
  "recipes": { ... },
  "rooms": {
    "room-id-1": {
      "id": "room-id-1",
      "name": "Iron Smeltery",
      "width": 400,
      "height": 300,
      "buildings": { ... },
      "belts": { ... },
      "rooms": { ... }
    }
  },
  "room_placements": {
    "placement-1": {
      "id": "placement-1",
      "room_id": "room-id-1",
      "x": 100,
      "y": 200,
      "parent_scene_id": null
    },
    "placement-2": {
      "id": "placement-2", 
      "room_id": "room-id-1",
      "x": 600,
      "y": 200,
      "parent_scene_id": null
    }
  },
  "view_state": { ... }
}
```

### Persistence Functions

```python
def room_to_dict(room: Room) -> dict:
    """Serialize a Room to dictionary (recursive for nested rooms)."""
    return {
        "id": room.id,
        "name": room.name,
        "width": room.width,
        "height": room.height,
        "buildings": {bid: building_to_dict(b) for bid, b in room.buildings.items()},
        "belts": {bid: belt_to_dict(b) for bid, b in room.belts.items()},
        "rooms": {rid: room_to_dict(r) for rid, r in room.rooms.items()},
    }

def dict_to_room(data: dict) -> Room:
    """Deserialize a Room from dictionary."""
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

def placement_to_dict(placement: RoomPlacement) -> dict:
    return {
        "id": placement.id,
        "room_id": placement.room_id,
        "x": placement.x,
        "y": placement.y,
        "parent_scene_id": placement.parent_scene_id,
    }

def dict_to_placement(data: dict) -> RoomPlacement:
    return RoomPlacement(
        id=data["id"],
        room_id=data["room_id"],
        x=data["x"],
        y=data["y"],
        parent_scene_id=data.get("parent_scene_id"),
    )
```

### Blueprint Library Storage

Blueprints are saved to XDG user data directory:

```
~/.local/share/satisfactory-planner/blueprints/
├── iron-smeltery.json
├── steel-production.json
└── ...
```

Each blueprint file contains a single Room (not a placement):

```json
{
  "version": "1.0.0",
  "room": { ... }
}
```

```python
def save_blueprint(room: Room, name: str) -> Path:
    """Save a room as a blueprint to user library."""
    blueprints_dir = get_user_data_dir() / "blueprints"
    blueprints_dir.mkdir(parents=True, exist_ok=True)
    
    # Sanitize filename
    filename = sanitize_filename(name) + ".json"
    path = blueprints_dir / filename
    
    data = {
        "version": "1.0.0",
        "room": room_to_dict(room),
    }
    path.write_text(json.dumps(data, indent=2))
    return path

def load_blueprints() -> dict[str, Room]:
    """Load all blueprints from user library."""
    blueprints_dir = get_user_data_dir() / "blueprints"
    if not blueprints_dir.exists():
        return {}
    
    blueprints = {}
    for path in blueprints_dir.glob("*.json"):
        data = json.loads(path.read_text())
        room = dict_to_room(data["room"])
        blueprints[room.id] = room
    return blueprints
```

### Migration

When loading older documents (version < 0.2.0), we need to handle missing fields:

```python
def dict_to_document(data: dict) -> tuple[Document, dict | None]:
    version = data.get("version", "0.1.0")
    
    doc = Document()
    # ... load buildings, belts, recipes as before
    
    # v0.2.0+: load rooms and placements
    if "rooms" in data:
        for rid, rdata in data["rooms"].items():
            doc.rooms[rid] = dict_to_room(rdata)
    if "room_placements" in data:
        for pid, pdata in data["room_placements"].items():
            doc.room_placements[pid] = dict_to_placement(pdata)
    
    view_state = data.get("view_state")
    return doc, view_state
```

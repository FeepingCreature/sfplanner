# Room & Blueprint System Design

## Overview

Rooms are groupings of buildings that act as a single movable unit while remaining transparent - you can see and interact with their contents directly. A Room is simultaneously a **Building** (has position, can be moved, has ports) and a **Scene** (contains buildings, belts, handles its own events).

**Key insight**: A room is a "window into a different scene." When you interact with items inside a room, you're interacting with that scene. Belts cannot cross room boundaries - they must go through Ports.

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
    x: float  # Position in parent scene
    y: float
    width: float
    height: float
    
    # Scene contents (coordinates relative to room origin)
    buildings: dict[str, Building] = field(default_factory=dict)
    belts: dict[str, Belt] = field(default_factory=dict)
    rooms: dict[str, Room] = field(default_factory=dict)  # Nested rooms
    ports: dict[str, Port] = field(default_factory=dict)
    
    # Linking
    blueprint_id: str | None = None  # Source blueprint if linked
    instance_number: int = 1  # Display as "Name #1"
    
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

### Port

Ports are the boundary interface between a room and its parent scene. They act as belt endpoints.

```python
@dataclass
class Port:
    """A port on a room boundary - acts as belt endpoint."""
    id: str
    room_id: str
    edge: str  # "top", "bottom", "left", "right"  
    position: float  # 0.0-1.0 along edge
    is_output: bool  # Direction: True = flow out of room, False = flow into room
    
    # Connections (exactly one belt each side)
    inside_belt_id: str | None = None   # Belt in room.belts connecting to this port
    outside_belt_id: str | None = None  # Belt in parent scene connecting to this port
```

A port appears as:
- An **input port** from inside the room (if `is_output=True` - items flow out)
- An **output port** from outside the room (items exit the port into parent scene)

Or vice versa for `is_output=False`.

### Document Updates

```python
@dataclass
class Document:
    """Root document - implements Scene protocol."""
    buildings: dict[str, Building] = field(default_factory=dict)
    belts: dict[str, Belt] = field(default_factory=dict)
    rooms: dict[str, Room] = field(default_factory=dict)
    recipes: dict[str, Recipe] = field(default_factory=dict)
    
    # Scene protocol methods (same as Room)
    def add_building(self, building: Building) -> None: ...
    def remove_building(self, building_id: str) -> Building | None: ...
    def add_belt(self, belt: Belt) -> None: ...
    def remove_belt(self, belt_id: str) -> Belt | None: ...
    def get_belts_for_building(self, building_id: str) -> list[Belt]: ...
    
    # Linked room helpers
    def get_all_rooms(self) -> list[Room]:
        """Get all rooms recursively (for finding linked instances)."""
        result = []
        def collect(scene: Scene):
            for room in scene.rooms.values():
                result.append(room)
                collect(room)
        collect(self)
        return result
    
    def get_linked_rooms(self, blueprint_id: str) -> list[Room]:
        """Find all rooms that share a blueprint_id."""
        return [r for r in self.get_all_rooms() if r.blueprint_id == blueprint_id]
```

## UI Architecture

### RoomItem

A `RoomItem` is a `QGraphicsRectItem` that:
1. Renders the room boundary
2. Contains child `BuildingItem`s, `BeltItem`s, and nested `RoomItem`s
3. Is selectable/movable as a unit in its parent scene

```python
class RoomItem(QGraphicsRectItem):
    """A room on the canvas - contains child items for its contents."""
    
    def __init__(self, room: Room, parent_scene: Scene, canvas: FactoryCanvas):
        super().__init__()
        self.room = room
        self.parent_scene = parent_scene  # The scene this room lives IN
        self.canvas = canvas
        
        # Visual setup - rect is in local coords (0,0 to width,height)
        self.setRect(0, 0, room.width, room.height)
        self.setPos(room.x, room.y)  # Position in parent scene
        
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
        
        # Nested rooms (recursive)
        for nested_room in self.room.rooms.values():
            item = RoomItem(nested_room, parent_scene=self.room, canvas=self.canvas)
            item.setParentItem(self)
            self._room_items[nested_room.id] = item
        
        # Ports
        for port in self.room.ports.values():
            item = RoomPortItem(port, self.room, self.canvas)
            item.setParentItem(self)
            self._port_items[port.id] = item
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

### Scene-Aware Commands

Commands operate on a specific scene. They store the scene reference (or room_id for serialization):

```python
@dataclass(frozen=True)
class PlaceBuildingCommand(Command):
    """Command to place a building in a scene."""
    document: Document  # Root, for navigation
    scene_room_id: str | None  # None = root document, else room ID
    building: Building
    canvas: FactoryCanvas
    
    def _get_scene(self) -> Scene:
        if self.scene_room_id is None:
            return self.document
        # Find room by ID (could be nested)
        for room in self.document.get_all_rooms():
            if room.id == self.scene_room_id:
                return room
        raise ValueError(f"Room {self.scene_room_id} not found")
    
    def execute(self) -> None:
        scene = self._get_scene()
        scene.add_building(self.building)
        # ... add to canvas
```

### Linked Room Commands

When modifying a building inside a linked room, the change applies to all linked instances:

```python
@dataclass(frozen=True)
class SetRecipeCommand(Command):
    document: Document
    room_id: str | None  # Room containing the building (None = root)
    building_id: str
    old_recipe_id: str | None
    new_recipe_id: str | None
    canvas: FactoryCanvas
    
    def execute(self) -> None:
        if self.room_id:
            room = self._find_room(self.room_id)
            if room.blueprint_id:
                # Apply to ALL linked instances
                for linked in self.document.get_linked_rooms(room.blueprint_id):
                    building = linked.buildings.get(self.building_id)
                    if building:
                        building.recipe_id = self.new_recipe_id
                        self.canvas.refresh_building(building.id)
                self.canvas.notify_mutation()
                return
        
        # Normal case: single building
        scene = self._get_scene()
        building = scene.buildings.get(self.building_id)
        if building:
            building.recipe_id = self.new_recipe_id
            self.canvas.refresh_building(self.building_id)
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
    document: Document
    parent_scene_room_id: str | None
    rect: tuple[float, float, float, float]
    building_ids: tuple[str, ...]
    belt_ids: tuple[str, ...]
    crossing_belt_ids: tuple[str, ...]
    canvas: FactoryCanvas
    
    # Captured state for undo
    created_room_id: str = field(default_factory=generate_id)
    created_ports: tuple[Port, ...] = ()
    
    def execute(self) -> None:
        parent = self._get_parent_scene()
        x, y, w, h = self.rect
        
        # Create room
        room = Room(
            id=self.created_room_id,
            name=f"Room {len(self.document.get_all_rooms()) + 1}",
            x=x, y=y, width=w, height=h,
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

### Creating from Library

```python
def instantiate_blueprint(self, blueprint_id: str, position: QPointF) -> Room:
    source = self.blueprint_library.get(blueprint_id)
    
    # Deep copy
    room = copy.deepcopy(source.room)
    room.id = generate_id()
    room.x = position.x()
    room.y = position.y()
    room.blueprint_id = blueprint_id
    
    # Regenerate IDs for all contents (buildings, belts, ports, nested rooms)
    self._regenerate_ids(room)
    
    # Assign instance number
    existing = self.document.get_linked_rooms(blueprint_id)
    room.instance_number = len(existing) + 1
    
    return room
```

### Delink

```python
@dataclass(frozen=True)
class DelinkRoomCommand(Command):
    document: Document
    room_id: str
    canvas: FactoryCanvas
    
    # For undo
    old_blueprint_id: str | None = None
    old_name: str = ""
    
    def execute(self) -> None:
        room = self._find_room(self.room_id)
        
        # Clear link
        room.blueprint_id = None
        
        # Generate unique name
        base_name = room.name.split(" #")[0]
        existing_names = {r.name for r in self.document.get_all_rooms()}
        num = 1
        while f"{base_name} #{num}" in existing_names:
            num += 1
        room.name = f"{base_name} #{num}"
        
        self.canvas.refresh_room(room.id)
        self.canvas.notify_mutation()
```

## Rendering

### RoomItem Paint

```python
class RoomItem(QGraphicsRectItem):
    def paint(self, painter, option, widget):
        # Room boundary
        if self.room.blueprint_id:
            # Linked: color based on blueprint_id
            color = self._color_for_blueprint(self.room.blueprint_id)
            pen = QPen(color, 2, Qt.SolidLine)
        else:
            pen = QPen(QColor(100, 100, 100), 2, Qt.DashLine)
        
        painter.setPen(pen)
        painter.setBrush(QBrush(QColor(50, 50, 55, 100)))
        painter.drawRect(self.rect())
        
        # Room name
        name = self.room.name
        if self.room.blueprint_id:
            name = f"{name} #{self.room.instance_number}"
        painter.drawText(self.rect(), Qt.AlignTop | Qt.AlignHCenter, name)
        
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

### Phase 9: Linked Instances
36. Add `blueprint_id` and `instance_number` to Room
37. Linked room rendering (color, instance number)  
38. Command propagation to linked instances
39. **Test**: Create linked rooms, modify one, verify sync

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
47. Room properties: name, link status, instance count
48. "Save to Library" button
49. "Delink" button
50. **Test**: Select room, verify properties display

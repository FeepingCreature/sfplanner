# Room & Blueprint System Design

## Overview

Rooms are groupings of buildings that act as a single movable unit while remaining transparent - you can see and interact with their contents directly. A Room is simultaneously a **Building** (has position, can be moved, has ports) and a **Scene** (contains buildings, belts, handles its own events).

## Core Insight: Room as Building + Scene

The key architectural insight is that Qt's `QGraphicsItem` hierarchy already provides:
1. **Coordinate transformation** - child items use parent-relative coordinates
2. **Event propagation** - mouse events naturally route to topmost item
3. **Recursive rendering** - children render within parent's coordinate space

A `RoomItem` is a `QGraphicsRectItem` that contains `BuildingItem` and `BeltItem` children. This gives us transparent rooms for free - clicks on buildings inside rooms "just work" because Qt routes events to the topmost item.

## Data Model

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

### Room

```python
@dataclass
class Room:
    """A room is both a positionable item and a container for buildings."""
    id: str
    name: str
    x: float
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
```

### Port

```python
@dataclass
class Port:
    """A port on a room boundary - acts as belt passthrough."""
    id: str
    room_id: str
    edge: str  # "top", "bottom", "left", "right"  
    position: float  # 0.0-1.0 along edge
    is_output: bool  # Direction inherited from belt creation
    
    # Connections (exactly one belt each side)
    inside_belt_id: str | None = None
    outside_belt_id: str | None = None
```

### Document Updates

```python
@dataclass
class Document:
    """Root document - implements Scene protocol."""
    buildings: dict[str, Building]
    belts: dict[str, Belt]
    rooms: dict[str, Room]  # Top-level rooms (was: outlines)
    recipes: dict[str, Recipe]
    
    # For linked rooms
    def get_linked_rooms(self, blueprint_id: str) -> list[Room]:
        """Find all rooms that share a blueprint_id (including nested)."""
        ...
```

## UI Architecture

### RoomItem (New Class)

```python
class RoomItem(QGraphicsRectItem):
    """A room on the canvas - contains child BuildingItems and BeltItems."""
    
    def __init__(self, room: Room, canvas: FactoryCanvas):
        super().__init__()
        self.room = room
        self.canvas = canvas
        
        # Visual setup
        self.setRect(0, 0, room.width, room.height)
        self.setPos(room.x, room.y)
        
        # Make it selectable/movable as a unit
        self.setFlag(ItemIsSelectable)
        self.setFlag(ItemIsMovable)
        
        # Create child items for room contents
        self._building_items: dict[str, BuildingItem] = {}
        self._belt_items: dict[str, BeltItem] = {}
        self._room_items: dict[str, RoomItem] = {}  # Nested
        self._port_items: dict[str, PortItem] = {}
        
        self._populate_children()
    
    def _populate_children(self):
        """Create child graphics items for room contents."""
        for building in self.room.buildings.values():
            item = BuildingItem(building, self.canvas)
            item.setParentItem(self)  # Key: makes it a child
            self._building_items[building.id] = item
        # Similar for belts, nested rooms, ports
```

### Key Behavior: Event Routing

When user clicks inside a room:
1. Qt finds the topmost item at that point
2. If it's a `BuildingItem` inside a room, that item handles the event
3. The building's parent (`RoomItem`) doesn't intercept it
4. Commands target the building directly

This is **transparent by default** - no special handling needed.

### Active Scene Tracking

For operations that create new items (place building, draw belt), we need to know which scene to add to:

```python
class FactoryCanvas:
    def __init__(self, ...):
        # The scene where new items are created
        # None = root Document, otherwise a Room
        self._active_scene: Room | None = None
    
    def get_target_scene(self) -> Scene:
        """Get the scene where new items should be added."""
        return self._active_scene or self.document
    
    def set_active_scene(self, room: Room | None) -> None:
        """Set which room new items go into."""
        self._active_scene = room
        self._update_active_scene_indicator()
```

**How active scene is determined:**
- Clicking on a building sets active scene to its containing room (or root)
- Drawing a belt: active scene = scene of source port
- Placing a building: active scene = room the cursor is over, or root

### Canvas Item Tracking Changes

Currently canvas tracks items in flat dicts. We need hierarchical awareness:

```python
class FactoryCanvas:
    # Current: flat tracking
    # _building_items: dict[str, BuildingItem]
    # _belt_items: dict[str, BeltItem]
    
    # New: add room tracking, items still flat for lookup
    _room_items: dict[str, RoomItem] = {}
    
    # Items are still in flat dicts for ID lookup, but their
    # parent hierarchy determines coordinate space
    
    def add_room_item(self, room: Room) -> RoomItem:
        """Add a room and all its contents to the scene."""
        item = RoomItem(room, self)
        self._scene.addItem(item)
        self._room_items[room.id] = item
        # Child items are created by RoomItem and parented to it
        # but we still track them for ID-based lookup
        for building_id, building_item in item._building_items.items():
            self._building_items[building_id] = building_item
        return item
```

## Command System Updates

### Scene-Aware Commands

Commands need to target a specific scene. Two approaches:

**Option A: Pass scene explicitly**
```python
@dataclass
class PlaceBuildingCommand(Command):
    scene: Scene  # Document or Room
    building: Building
    canvas: FactoryCanvas
```

**Option B: Commands find scene from building location**
```python
@dataclass  
class PlaceBuildingCommand(Command):
    document: Document  # Root always
    building: Building
    target_room_id: str | None  # None = root
    canvas: FactoryCanvas
    
    def _get_target_scene(self) -> Scene:
        if self.target_room_id:
            return self._find_room(self.target_room_id)
        return self.document
```

**Recommendation: Option B** - Commands always have root Document for navigation, plus optional room targeting. This makes serialization cleaner and supports undo across room boundaries.

### Linked Room Commands

When a command modifies a linked room, it must apply to all instances:

```python
@dataclass
class SetRecipeCommand(Command):
    document: Document
    building_id: str
    room_id: str | None  # Room containing the building
    old_recipe_id: str | None
    new_recipe_id: str | None
    canvas: FactoryCanvas
    
    def execute(self) -> None:
        if self.room_id:
            room = self._find_room(self.room_id)
            if room.blueprint_id:
                # Apply to ALL rooms with same blueprint_id
                for linked in self.document.get_linked_rooms(room.blueprint_id):
                    building = linked.buildings.get(self.building_id)
                    if building:
                        building.recipe_id = self.new_recipe_id
                        self._refresh_building_in_room(linked, building)
                return
        # ... normal single-building case
```

### Move Bounds Checking

Moves must not drag buildings across room boundaries:

```python
class MoveBuildingsCommand(Command):
    def execute(self) -> None:
        for move in self.moves:
            building = self._find_building(move.building_id)
            room = self._containing_room(move.building_id)
            
            if room:
                # Check new position is within room bounds
                new_rect = QRectF(move.new_x, move.new_y, building.width, building.height)
                room_rect = QRectF(0, 0, room.width, room.height)
                if not room_rect.contains(new_rect):
                    # Clamp to room bounds
                    move = self._clamp_to_room(move, room)
            
            # Apply move...
```

## Room Creation Flow

### Tool: Create Room

1. User clicks "Room" tool in toolbar (one-shot tool)
2. User drags a rectangle on canvas
3. On release:

```python
def _complete_room_creation(self, rect: QRectF) -> None:
    # Validate: no buildings intersected (partially inside)
    for building_item in self._building_items.values():
        building_rect = building_item.sceneBoundingRect()
        if rect.intersects(building_rect) and not rect.contains(building_rect):
            self._show_error("Room boundary cannot intersect buildings")
            return
    
    # Collect buildings completely inside
    contained_buildings = []
    for building_item in self._building_items.values():
        if rect.contains(building_item.sceneBoundingRect()):
            # Must be in same scene (root or same room)
            if self._get_containing_room(building_item) == self._active_scene:
                contained_buildings.append(building_item.building)
    
    if not contained_buildings:
        self._show_error("Room must contain at least one building")
        return
    
    # Create room via command
    cmd = CreateRoomCommand(
        document=self.document,
        rect=rect,
        building_ids=[b.id for b in contained_buildings],
        canvas=self,
    )
    self.command_stack.execute(cmd)
```

### CreateRoomCommand

```python
@dataclass
class CreateRoomCommand(Command):
    document: Document
    rect: tuple[float, float, float, float]  # x, y, w, h
    building_ids: tuple[str, ...]
    belt_ids: tuple[str, ...]  # Belts where both ends are inside
    crossing_belts: tuple[CrossingBelt, ...]  # Belts that cross boundary
    canvas: FactoryCanvas
    
    def execute(self) -> None:
        # Create room
        room = Room(
            id=generate_id(),
            name=f"Room {len(self.document.rooms) + 1}",
            x=self.rect[0], y=self.rect[1],
            width=self.rect[2], height=self.rect[3],
        )
        
        # Move buildings into room (translate to room-relative coords)
        for building_id in self.building_ids:
            building = self.document.buildings.pop(building_id)
            building.x -= room.x
            building.y -= room.y
            room.buildings[building_id] = building
        
        # Move internal belts
        for belt_id in self.belt_ids:
            belt = self.document.belts.pop(belt_id)
            room.belts[belt_id] = belt
        
        # Handle crossing belts: create ports, split belts
        for crossing in self.crossing_belts:
            self._handle_crossing_belt(room, crossing)
        
        # Add room to document
        self.document.rooms[room.id] = room
        
        # Update UI
        self.canvas.add_room_item(room)
```

## Belt Boundary Crossing

When drawing a belt that would cross a room boundary:

```python
def complete_belt_connection(self, dest_building_id: str, dest_port_index: int):
    source_room = self._get_containing_room(self._connect_start_building)
    dest_room = self._get_containing_room(dest_building_id)
    
    if source_room != dest_room:
        # Belt crosses boundary - create port and split
        if source_room is None:
            # Source outside, dest inside room
            crossing_room = dest_room
            is_output = False  # Port receives from outside
        else:
            # Source inside room, dest outside
            crossing_room = source_room
            is_output = True  # Port sends to outside
        
        # Calculate intersection point
        intersection = self._line_rect_intersection(
            self._connect_start_pos, 
            dest_pos,
            crossing_room.rect
        )
        
        # Create port
        port = Port(
            id=generate_id(),
            room_id=crossing_room.id,
            edge=intersection.edge,
            position=intersection.position,
            is_output=is_output,
        )
        
        # Create two belts
        outside_belt = Belt(...)  # Source/dest depending on direction
        inside_belt = Belt(...)
        
        cmd = CreatePortAndBeltsCommand(port, outside_belt, inside_belt, ...)
        self.command_stack.execute(cmd)
    else:
        # Normal case: belt within same scene
        cmd = ConnectBeltCommand(...)
        self.command_stack.execute(cmd)
```

## Linked Instances

### Creating Linked Instances

When user drags a room from the library or duplicates a linked room:

```python
def instantiate_blueprint(self, blueprint_id: str, position: QPointF) -> Room:
    """Create a new instance linked to a blueprint."""
    source = self.blueprint_library.get(blueprint_id)
    
    # Deep copy the room
    room = copy.deepcopy(source.room)
    room.id = generate_id()
    room.x = position.x()
    room.y = position.y()
    room.blueprint_id = blueprint_id
    
    # Assign instance number
    existing = self.document.get_linked_rooms(blueprint_id)
    room.instance_number = len(existing) + 1
    
    return room
```

### Delink

```python
@dataclass
class DelinkRoomCommand(Command):
    room_id: str
    
    def execute(self) -> None:
        room = self._find_room(self.room_id)
        old_name = room.name
        old_blueprint_id = room.blueprint_id
        
        # Clear link
        room.blueprint_id = None
        
        # Generate new name with unique number
        base_name = old_name.split(" #")[0]  # Strip existing number
        existing_names = [r.name for r in self.document.all_rooms()]
        num = 1
        while f"{base_name} #{num}" in existing_names:
            num += 1
        room.name = f"{base_name} #{num}"
```

## Rendering

### RoomItem Paint

```python
class RoomItem(QGraphicsRectItem):
    def paint(self, painter, option, widget):
        # Draw room boundary
        if self.room.blueprint_id:
            # Linked: distinct color based on blueprint_id hash
            color = self._color_for_blueprint(self.room.blueprint_id)
            pen = QPen(color, 2, Qt.SolidLine)
        else:
            pen = QPen(QColor(100, 100, 100), 2, Qt.DashLine)
        
        painter.setPen(pen)
        painter.setBrush(QBrush(QColor(50, 50, 55, 100)))  # Semi-transparent
        painter.drawRect(self.rect())
        
        # Draw room name + instance number
        name = self.room.name
        if self.room.blueprint_id:
            name = f"{name} #{self.room.instance_number}"
        painter.drawText(self.rect(), Qt.AlignTop | Qt.AlignHCenter, name)
        
        # Children (buildings, belts) render themselves via Qt parent hierarchy
```

### Port Rendering

Ports render on room boundary, similar to building ports:

```python
class RoomPortItem(QGraphicsItem):
    def paint(self, painter, option, widget):
        # Draw on the edge of parent room
        if self.port.is_output:
            color = OUTPUT_COLOR  # Green
            # Arrow points outward
        else:
            color = INPUT_COLOR  # Yellow
            # Arrow points inward
        
        # Position is along edge, arrow points perpendicular
        ...
```

## Visual Indication of Linked Rooms

- **Border color**: Each `blueprint_id` gets a deterministic color (hash-based)
- **Instance number**: Displayed as `"Room Name #3"` 
- **Cross-instance**: `"#3.5"` means "5th instance of blueprint 3" (if we track blueprints by number)

Simpler approach: Just use name and instance number. Blueprint ID is internal.

---

## Implementation Sequence

Each step should be independently testable:

### Phase 1: Data Model
1. **Add `Room` dataclass** to models.py with Scene-like interface
2. **Add `Port` dataclass** to models.py
3. **Update `Document`** to have `rooms: dict[str, Room]`
4. **Add `Scene` protocol** for shared interface
5. **Update persistence** to save/load rooms

**Test**: Create Room in code, serialize/deserialize

### Phase 2: RoomItem Graphics
6. **Create `RoomItem`** class (QGraphicsRectItem subclass)
7. **RoomItem creates child BuildingItems** for its contents
8. **Test**: Manually create a Room with buildings, verify rendering

### Phase 3: Canvas Integration
9. **Add `_room_items` dict** to FactoryCanvas
10. **Add `add_room_item`/`remove_room_item`** methods
11. **Update `refresh()`** to handle rooms recursively
12. **Test**: Load document with room, verify display

### Phase 4: Room Creation Tool
13. **Add room creation tool** to toolbar (one-shot)
14. **Implement rectangle drag** for room boundary
15. **Validate building containment** (no intersections)
16. **CreateRoomCommand**: moves buildings into room
17. **Test**: Create room around buildings, verify hierarchy

### Phase 5: Room Movement
18. **RoomItem movement** moves all children
19. **Bounds checking** for buildings inside rooms
20. **MoveRoomCommand** for undo/redo
21. **Test**: Move room, verify contents follow

### Phase 6: Ports
22. **Create `RoomPortItem`** class
23. **Port positioning** on room boundary
24. **Port drag** along edge
25. **Test**: Create port, move it along edge

### Phase 7: Belt Boundary Crossing
26. **Detect belt crossing** room boundary during draw
27. **Auto-create port** at intersection
28. **Split belt** into inside/outside segments
29. **Test**: Draw belt crossing boundary, verify port creation

### Phase 8: Linked Instances
30. **Add `blueprint_id`** and `instance_number` to Room
31. **Linked room rendering** (color, instance number)
32. **Command propagation** to linked instances
33. **Test**: Create linked rooms, modify one, verify sync

### Phase 9: Delink
34. **DelinkRoomCommand**: clears blueprint_id, renames
35. **Verify independence** after delink
36. **Test**: Delink room, modify, verify no sync

### Phase 10: Blueprint Library
37. **Save room to library** (XDG dir)
38. **Load blueprints** into library panel
39. **Instantiate from library** (deep copy)
40. **Test**: Save blueprint, reload app, instantiate

### Phase 11: Properties Panel
41. **Room properties**: name, link status, instance count
42. **"Save to Library" button**
43. **"Delink" button** in properties
44. **Test**: Select room, verify properties display

---

## Summary

The key insight is using Qt's item hierarchy for transparent rooms:
- `RoomItem` contains child `BuildingItem`s
- Events naturally route to topmost item
- Coordinates transform automatically

This minimizes the UI rework - most of the change is in:
1. Data model (Room, Port, Scene protocol)
2. New graphics items (RoomItem, RoomPortItem)
3. Command targeting (which scene to modify)
4. Belt crossing detection and port auto-creation

The transparent approach means no "click into room" mode - just click on what you want and it works.

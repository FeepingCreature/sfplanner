# Room & Blueprint System Design

## Overview

Rooms are groupings of buildings that act as a single movable unit. Blueprints are rooms that can be saved to a library and reused. This document describes the architecture for both.

## Core Concepts

### Room
- A rectangular boundary containing buildings, belts, and ports
- Created by dragging a box around existing buildings
- Acts as a single "building" that can be moved/selected
- Has a **name** (editable in properties panel, used for save filename)
- Stored inline in the scene file (Document)

### Blueprint
- A room that has been saved to the user library (XDG data dir)
- When instantiated from library, a **copy** is made into the scene
- Changes to in-scene rooms do NOT affect the library version
- To update library: explicitly "Save Blueprint" again

### Port
- Special building type that exists only on room boundaries
- Has a direction (input or output) inherited from the belt that created it
- Exactly one belt connection allowed from inside, one from outside
- Visualizes like machine I/O arrows (yellow inward, green outward)
- Acts as a passthrough for flow calculations

## Data Model

### Room as Sub-Scene

A Room contains its own Document-like structure:

```python
@dataclass
class Room:
    id: str
    name: str
    rect: tuple[float, float, float, float]  # x, y, width, height in parent coords
    
    # Sub-scene contents (coordinates relative to room origin)
    buildings: dict[str, Building]  # includes nested Rooms
    belts: dict[str, Belt]
    ports: dict[str, Port]
    
    # Reference tracking for linked instances
    blueprint_id: str | None  # ID of source blueprint if linked
    instance_number: int  # For display: "Iron Smeltery #3"
```

### Port

```python
@dataclass
class Port:
    id: str
    room_id: str
    edge: str  # "top", "bottom", "left", "right"
    position: float  # 0.0-1.0 along edge
    direction: str  # "in" or "out"
    
    # Connected belts
    inside_belt_id: str | None   # Belt within the room
    outside_belt_id: str | None  # Belt in parent scene
```

### Blueprint Library Entry

```python
@dataclass
class BlueprintEntry:
    id: str
    name: str
    room: Room  # The template room (deep copy on instantiate)
    created_at: datetime
    modified_at: datetime
```

## Room Creation Flow

1. User clicks "Create Room" tool in toolbar
2. User drags a rectangle on canvas
3. On mouse release:
   - Validate: no buildings are *intersected* (partially inside)
   - Collect all buildings completely inside the rectangle
   - Collect all belts where BOTH endpoints are inside
   - Create Room with these contents
   - Handle belts that cross the boundary (see Belt Boundary Crossing)
   - Remove original buildings/belts from parent Document
   - Add Room to parent Document

## Belt Boundary Crossing

When a belt would cross a room boundary (during room creation OR when drawing a new belt):

1. Calculate intersection point of belt line with room rectangle
2. Create a Port at that intersection:
   - Edge = which side of rectangle was crossed
   - Position = normalized position along that edge
   - Direction = "in" if belt flows into room, "out" if flowing out
3. Split the belt into two:
   - Outside belt: from original source to Port
   - Inside belt: from Port to original destination
4. Both belts inherit tier from original

### During Room Creation

For each belt that has one endpoint inside and one outside:
1. Create Port at boundary intersection
2. Create inside belt (stored in Room)
3. Create outside belt (stored in parent Document)
4. Delete original belt

### When Drawing New Belt

If user drags from a port inside a room to a port outside (or vice versa):
1. Detect that the line crosses a room boundary
2. Auto-create Port at intersection
3. Create the two belt segments

## Linked Instances

When a room is created from a library blueprint:
1. Deep copy the Room from BlueprintEntry
2. Set `blueprint_id` to reference the source
3. Assign next available `instance_number`

### Synchronized Editing

All rooms with the same `blueprint_id` share modifications:
- Commands targeting a linked room are applied to ALL instances
- This includes: recipe changes, clock speed, internal belt changes, building additions/deletions
- Does NOT include: room position (each instance has its own location)

### Delink

Toolbar button to delink a room:
1. Set `blueprint_id = None`
2. Generate new unique room name: `"{original_name} #{next_number}"`
3. Room is now independent

## Command System Updates

### Command Targeting

Commands need to know which scene they're operating in:

```python
class Command(ABC):
    @abstractmethod
    def execute(self) -> None: ...
    
    @abstractmethod
    def undo(self) -> None: ...
    
    def target_room_id(self) -> str | None:
        """Return room ID if this command targets a sub-scene, None for root."""
        return None
```

### Coordinate Translation

Buildings inside a room use coordinates relative to room origin. Commands must:
1. Translate coordinates when rendering (room_pos + building_pos)
2. Bounds-check moves to prevent dragging buildings outside their room
3. Reject operations that would move buildings across room boundaries

### Linked Room Commands

For commands targeting a linked room:
```python
def execute(self):
    # Find all rooms with same blueprint_id
    linked_rooms = document.get_linked_rooms(self.blueprint_id)
    for room in linked_rooms:
        # Apply command to each instance
        self._apply_to_room(room)
```

## Rendering

Rooms render recursively:
1. Draw room boundary rectangle
2. Draw room name label
3. Translate to room origin
4. Draw all contained buildings/belts/ports
5. For nested rooms, recurse

### Port Rendering

Ports appear on the room boundary:
- Input ports: Yellow arrow pointing INTO room
- Output ports: Green arrow pointing OUT OF room
- Size similar to building ports
- Clickable for belt connections

## Library Panel Updates

Add "Blueprints" category to tree:
```
Buildings
├── Production
│   ├── Smelter
│   └── ...
├── Logistics
│   └── ...
└── Blueprints
    ├── Iron Smeltery
    ├── Steel Production
    └── ...
```

Blueprints section shows:
- Saved blueprints from user library
- Right-click menu: Rename, Delete
- Drag to canvas to instantiate

## Properties Panel Updates

When a Room is selected:
- Name (editable text field)
- Blueprint source (if linked): "{name}" with "Delink" button
- Instance count: "3 linked instances in scene"
- "Save to Library" button
- Summary: building count, input/output port count

## Flow Solver Updates

Ports act as passthroughs:
```python
def get_port_flow(port: Port) -> ItemFlow:
    # Flow through port = flow from the connected inside belt
    if port.inside_belt_id:
        return self.get_flow_rate(port.inside_belt_id)
    return None
```

For rooms, the solver:
1. Traces flow into input ports
2. Solves the internal sub-graph
3. Traces flow out of output ports

---

## Open Questions

### 1. Editing Inside Linked Rooms

**Q: How does the user edit the contents of a linked room?**

Options:
- A) Double-click room to "enter" it (like Figma components)
- B) Rooms are always visible, just click buildings inside
- C) Must delink before editing

Recommendation: **Option A** - Double-click enters room, breadcrumb shows path, changes propagate to all linked instances. Escape or click breadcrumb to exit.

### 2. Visual Indication of Linked Rooms

**Q: How do we show that rooms are linked?**

Ideas:
- Same border color for all instances of a blueprint
- Small icon/badge in corner
- Dotted vs solid border
- Name includes instance number: "Iron Smeltery #2"

Recommendation: All of the above - distinct border color + instance number in name.

### 3. Nested Rooms

**Q: Can rooms contain other rooms?**

The model supports it, but adds complexity:
- Coordinate transforms become nested
- Linking gets complicated (can a nested room be linked independently?)

Recommendation: **Allow nesting** but linked instances must be at the same nesting depth. Defer deep nesting edge cases to v2.

### 4. Moving Ports

**Q: Can ports be repositioned after creation?**

Options:
- A) Fixed at creation point
- B) Can drag along the edge they're on
- C) Can move to any edge

Recommendation: **Option B** - Drag along edge only. This maintains the constraint that ports are on boundaries.

### 5. Belt Routing to/from Ports

**Q: How do belts route to ports on room boundaries?**

The existing Dubins path algorithm should work - ports have a position and direction like any other connection point. The port direction defines the tangent angle.

### 6. Instance Numbering

**Q: How are instance numbers assigned?**

- When creating from library: find max instance_number for that blueprint_id, add 1
- When delinking: same logic, but for rooms with matching name prefix

---

## Implementation Order

1. **Room data model** - Add Room, Port to models.py
2. **Room creation tool** - Box drag, validation, boundary crossing
3. **Room rendering** - Recursive drawing, port visuals
4. **Room as building** - Move, select, delete room as unit
5. **Port connections** - Belt drawing to/from ports
6. **Blueprint save/load** - User library persistence
7. **Linked instances** - Sync edits across instances
8. **Delink** - Create independent copy
9. **Enter/exit room** - Double-click navigation
10. **Properties panel** - Room-specific properties

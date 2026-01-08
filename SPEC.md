# Satisfactory Production Planner - Specification

## Overview

A PCB-style factory floor planner for Satisfactory. Manual placement of buildings and belts with continuous validation of production flows.

## Tech Stack

- **Language**: Python 3.11+
- **UI Framework**: PySide6 (Qt 6)
- **Deployment**: pyside6-deploy (Nuitka) for static executables
- **Testing**: pytest + pytest-qt with custom test DSL
- **Build/Deps**: pyproject.toml + uv

## Core Concepts

### Buildings
Factory machine primitives:
- **Production**: Smelter, Foundry, Constructor, Assembler, Manufacturer, Refinery, Packager, Blender
- **Extraction**: Miner (Mk.1/2/3)
- **Logistics**: Splitter, Merger

Properties:
- Have **input ports** (yellow arrow) and **output ports** (green arrow)
- Splitters: 1 input, 3 outputs (square shape)
- Mergers: 3 inputs, 1 output (square shape)
- Configurable recipe selection (for production buildings)
- Configurable clock speed 0.01 - 2.5 (affects rates and power)
- Display current production rates
- Each building type has a defined bounding box size

Icons from Satisfactory wiki will be available for all items/buildings.

### Belts
- Connect output ports to input ports
- Have a **tier** determining max throughput:
  - Mk.1: 60/min
  - Mk.2: 120/min
  - Mk.3: 270/min
  - Mk.4: 480/min
  - Mk.5: 780/min
  - Mk.6: 1200/min
- Visual thickness varies by tier
- Show **item type** and **flow rate** as annotation
- Right-click to manually set belt tier
- Faint gray arrows underneath indicate flow direction

### Pipes (Fluids)
- Same mechanics as belts, different visual theming
- Fluid items (Water, Oil, etc.) use pipes instead of belts
- Pipe tiers: Mk.1 (300 m³/min), Mk.2 (600 m³/min)
- **Simplification**: Ignore head lift - assume full flow always
- Same circle-line-circle routing as belts
- Visual: thicker, different color scheme

### Belt Routing Algorithm
Belts use a **circle-line-circle** routing:
1. Constant-curvature arc leaving the source port
2. Straight line segment
3. Constant-curvature arc entering the destination port

This requires solving for tangent points between two circles with a connecting line.

The minimum turning radius should match the actual in-game belt radius (to be measured).


### Blueprints
- A **blueprint** is created from a building outline
- Contains: the outline's buildings, belts, sub-outlines, and connectors
- Can be **saved to user library**
- Can be **instantiated** (linked copy) or **embedded** (independent copy)
- Linked blueprints update when the source is edited
- Linked blueprints **cannot be edited directly** - must delink first
- Right-click → "Delink" to convert to independent copy
- Input/output ports are defined by connectors on the outline

## Validation & Warnings

The system continuously validates the factory graph and flags:

### Warning Types
1. **Leftover items** - Output not connected or exceeds downstream capacity
2. **Disconnected belts** - Belt missing source or destination
3. **Resource underflow** - Input demand exceeds supply
4. **Production underflow** - Building can't produce at required rate

### Causal Chain Display
Clicking a warning shows the **causal chain**:
```
Motors 4.3 < 5
  └── Rotors 7.1 < 10
        └── Belt has insufficient iron ingots (at capacity 780/min)
```
Each node in the chain is clickable to navigate to that element.

## UI Layout

**Blender-style fully reconfigurable panel system:**
- Any panel can be a foldout within another panel, or a standalone docked panel
- Panels can be docked to any edge, floated, or tabbed together
- User can save/load layout presets
- Ship with sensible defaults

### Available Panels
- **Library Panel** - Building primitives (icons), user blueprints
- **Properties Panel** - Selected item details (recipe, clock speed, stats)
- **Warnings Panel** - Clickable tree of validation issues
- **Power Summary Panel** - Total consumption, breakdown by type
- **Production Summary Panel** - Net inputs/outputs

### Default Layout
```
┌─────────────────────────────────────────────────────────────┐
│  Menu Bar: File | Edit | View | Help                        │
├─────────────────────────────────────────────────────────────┤
│  Toolbar: [Grid snap toggle] [Grid size] ...                │
├───────────────┬─────────────────────────────────────────────┤
│               │                                             │
│  [Library   ] │            Canvas                           │
│  [foldout   ] │         (QGraphicsView)                     │
│               │                                             │
│  [Properties] │     - Pan: middle-drag or space+drag        │
│  [foldout   ] │     - Zoom: scroll wheel                    │
│               │     - Select: click                         │
│  [Warnings  ] │     - Multi-select: shift+click or drag-box │
│  [foldout   ] │     - Drag: click+drag selected items       │
│               │     - Belt: drag from output to input port  │
│               │                                             │
└───────────────┴─────────────────────────────────────────────┘
```

## Interactions

### Canvas
- **Pan**: Middle mouse drag, or Space + left drag
- **Zoom**: Scroll wheel (centered on cursor)
- **Select**: Left click on item
- **Multi-select**: Shift+click to add, or drag rectangle to box-select
- **Move**: Drag selected items
- **Delete**: Delete key on selection
- **Copy/Paste**: Ctrl+C / Ctrl+V (pastes at cursor)
- **Undo/Redo**: Ctrl+Z / Ctrl+Shift+Z
- **Grid snap**: Toggle via toolbar icon, configurable grid size

### Belt Drawing
- Click and drag from output port
- Belt preview follows cursor with live routing
- Release on input port to connect
- Release on empty space to cancel
- Right-click on belt to set tier or delete

### Buildings
- Drag from library to place
- Double-click to edit (recipe, clock speed)
- Ports show connection status (filled = connected)

### Blueprints
- Select multiple items → Right-click → "Save as Blueprint"
- Drag blueprint from library to instantiate
- Right-click blueprint instance → "Delink" to make independent
- Double-click blueprint to "enter" and edit contents

## Data Model

### Recipe
```python
@dataclass
class Recipe:
    id: str
    name: str
    building_type: str  # "Smelter", "Constructor", etc.
    inputs: list[ItemRate]   # [(item_id, rate_per_min), ...]
    outputs: list[ItemRate]
    power_mw: float
    crafting_time: float  # seconds
```

### Building
```python
@dataclass
class Building:
    id: str
    building_type: str
    recipe_id: str | None
    clock_speed: float  # 0.01 to 2.5
    position: tuple[float, float]
```

### Belt
```python
@dataclass  
class Belt:
    id: str
    tier: int  # 1-6
    source_building_id: str
    source_port_index: int
    dest_building_id: str
    dest_port_index: int
    item_id: str | None  # inferred from source
    # Routing is computed, not stored
```


### Blueprint
```python
@dataclass
class Blueprint:
    id: str
    name: str
    outline: Outline  # The defining outline
    # Contents are stored within the outline
```

### BlueprintInstance
```python
@dataclass
class BlueprintInstance:
    id: str
    blueprint_id: str  # Reference to library blueprint
    position: tuple[float, float]
    is_linked: bool  # If True, cannot edit; mirrors source
```

## File Formats

### Project File (`.satplan`)
JSON containing:
- Root blueprint
- User library (custom blueprints)
- Custom recipes
- View state (zoom, pan position)

### Recipe Database (`recipes.json`)
Shipped with app, contains all vanilla Satisfactory recipes.
User can add custom recipes which are saved in project file.

## Summary Displays

### Power Summary
- Total power consumption (MW)
- Breakdown by building type
- Power at current clock speeds vs. 100% clock

### Production Summary  
- Net inputs (what the factory needs from outside)
- Net outputs (what the factory produces)
- Internal flows (what's consumed internally)

## Undo/Redo System

**Command pattern** - all mutations go through commands:

```python
class Command(ABC):
    @abstractmethod
    def execute(self) -> None: ...
    
    @abstractmethod  
    def undo(self) -> None: ...
    
    def merge_with(self, other: Command) -> Command | None:
        """Optional: merge consecutive commands (e.g., drag movements)"""
        return None

class CommandStack:
    def __init__(self):
        self.undo_stack: list[Command] = []
        self.redo_stack: list[Command] = []
    
    def execute(self, cmd: Command) -> None:
        cmd.execute()
        # Try to merge with previous
        if self.undo_stack:
            merged = self.undo_stack[-1].merge_with(cmd)
            if merged:
                self.undo_stack[-1] = merged
                self.redo_stack.clear()
                return
        self.undo_stack.append(cmd)
        self.redo_stack.clear()
    
    def undo(self) -> None:
        if self.undo_stack:
            cmd = self.undo_stack.pop()
            cmd.undo()
            self.redo_stack.append(cmd)
    
    def redo(self) -> None:
        if self.redo_stack:
            cmd = self.redo_stack.pop()
            cmd.execute()
            self.undo_stack.append(cmd)
```

### Command Types
- `PlaceBuildingCommand`
- `DeleteItemsCommand`
- `MoveBuildingsCommand` (mergeable - consecutive drags combine)
- `ConnectBeltCommand`
- `SetRecipeCommand`
- `SetClockSpeedCommand`
- `ResizeOutlineCommand`
- `CreateBlueprintCommand`
- `DelinkBlueprintCommand`

**All state mutations must go through commands.** This is enforced architecturally.

## Room System

Rooms are groupings of buildings that act as a single movable unit while remaining transparent - you can see and interact with their contents directly.

### Key Concepts

**Rooms are windows into scenes**: A Room implements the Scene protocol (contains buildings, belts). When you interact with items inside a room, you're interacting with that scene. The room boundary is just a viewport.

**Room vs RoomPlacement**: A `Room` is pure data (buildings, belts, size, name) with NO position. A `RoomPlacement` says "render Room X at position (x, y)". Multiple placements can reference the same Room - this is how linked instances work.

**Linked rooms are ONE room rendered multiple times**: There's only one Room object. Each "instance" is a RoomPlacement. Edits happen once to the single Room; all placements see the change.

**No "active scene" state**: Every UI action determines its target scene from the specific thing being acted upon (hit-test position, or ask the item for its scene). There's no global "current scene" - this is essential for transparent rooms.

**Scene-local operations**: A building belongs to exactly one scene. Belts connect buildings in the same scene. You cannot select items across scenes or draw belts across room boundaries.

### Ports (Future)

Ports are buildings inside the room with `BuildingType.PORT`. From inside, connect belts to them like any building. From outside, ports appear on the room boundary. Belts cannot cross room boundaries - they must go through ports.

### Blueprint Library

Blueprints are rooms saved to `~/.local/share/satisfactory-planner/blueprints/`. When instantiating:
- If room ID exists in document → creates linked placement
- If room ID doesn't exist → adds room and creates placement

This preserves linking when loading blueprints back into the same document.

### Delink

Delinking creates a shallow copy of the Room (new IDs for buildings/belts, but nested rooms stay linked) and points the placement at the copy. Uses "Copy of {name}" Windows-style naming.

## Future Considerations (Out of Scope v1)
- Trains/trucks/drones (logistics)
- 3D view
- Import from save file
- Auto-layout suggestions

---

## Project Structure

```
satisfactory-planner/
├── pyproject.toml
├── README.md
├── SPEC.md
├── src/
│   └── satisfactory_planner/
│       ├── __init__.py
│       ├── main.py
│       ├── core/
│       │   ├── __init__.py
│       │   ├── models.py          # Recipe, Building, Belt, Blueprint, Outline
│       │   ├── commands.py        # Command pattern for undo/redo
│       │   ├── flow_solver.py     # Graph analysis, rate propagation
│       │   └── routing.py         # Circle-line-circle belt routing math
│       ├── ui/
│       │   ├── __init__.py
│       │   ├── main_window.py
│       │   ├── canvas.py          # QGraphicsView + QGraphicsScene
│       │   ├── items/
│       │   │   ├── __init__.py
│       │   │   ├── building_item.py
│       │   │   ├── belt_item.py
│       │   │   └── port_item.py
│       │   ├── panels/
│       │   │   ├── __init__.py
│       │   │   ├── panel_system.py     # Docking/tabbing infrastructure
│       │   │   ├── library_panel.py
│       │   │   ├── properties_panel.py
│       │   │   └── warnings_panel.py
│       │   └── dialogs/
│       │       └── __init__.py
│       └── data/
│           ├── __init__.py
│           ├── recipes.json
│           └── icons/
└── tests/
    ├── conftest.py
    ├── helpers/
    │   └── canvas_helper.py
    ├── test_core/
    │   ├── test_models.py
    │   ├── test_flow_solver.py
    │   └── test_routing.py
    └── test_ui/
        └── test_canvas.py
```

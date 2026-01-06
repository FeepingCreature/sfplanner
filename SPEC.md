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
- Represent machines (Smelter, Constructor, Assembler, etc.)
- Have **input ports** (yellow arrow) and **output ports** (green arrow)
- Configurable recipe selection
- Configurable clock speed (affects rates and power)
- Display current production rates

### Belts
- Connect output ports to input ports
- Have a **tier** determining max throughput (60/120/270/480/780 items/min)
- Visual thickness varies by tier
- Show **item type** and **flow rate** as annotation
- Right-click to manually set belt tier
- Faint gray arrows underneath indicate flow direction

### Belt Routing Algorithm
Belts use a **circle-line-circle** routing:
1. Constant-curvature arc leaving the source port
2. Straight line segment
3. Constant-curvature arc entering the destination port

This requires solving for tangent points between two circles with a connecting line.

### Connectors
- **Cross-wall/cross-building connectors**: Square icon
- Represent logical connections that span blueprint boundaries

### Blueprints
- A blueprint is a container of buildings, belts, and sub-blueprints
- Can be **saved to user library**
- Can be **instantiated** (linked copy) or **embedded** (independent copy)
- Linked blueprints update when the source is edited
- Right-click to **delink** (convert to independent copy)
- Have defined input/output ports visible from outside

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

```
┌─────────────────────────────────────────────────────────────┐
│  Menu Bar: File | Edit | View | Help                        │
├───────────────┬─────────────────────────────────────────────┤
│               │                                             │
│   Library     │                                             │
│   Panel       │            Canvas                           │
│               │         (QGraphicsView)                     │
│  ┌─────────┐  │                                             │
│  │Buildings│  │     - Pan: middle-drag or space+drag        │
│  ├─────────┤  │     - Zoom: scroll wheel                    │
│  │ Belts   │  │     - Select: click                         │
│  ├─────────┤  │     - Multi-select: shift+click or drag-box │
│  │ User    │  │     - Drag: click+drag selected items       │
│  │Blueprints│ │     - Belt: drag from output to input port  │
│  └─────────┘  │                                             │
│               │                                             │
├───────────────┴──────────────────────┬──────────────────────┤
│  Properties Panel                    │  Warnings Panel      │
│  (selected item details, recipe,     │  (clickable tree of  │
│   clock speed, etc.)                 │   validation issues) │
└──────────────────────────────────────┴──────────────────────┘
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
    tier: int  # 1-5
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
    buildings: list[Building]
    belts: list[Belt]
    sub_blueprints: list[BlueprintInstance]
    input_ports: list[PortDefinition]   # exposed to parent
    output_ports: list[PortDefinition]
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

## Future Considerations (Out of Scope v1)
- Fluid pipes (different routing, different mechanics)
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
│       │   ├── models.py          # Recipe, Building, Belt, Blueprint
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

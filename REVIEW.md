# Satisfactory Planner - Design Review

## Executive Summary

The codebase is well-architected with clean separation between core logic (models, flow simulation, persistence) and UI (canvas, commands, panels). The command pattern implementation is particularly solid with immutable commands and pre-generated IDs for deterministic undo/redo. The flow solver integration is complete and well-structured.

---

## Architecture Strengths

### 1. Scene Protocol
The `Scene` protocol elegantly unifies `Document` and `Room` handling. Both implement the same interface (`add_building`, `remove_belt`, etc.), allowing commands and the flow builder to work uniformly on either. This is clean and extensible.

### 2. Command Pattern
The command implementation is exemplary:
- **Immutable commands** (`@dataclass(frozen=True)`)
- **Pre-generated IDs** at construction time for deterministic redo
- **Canvas reference** allows commands to update both model and UI
- **Merge support** for move commands (drag consolidation)
- Commands are correctly placed in `ui.commands` (undo/redo is a UI concern)

### 3. Flow Solver Pipeline
Clean separation of concerns:
- `flow_builder.py` - Document → FlowGraph with fatal error detection
- `flow_lp_solver.py` - FlowGraph → SolvedModel using LP
- `detectors/` - Modular warning detectors as pure functions
- `flow_solver.py` - Orchestrates the pipeline

The two-pass solve (with/without belt limits) for bottleneck detection is clever.

### 4. Canvas Composition
`FactoryCanvas` delegates to focused managers:
- `BeltConnector` - Belt connection dragging
- `PlacementManager` - Building/blueprint placement
- `DrawingTools` - Box selection and room creation
- `SelectionManager` - Selection state and outline

This keeps the main canvas file from becoming monolithic.

---

## Issues & Recommendations

### High Priority


#### 2. `recipe_id` Overloading
For `MINER`, `SOURCE`, and `SINK`, the `building.recipe_id` field stores an `item_id` instead of a recipe ID. This works but is confusing and could cause bugs.

**Recommendation:** Add an explicit `item_id: str | None` field to `Building` for these cases. Update `flow_builder.py` to use it.

#### 3. Missing UI Items Module
The `ui/items/` directory is referenced throughout (`BuildingItem`, `BeltItem`, `RoomItem`, `PortItem`, `WarningIconItem`) but the files aren't in the loaded context. The module structure exists but wasn't loaded.

**Recommendation:** Ensure `ui/items/__init__.py` exports all items cleanly.

### Medium Priority

#### 4. Unwired Toolbar Features
Several toolbar buttons are created but not fully wired:
- `show_grid_action` - disabled with TODO comment
- `show_leftovers_action` - disabled with TODO comment
- `belt_tier_combo` - has TODO comment about wiring

**Recommendation:** Either implement or remove these placeholders.

#### 5. Magic Numbers
Several magic numbers appear throughout:
- `100000.0` for "infinite" rate in flow ports
- `0.01` tolerance in flow comparisons
- `50` minimum room size
- Port offsets like `30` in room commands

**Recommendation:** Define named constants (e.g., `INFINITE_RATE = 100000.0`).

#### 6. Incomplete Panel Integration
The `PropertiesPanel` and `WarningsPanel` are referenced but not in the loaded files. Based on usage in `main_window.py`, they exist but their implementation details aren't visible.

**Recommendation:** Verify panels handle all expected data (efficiency display, causal chains).

### Low Priority

#### 7. Type Annotations
The `linprog.py` file is vendored and untyped (has `# type: ignore` on calls). This is fine since it's third-party code.

Some methods use `object` for signals where more specific types would help (`tool_mode_changed = Signal(object)`).

#### 8. Mutation Callback Pattern
`FactoryCanvas._mutation_callback` is a lambda set externally. This works but a proper signal would be more Qt-idiomatic.

#### 9. Test Coverage for Rooms
Based on test file summaries, room/blueprint functionality may have less test coverage than building/belt operations. The command logic for rooms is complex.

---

## Module Dependency Graph

```
core/
├── models.py           (Building, Belt, Room, Document, Scene protocol)
├── persistence.py      (save/load document, recipes, blueprints)
├── routing.py          (Dubins path computation for belts)
├── flow_models.py      (FlowGraph, FlowNode, FlowEdge)
├── flow_builder.py     (Document → FlowGraph)
├── flow_lp_solver.py   (FlowGraph → SolvedModel)
├── flow_solver.py      (orchestrator)
├── linprog.py          (vendored LP solver)
└── detectors/          (warning detectors)

ui/
├── main_window.py      (MainWindow, DocumentTab)
├── canvas/
│   ├── factory_canvas.py
│   ├── belt_connector.py
│   ├── drawing_tools.py
│   ├── placement_manager.py
│   └── selection_manager.py
├── commands/           (Command, CommandStack, all command classes)
├── dialogs/            (RecipeEditorDialog, SettingsDialog)
├── items/              (BuildingItem, BeltItem, RoomItem, etc.)
└── panels/             (LibraryPanel, PropertiesPanel, WarningsPanel)
```

---

## Suggested Cleanup Tasks

1. [x] Remove `Connector`, `Outline`, `Document.outlines` *(done)*
2. [x] Add `Building.item_id` for MINER/SOURCE/SINK *(done: added field, updated flow_builder, added migration in persistence)*
3. [x] Define constants for magic numbers *(done: INFINITE_RATE, FLOW_TOLERANCE, BOTTLENECK_TOLERANCE, PORT_EDGE_OFFSET, MIN_ROOM_SIZE)*
4. [x] Wire or remove disabled toolbar buttons *(done: removed show_grid_action, show_leftovers_action)*
5. [x] Add tests for room commands *(done: 13 tests for CreateRoomCommand, DelinkRoomCommand, PlaceBlueprintCommand)*
6. [ ] Use specific types in Signal declarations where possible

---

## Conclusion

This is a solid, well-organized codebase. The architecture supports the app's complexity well, and the separation of concerns is clean. The main technical debt is minor (unused types, magic numbers, incomplete UI features). The flow solver integration is complete and well-designed.

Priority should be:
1. Complete the UI integration (TODO.md items)
2. Clean up legacy code (Connector/Outline)
3. Add more test coverage for rooms

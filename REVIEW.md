# Architecture Review

## Summary

The codebase is well-structured with clear separation between core logic and UI. The command pattern is correctly implemented, and the multi-document tab system works. However, there are several awkward points, bugs, and missing dataflow connections.

---

## Bugs & Errors

### 1. Wrong attribute access in `building_item.py`
**File**: `src/satisfactory_planner/ui/items/building_item.py:132`
```python
doc = self.canvas._document  # WRONG - should be self.canvas.document
```
The canvas has `self.document`, not `self._document`. This will crash when trying to display recipe names.

### 2. `math` import inside methods
**Files**: `models.py` (lines 99, 117, 132, 150)
The `math` module is imported inside methods (`input_port_direction`, `output_port_direction`). While it works, it's unconventional and slightly slower. Should be at module top.

---

## DRY Violations

### 3. Duplicate `BUILDING_COLORS` definition
**Files**: 
- `building_item.py` (lines 19-32)
- `library_panel.py` (lines 36-49)

Same color mapping defined twice. Should be in `core/models.py` or a shared `ui/constants.py`.

### 4. Duplicate building display size logic
**Files**:
- `Building._get_display_size()` in `models.py`
- `BuildingItem._get_display_size()` in `building_item.py`
- Inline checks in `library_panel.py`

The "splitter/merger use 40x40" logic is repeated. The model should be the single source of truth.

### 5. Duplicate Dubins path drawing code
**Files**:
- `canvas.py` (`_update_drag_preview`)
- `belt_item.py` (`update_path`)

Nearly identical code for converting `BeltPath` to `QPainterPath`. Should be a shared utility.

---

## Coupling Issues

### 6. BuildingItem accesses canvas internals
**File**: `building_item.py`
```python
self.canvas._grid_snap
self.canvas._grid_size
self.canvas._update_belts_for_building(...)
```
BuildingItem reaches into canvas private members. Should use public methods.

### 7. PortItem directly calls canvas methods
**File**: `port_item.py`
```python
self.canvas.start_belt_drag(...)
self.canvas.complete_belt_connection(...)
self.canvas.is_dragging_belt()
```
This is acceptable but creates tight coupling. Consider using signals instead.

### 8. Canvas has knowledge of document internals
**File**: `canvas.py`
```python
self.document.is_port_connected(...)
self.document.buildings.get(...)
```
This is reasonable for read operations but could use accessor methods for cleaner API.

---

## Missing Dataflow Links

### 9. Recipe changes don't update building display
When a recipe is changed via `SetRecipeCommand`, the `BuildingItem` visual isn't updated. The flow is:
- `PropertiesPanel` → `SetRecipeCommand` → `Document` 
- Missing: → `BuildingItem.update()` or `canvas.refresh()`

### 10. Clock speed changes don't propagate to flow solver
The `FlowSolver` is called on `document_changed` signal, but it doesn't actually use clock speed in its calculations yet (TODOs in flow_solver.py).

### 11. No notification when user recipes are saved
`save_user_recipes()` in `RecipeEditorDialog` doesn't notify the document or other open tabs that recipes changed.

### 12. Belt tier changes have no command
The `PropertiesPanel` has a tier combo for belts but no handler connected to create a command. Tier changes aren't undoable.

### 13. Warnings panel click → canvas navigation not connected
`WarningsPanel.warning_clicked` signal is defined but never connected. Clicking a warning should navigate to the element.

---

## Excessive/Unnecessary Links

### 14. Document stores recipes redundantly
Both:
- `Document.recipes` - recipes specific to this document
- `load_all_recipes()` - loads base + user recipes

When a document is opened, recipes should be loaded once into the document. Currently, `PropertiesPanel._update_recipe_combo()` loads recipes every time it's called.

### 15. FlowSolver recreated per-tab but not per-change
Each `DocumentTab` has its own `FlowSolver`, but the solver just runs on `refresh()` calls. It could be stateless.

---

## Incomplete Implementations

### 16. Flow solver is mostly stubbed
**File**: `flow_solver.py`
- `_check_belt_capacity()` - empty, just passes
- `_check_production_rates()` - empty, just passes
- `get_flow_rate()` - always returns None

These are core to the value proposition of the app.

### 17. No copy/paste implementation
Listed in TODO.md, no code exists.

### 18. No keyboard shortcuts beyond delete/undo/redo
The SPEC mentions Ctrl+C/V, but they're not implemented.

### 19. Building rotation is visual-only
`rotation_angle` is stored on `BuildingItem`, not `Building`. Rotation is lost on refresh.

---

## Architectural Suggestions

### 20. Consider event bus for cross-component communication
Currently:
- `canvas.document_changed.emit()` → `MainWindow._update_warnings()`
- `library_panel.building_selected.emit()` → `MainWindow._on_building_selected()`

As the app grows, this will become a web of signal connections. An event bus pattern could simplify.

### 21. Model-View separation could be cleaner
`BuildingItem` holds a reference to `Building` AND caches display state like `rotation_angle`. Should be either:
- All state in model (preferred)
- Clear separation where item only reads from model

### 22. Consider making Document observable
Instead of requiring `canvas.refresh()` calls, the Document could emit signals when buildings/belts change, and items could listen.

---

## Test Coverage Gaps

### 23. No tests for UI panels
Tests exist for canvas but not for:
- `LibraryPanel` - drag/drop behavior
- `PropertiesPanel` - recipe/clock changes
- `WarningsPanel` - warning display

### 24. No tests for persistence
`load_document`/`save_document` aren't tested with actual file I/O.

### 25. No integration tests
No tests verify the full flow: place building → set recipe → connect belt → check warnings.

---

## Minor Issues

### 26. Magic numbers
- `40` for logistics size (defined as `LOGISTICS_SIZE` in building_item.py but hardcoded in models.py)
- `20` for default grid size (hardcoded in multiple places)
- Port radius/arrow sizes hardcoded

### 27. Type ignores could be reduced
Several `# type: ignore` comments that could be fixed with proper typing.

### 28. Inconsistent import style
Some files use `from PySide6.QtCore import Qt, Signal, ...` (preferred)
Others import whole modules like `from PySide6 import QtCore`

---

## Priority Fixes

1. **BUG**: Fix `self.canvas._document` → `self.canvas.document` (crashes app)
2. **DRY**: Consolidate `BUILDING_COLORS` 
3. **MISSING**: Connect `warning_clicked` signal
4. **MISSING**: Add belt tier change command
5. **ARCH**: Move `rotation_angle` to Building model

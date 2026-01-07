# Architecture Review

## Summary

The codebase is well-structured with clear separation between core logic and UI. The command pattern is correctly implemented, and the multi-document tab system works. However, there are several awkward points, bugs, and missing dataflow connections.

---

## Bugs & Errors

(None currently)

---

## DRY Violations

### ~~5. Duplicate Dubins path drawing code~~ ✓ FIXED
Extracted to `ui/items/path_utils.py::belt_path_to_painter_path()`.

---

## Coupling Issues

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

### ~~9. Recipe changes don't update building display~~ ✓ FIXED
`SetRecipeCommand.execute()` calls `canvas.refresh_building()` which updates the visual.

### 10. Clock speed changes don't propagate to flow solver
The `FlowSolver` is called on `document_changed` signal, but it doesn't actually use clock speed in its calculations yet (TODOs in flow_solver.py).

### 11. No notification when user recipes are saved
`save_user_recipes()` in `RecipeEditorDialog` doesn't notify the document or other open tabs that recipes changed.

### ~~12. Belt tier changes have no command~~ ✓ FIXED
~~The `PropertiesPanel` has a tier combo for belts but no handler connected to create a command. Tier changes aren't undoable.~~



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

### ~~17. No copy/paste implementation~~ ✓ FIXED
Implemented Ctrl+C/V in canvas.py.

### ~~18. No keyboard shortcuts beyond delete/undo/redo~~ ✓ FIXED
Added Ctrl+C, Ctrl+V, Ctrl+A shortcuts.



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
- Port radius/arrow sizes hardcoded

### ~~27. Type ignores could be reduced~~ ✓ FIXED
Reduced type ignores in canvas.py by using proper type signatures.

### 28. Inconsistent import style
Some files use `from PySide6.QtCore import Qt, Signal, ...` (preferred)
Others import whole modules like `from PySide6 import QtCore`

---

## Priority Fixes

1. ~~**MISSING**: Add belt tier change command~~ ✓ DONE


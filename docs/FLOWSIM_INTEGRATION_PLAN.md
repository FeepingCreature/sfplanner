# Flowsim Integration Plan

This document outlines how to integrate the `spikes/flowsim` prototype into the main `src/satisfactory_planner` codebase.

## Overview

The flowsim spike implements a complete flow simulation system:
- **Builder**: Converts visual models (Building, Belt) → FlowGraph
- **Solver**: LP-based steady-state flow calculation using pylinprog (pure Python)
- **Detectors**: Modular warning detection (underflow, overcapacity, dangling, etc.)

The current `src/satisfactory_planner/core/flow_solver.py` is a stub with basic disconnected belt detection. We'll replace it with the full implementation.

## Architecture Comparison

### Current (Stub)
```
Document → FlowSolver.solve() → list[Warning]
              ↓
         Basic checks only
```

### Target (Flowsim)
```
Document → build_flow_graph() → FlowGraph
                                    ↓
                              solve_flows() → SolvedModel
                                                  ↓
                                          detect_all_warnings() → list[Warning]
```

## Integration Steps

### Phase 1: Vendor pylinprog

**New file: `src/satisfactory_planner/core/linprog.py`**

Copy the vendored `linprog.py` from `spikes/flowsim/linprog.py`. This is a pure Python simplex solver from [dmishin/pylinprog](https://github.com/dmishin/pylinprog) (MIT license).

**Why pylinprog instead of scipy?**
- scipy + numpy adds ~78MB to packaged executable and **doesn't work** with pyside6-deploy/Nuitka (missing Cython modules)
- pylinprog is pure Python, single file (~300 lines), packages to ~39MB total
- All 49 flowsim tests pass with pylinprog

**Update `pyproject.toml`**: Add exclude for vendored file from ruff linting:
```toml
[tool.ruff]
exclude = [
    "src/satisfactory_planner/core/linprog.py",
]
```

---

### Phase 2: Add Flow Models

**New file: `src/satisfactory_planner/core/flow_models.py`**

Copy from `spikes/flowsim/models.py`:
- `NodeType` enum
- `FlowPort` dataclass
- `FlowNode` dataclass  
- `FlowEdge` dataclass
- `FlowGraph` dataclass
- `LimitingFactor` enum
- `BuildingEfficiency` dataclass

Keep `WarningType` and `Warning` in the existing location but update them:

**Update: `src/satisfactory_planner/core/flow_solver.py`**

Add new warning types from flowsim:
```python
class WarningType(Enum):
    DISCONNECTED_BELT = "disconnected_belt"
    RESOURCE_UNDERFLOW = "resource_underflow"
    PRODUCTION_UNDERFLOW = "production_underflow"
    LEFTOVER_ITEMS = "leftover_items"
    BELT_OVERCAPACITY = "belt_overcapacity"
    ITEM_MISMATCH = "item_mismatch"  # NEW
```

Add causal chain to Warning:
```python
@dataclass
class Warning:
    type: WarningType
    message: str
    element_id: str
    severity: float = 1.0  # NEW: 0.0-1.0 for sorting
    details: dict[str, object] | None = None
    caused_by: list["Warning"] = field(default_factory=list)  # NEW
```

---

### Phase 3: Implement Graph Builder

**New file: `src/satisfactory_planner/core/flow_builder.py`**

Adapt `spikes/flowsim/builder.py` to use existing models:

Key changes:
1. Remove the spike's local `Building`, `Belt`, `Document` dataclasses
2. Import from `satisfactory_planner.core.models` instead
3. Use the existing `Recipe` loading from persistence

```python
from satisfactory_planner.core.models import (
    Building, Belt, Document, Room, BuildingType, BELT_CAPACITIES
)
from satisfactory_planner.core.persistence import load_all_recipes
from satisfactory_planner.core.flow_models import (
    FlowGraph, FlowNode, FlowEdge, FlowPort, NodeType
)
```

Mapping from core BuildingType to NodeType:
```python
def _get_node_type(building_type: BuildingType) -> NodeType:
    if building_type in (BuildingType.MINER_MK1, BuildingType.MINER_MK2, BuildingType.MINER_MK3):
        return NodeType.MINER
    if building_type == BuildingType.SPLITTER:
        return NodeType.SPLITTER
    if building_type == BuildingType.MERGER:
        return NodeType.MERGER
    if building_type == BuildingType.PORT_IN:
        return NodeType.PORT_IN
    if building_type == BuildingType.PORT_OUT:
        return NodeType.PORT_OUT
    return NodeType.PRODUCER
```

Handle Rooms (not in spike):
- Recursively build flow graphs for room contents
- Connect PORT_IN/PORT_OUT nodes to parent graph via room placements

---

### Phase 4: Implement LP Solver

**New file: `src/satisfactory_planner/core/flow_lp_solver.py`**

Copy `spikes/flowsim/solver.py` with adjustments:
1. Update imports to use `satisfactory_planner.core.flow_models`
2. Import from vendored `satisfactory_planner.core.linprog`

```python
from satisfactory_planner.core.linprog import RESOLUTION_SOLVED, linsolve
from satisfactory_planner.core.flow_models import (
    FlowGraph, FlowNode, NodeType, BuildingEfficiency, LimitingFactor
)
```

The solver returns `SolvedModel` which contains:
- `graph`: The FlowGraph (with computed actual_rate values)
- `flows`: Dict of edge_id → flow rate
- `efficiencies`: Dict of node_id → BuildingEfficiency
- `success`: Whether LP solved successfully

---

### Phase 5: Implement Warning Detectors

**New directory: `src/satisfactory_planner/core/detectors/`**

Copy detector modules from `spikes/flowsim/detectors/`:

```
src/satisfactory_planner/core/detectors/
├── __init__.py      # detect_all_warnings() + re-exports
├── dangling.py      # detect_dangling_ports()
├── overcapacity.py  # detect_overcapacity()
├── underflow.py     # detect_underflow()
└── info.py          # detect_spare_capacity()
```

Update imports in each file to use the new module paths.

---

### Phase 6: Update FlowSolver Facade

**Update: `src/satisfactory_planner/core/flow_solver.py`**

Replace the stub implementation with orchestration:

```python
from satisfactory_planner.core.flow_builder import build_flow_graph, FatalError
from satisfactory_planner.core.flow_lp_solver import solve_flows, SolvedModel
from satisfactory_planner.core.detectors import detect_all_warnings

class FlowSolver:
    def __init__(self, document: Document) -> None:
        self.document = document
        self._solved_model: SolvedModel | None = None
        self._fatal_errors: list[FatalError] = []
        
    def solve(self) -> list[Warning]:
        """Analyze the factory and return warnings."""
        # Step 1: Build flow graph
        build_result = build_flow_graph(self.document)
        
        if not build_result.success:
            # Convert fatal errors to warnings
            self._fatal_errors = build_result.errors
            return [
                Warning(
                    type=_fatal_error_to_warning_type(e.error_type),
                    message=e.message,
                    element_id=e.element_id,
                    severity=1.0,
                )
                for e in build_result.errors
            ]
        
        # Step 2: Solve flows
        self._solved_model = solve_flows(build_result.graph)
        
        if not self._solved_model.success:
            return [Warning(
                type=WarningType.DISCONNECTED_BELT,  # Generic error
                message=self._solved_model.message,
                element_id="",
            )]
        
        # Step 3: Detect warnings
        return detect_all_warnings(self._solved_model)
    
    def get_flow_rate(self, belt_id: str) -> float | None:
        """Get the calculated flow rate for a belt."""
        if self._solved_model is None:
            return None
        return self._solved_model.flows.get(belt_id)
    
    def get_efficiency(self, building_id: str) -> BuildingEfficiency | None:
        """Get efficiency info for a building."""
        if self._solved_model is None:
            return None
        # Find node by building_id
        for eff in self._solved_model.efficiencies.values():
            if eff.building_id == building_id:
                return eff
        return None
```

---

### Phase 7: Update UI Integration

**Update: `src/satisfactory_planner/ui/panels/warnings_panel.py`**

1. Add new warning type icons:
```python
WARNING_ICONS = {
    WarningType.DISCONNECTED_BELT: "🔌",
    WarningType.RESOURCE_UNDERFLOW: "📉",
    WarningType.PRODUCTION_UNDERFLOW: "⚠️",
    WarningType.LEFTOVER_ITEMS: "📦",
    WarningType.BELT_OVERCAPACITY: "🚫",
    WarningType.ITEM_MISMATCH: "❌",  # NEW
}
```

2. Display causal chains as nested tree items:
```python
def _add_warning_item(self, parent: QTreeWidgetItem, warning: Warning) -> None:
    item = QTreeWidgetItem([warning.message])
    item.setData(0, Qt.ItemDataRole.UserRole, warning.element_id)
    parent.addChild(item)
    
    # Add causal chain as children
    for cause in warning.caused_by:
        self._add_warning_item(item, cause)
```

3. Sort warnings by severity (highest first)

**Update: `src/satisfactory_planner/ui/panels/properties_panel.py`**

Add efficiency display for buildings:
```python
def _show_building_properties(self, building: Building) -> None:
    # ... existing code ...
    
    # Add efficiency section
    efficiency = self.flow_solver.get_efficiency(building.id)
    if efficiency:
        self._add_label(f"Duty Cycle: {efficiency.duty_cycle * 100:.1f}%")
        self._add_label(f"Status: {efficiency.limiting_details}")
```

**Update: `src/satisfactory_planner/ui/items/belt_item.py`**

Show flow rate on belt hover/selection:
```python
def paint(self, painter, option, widget):
    # ... existing rendering ...
    
    # Show flow rate if available
    flow_rate = self.canvas.flow_solver.get_flow_rate(self.belt.id)
    if flow_rate is not None:
        painter.drawText(midpoint, f"{flow_rate:.1f}/min")
```

---

### Phase 8: Handle Rooms

The spike doesn't handle rooms. We need to extend the builder:

**In `flow_builder.py`:**

```python
def build_flow_graph(document: Document) -> BuildResult:
    """Build flow graph from document, including rooms."""
    graph = FlowGraph()
    errors: list[FatalError] = []
    
    # Build top-level buildings
    _build_scene(document, graph, errors)
    
    # Build each room placement
    for placement in document.room_placements.values():
        room = document.rooms.get(placement.room_id)
        if room:
            _build_room(room, placement, graph, errors)
    
    # ... validation passes ...
    
    return BuildResult(graph=graph, errors=errors)

def _build_room(room: Room, placement: RoomPlacement, 
                graph: FlowGraph, errors: list[FatalError]) -> None:
    """Build flow nodes for a room's contents."""
    # Build internal buildings/belts
    _build_scene(room, graph, errors, offset=(placement.x, placement.y))
    
    # PORT_IN/PORT_OUT buildings become special nodes that
    # connect the room's internal graph to the external graph
```

---

## Testing Strategy

### Unit Tests

Copy and adapt tests from `spikes/flowsim/tests/`:
- `test_builder.py` → `tests/test_core/test_flow_builder.py`
- `test_solver.py` → `tests/test_core/test_flow_lp_solver.py`
- `test_*.py` (detectors) → `tests/test_core/test_detectors/`

Update tests to use the real `Document`, `Building`, `Belt` models.

### Integration Tests

Add tests in `tests/test_core/test_flow_solver.py`:
- End-to-end: Document → warnings
- Room handling
- Recipe scaling with clock speed
- Edge cases from the spike tests

---

## File Summary

### New Files
- `src/satisfactory_planner/core/linprog.py` - Vendored pure Python LP solver (MIT)
- `src/satisfactory_planner/core/flow_models.py` - Flow graph models
- `src/satisfactory_planner/core/flow_builder.py` - Document → FlowGraph
- `src/satisfactory_planner/core/flow_lp_solver.py` - LP solver
- `src/satisfactory_planner/core/detectors/__init__.py` - Detector orchestration
- `src/satisfactory_planner/core/detectors/dangling.py`
- `src/satisfactory_planner/core/detectors/overcapacity.py`
- `src/satisfactory_planner/core/detectors/underflow.py`
- `src/satisfactory_planner/core/detectors/info.py`

### Modified Files
- `pyproject.toml` - Add ruff exclude for vendored linprog.py
- `src/satisfactory_planner/core/__init__.py` - Export new types
- `src/satisfactory_planner/core/flow_solver.py` - Replace stub with orchestration
- `src/satisfactory_planner/ui/panels/warnings_panel.py` - Causal chain UI
- `src/satisfactory_planner/ui/panels/properties_panel.py` - Efficiency display
- `src/satisfactory_planner/ui/items/belt_item.py` - Flow rate display

### Deleted (after integration)
- `spikes/flowsim/` - No longer needed
- `spikes/scipy_size_test/` - No longer needed

---

## Migration Checklist

- [x] Test pylinprog as scipy replacement (39MB vs 78MB, works!)
- [x] Port flowsim solver to pylinprog (all 49 tests pass)
- [ ] Vendor `linprog.py` into src/
- [ ] Create `flow_models.py` with flow graph types
- [ ] Create `flow_builder.py` adapting spike builder
- [ ] Create `flow_lp_solver.py` with LP solver
- [ ] Create `detectors/` module with all detectors
- [ ] Update `FlowSolver` to orchestrate pipeline
- [ ] Add severity and caused_by to Warning
- [ ] Update warnings panel for causal chains
- [ ] Add efficiency display to properties panel
- [ ] Add flow rate display to belt items
- [ ] Migrate and update all spike tests
- [ ] Handle rooms in builder
- [ ] Manual testing of full flow
- [ ] Delete spikes after verification

---

## Risks & Considerations

1. **~~scipy dependency size~~**: ✅ Solved! Using pylinprog instead (39MB total vs 78MB broken).

2. **Performance**: LP solving is O(n³) worst case. For large factories (1000+ nodes), may need caching or incremental solving. pylinprog is pure Python so potentially slower than scipy's HiGHS, but for typical factory sizes should be fine.

3. **Room graph stitching**: Connecting PORT_IN/PORT_OUT to parent graph needs careful handling of coordinate transforms.

4. **Backward compatibility**: The new Warning format (with severity, caused_by) is a superset of the old format.

5. **pylinprog maintenance**: We're vendoring a third-party library. If bugs are found, we either fix them ourselves or update from upstream. The code is simple enough (~300 lines) that this is manageable.

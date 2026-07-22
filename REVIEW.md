# Satisfactory Planner - Design Review

*Full-codebase review (all src/ + tests/ loaded). Replaces the previous review; completed items from the old checklist were verified as done.*

## Executive Summary

The codebase is well-architected: clean core/UI separation, an exemplary command pattern, and a sophisticated flow-solving pipeline (two-pass LP with dual-value bottleneck attribution). Tests for the core are strong. The main findings this pass are a handful of **real correctness bugs** (positional port/edge matching in the LP solver, lossy clipboard paste), several **undo/redo bypasses** where UI mutates the model directly, some **stale documentation**, and accumulated **dead code** in the optimizer/detectors.

---

## Architecture Strengths (verified against code)

1. **Scene protocol** (`models.py`) — Document and Room share one interface; commands and flow_builder work uniformly on either. Clean.
2. **Command pattern** (`ui/commands/`) — frozen dataclasses, all IDs pre-generated at construction (`CreateRoomCommand.create()` etc.), deterministic redo, merge support for drags. The invariant docs in `base.py` are excellent.
3. **Flow pipeline** — `flow_builder` (fatal errors, item-type propagation) → `flow_lp_solver` (two-pass solve, `ConstraintSource` tags surfaced via LP duals) → `detectors/` (pure functions). Limiting-factor detection with upstream/downstream BFS walking is genuinely clever and well-tested (`test_flow_solver.py`).
4. **Constraint optimizer** — symbolic bound tightening with source tracking; good dedicated tests.
5. **Canvas composition** — FactoryCanvas delegates to 6 focused managers (BeltConnector, PlacementManager, DrawingTools, SelectionManager, VisualSyncManager, ClipboardManager). Keeps the 40KB canvas file navigable.

---

## Bugs / Correctness Issues

### B1. Positional edge↔port matching in LP solver (HIGH)
`flow_lp_solver.py`: both `_solve_lp` (PRODUCER branch: `for i, out_edge in enumerate(outgoing): if i < len(node.outputs)`) and `_compute_efficiencies` (`if i < len(outgoing): flows.get(outgoing[i].id)`) pair the *i-th outgoing edge* with *output port i*. But `get_outgoing_edges` returns edges in dict-insertion order, not `source_port_index` order. For multi-output buildings (Refinery, Packager, Blender), if belts are connected out of order, the wrong rate constraints get applied. Should match `edge.source_port_index` to the port index explicitly. (The multi-output test connects ports in order, so it doesn't catch this.)

### B2. Clipboard paste loses building fields (HIGH)
`clipboard_manager.py.paste()` reconstructs Buildings with only `building_type, x, y, recipe_id, clock_speed, rotation`. **Dropped: `item_id`, `tier`, `min_rate`, `max_rate`, `port_index`.** Pasting a Miner/Source/Sink silently loses its configured item and tier. It deep-copies on copy, so just copy the remaining fields (or deepcopy + reassign id).

### B3. Direct model mutation bypassing the command stack (MEDIUM)
In `properties_panel.py`, these mutate the model directly with `notify_mutation()` and are therefore **not undoable**, unlike their sibling operations:
- `_on_miner_tier_changed` (sets `building.tier`)
- `_on_min_max_changed` (sets `min_rate`/`max_rate`)
- `_on_room_name_changed` (sets `room.name`)

Inconsistent with SetItemCommand/SetClockSpeedCommand handling of adjacent fields. Should get `SetMinerTierCommand`/`SetRateLimitsCommand`/`RenameRoomCommand` (or a generic property command).

### B4. room_id vs placement_id conflation in ItemKey (MEDIUM)
`ItemKey.placement_id` is documented as "the RoomPlacement.id". But `PortItem.mousePressEvent` builds `ItemKey(element_id=building_id, placement_id=self.scene_room_id)` where `scene_room_id` is a **Room** id, and `BeltConnector.complete()` then uses `self._connect_start_item.placement_id` as a `scene_room_id`. It works because BeltConnector treats it consistently as a scene id, but it's a category error waiting to bite anyone who compares these keys to flow-solver keys (which use real placement ids). Recommend a separate field or type for "scene context" vs "placement identity". (Related: `belt_item.py` already carries `# FIXME isn't this redundant with source_placement?` for `_placement_id`.)

### B5. Warnings panel can't name elements inside rooms (LOW)
`warnings_panel._get_element_name` uses `self.document.buildings.get()` / `belts.get()` — top-level only. `Document.find_building`/`find_belt` exist and should be used, so warnings for room contents show a friendly name.

### B6. Stale docstring contradicts design (LOW, but confusing)
`flow_lp_solver.solve_flows` docstring says: *"Fairness: Splitter outputs are constrained to be equal."* The code (correctly, per CLAUDE.md's **NO FAIRNESS CONSTRAINTS**) does no such thing. Delete the paragraph before it misleads someone into "fixing" the solver.

---

## Dead / Vestigial Code

- `detectors/underflow.py::_build_causal_chain` — never called (causal chains now come from LP duals). ~90 lines.
- `constraint_optimizer.py` — variable merging was deliberately disabled (good comment explains why), but its machinery remains: `merges` counter is never incremented (so the `if merges > 0` log condition is half-dead), `_eliminated_vars` is never used, `substitute()`/`is_simple_equality()`/`is_two_var_equality()` are only used by tests. Either delete or mark as intentionally retained.
- `detectors/overcapacity.py` — the non-two-pass fallback path only runs when `model.bottlenecks` is empty; worth a comment on whether that path is still reachable intentionally.
- `flow_lp_solver._write_dot_file` — debug-only, fine, but the call site is commented out; consider gating on an env var instead so it doesn't rot.

---

## Design Smells / Minor

1. **Duplicate port-layout logic** — `Building.get_port_layout()` claims to be "the single source of truth", but `input_port_pos`/`output_port_pos`/`*_port_direction` re-derive the same positions independently. Divergence risk (splitter/merger port ordering is spelled out twice).
2. **O(E) adjacency scans** — `FlowGraph.get_incoming_edges`/`get_outgoing_edges` linearly scan all edges and are called per-node in loops (builder, solver, detectors) → O(N·E). Fine at current scale; precompute adjacency maps if factories grow.
3. **Private access across modules** — `building._get_display_size()` is called from drawing_tools, placement_manager, room_item. It's de-facto public; rename to `get_display_size()`.
4. **`FactoryCanvas.window()` asserts MainWindow** — will assert-crash if called outside the app (tests avoid it via `super().window()` in one spot). Return `MainWindow | None` instead.
5. **`get_binding_sources` recomputes `get_reduced_system()`** — minor redundant work per solve.
6. **`detect_spare_capacity`** hardcodes 3 splitter outputs (`n_open = 3 - n_connected`) and embeds the raw ItemKey repr in the user-facing message.
7. **`ClipboardManager.copy_selection`** only scans `document.belts` — belts between selected buildings inside a room aren't copied (paste into rooms is handled, copy from rooms is not symmetric).
8. **`FlowSolver.solve()` is called redundantly** — `WarningsPanel.refresh()` calls `solve()` again even though MainWindow already solved; and `test_downstream_sink_limits_constructor` calls `solver.solve()` twice. Idempotent but wasteful; consider caching warnings on the solver.
9. `flow_solver.py` emits `ItemKey("")` for solver-failure warnings — a sentinel; navigation click on it silently no-ops. Acceptable but worth a comment.

---

## Test Coverage Notes

- **Strong**: flow solver semantics (limiting factors, propagation, bottlenecks, mismatches), constraint optimizer source tracking, room commands (incl. crossing-belt ports, undo/redo ID stability), command stack.
- **Gaps**: multi-output out-of-order belt connection (would catch B1); clipboard copy/paste round-trip (would catch B2); DissolveRoomCommand and DeleteRoomPlacementCommand have no direct tests; properties panel behaviors untested (understandable for Qt, but B3's non-undoable edits would surface in a command-level test if commands existed).

---

## Suggested Task List (priority order)

1. [x] **B1**: Match edges to ports by `source_port_index`/`dest_port_index` in `_solve_lp` and `_compute_efficiencies`; add out-of-order multi-output test. **DONE** (incl. SINK branch + recipe-ratio reference-edge selection; regression test `test_multi_output_out_of_order_belts`)
2. [x] **B2**: Preserve all Building fields in clipboard paste; add round-trip test. **DONE** (deepcopy + reassign id/x/y; test `test_copy_paste_preserves_building_fields`)
3. [x] **B3**: Command-ify miner tier, min/max rate, room rename. **DONE** (SetMinerTierCommand, SetRateLimitsCommand, RenameRoomCommand)
4. [x] **B6**: Delete stale fairness docstring in `solve_flows`. **DONE**
5. [x] **B4**: Untangle room_id vs placement_id in PortItem/BeltConnector ItemKeys (and resolve the belt_item FIXME). **DONE** (scene id now passed separately through start_belt_drag/BeltConnector - no more fake ItemKeys; flow-graph lookups match by element id)
6. [x] **B5**: Use `find_building`/`find_belt` in warnings panel naming. **DONE**
7. [x] Remove dead `_build_causal_chain`; prune or annotate vestigial optimizer machinery. **DONE** (also gated `_write_dot_file` behind SFPLANNER_DUMP_FLOW_DOT env var, documented overcapacity fallback path)
8. [x] Rename `_get_display_size` → `get_display_size` (public). **DONE** (FlowGraph adjacency maps deferred until perf matters)

---

## Module Dependency Graph

```
core/
├── models.py           (Building, Belt, Room, Document, Scene protocol)
├── item_key.py         (ItemKey - building/belt identity incl. placement)
├── persistence.py      (save/load document, recipes, blueprints)
├── routing.py          (Dubins path computation for belts)
├── port_geometry.py    (PORT building edge-snapping math)
├── flow_models.py      (FlowGraph, FlowNode, FlowEdge, BuildingEfficiency)
├── flow_builder.py     (Document → FlowGraph, fatal errors, type propagation)
├── constraint_optimizer.py (symbolic LP simplification + source tracking)
├── flow_lp_solver.py   (two-pass LP, duals → limiting factors)
├── flow_solver.py      (orchestrator + Warning types)
├── linprog.py          (vendored pylinprog simplex, extended with duals)
└── detectors/          (dangling, overcapacity, underflow, spare capacity)

ui/
├── main_window.py      (MainWindow, DocumentTab, toolbar/menu wiring)
├── print_dialog.py     (print preview, B&W rendering)
├── canvas/             (FactoryCanvas + 6 delegated managers)
├── commands/           (base + building/belt/property/room commands)
├── dialogs/            (RecipeEditorDialog, SettingsDialog)
├── items/              (Building/Belt/Port/Room/RoomPort/WarningIcon items)
├── panels/             (Library, Properties, Warnings)
└── widgets/            (SearchableComboBox)
```

---

## Conclusion

This codebase is in good shape — the hard problems (flow solving, undo determinism, linked room instances) have thoughtful, tested solutions. The issues found are localized: two genuine bugs (B1, B2), three consistency gaps (B3–B5), and routine cruft. Nothing structural needs to change.

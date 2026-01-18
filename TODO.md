# TODO

## Room System
- [ ] Room resizing (drag edges/corners to resize, with building constraint checks)
- [ ] Constrain building movement to stay within room bounds
- [x] Deletion inside rooms (DeleteItemsCommand has scene awareness)
- [ ] Clamp port movement to room edge (drag along boundary only)
- [x] Belts crossing room boundary auto-create ports
- [x] Room creation redo works correctly
- [x] Room deletion (DeleteRoomPlacementCommand)
- [x] Room dissolve (DissolveRoomCommand) - ungroup and restore buildings
- [x] Room delink (DelinkRoomCommand) - make independent copy
- [x] Create Room toolbar button shows active state while in CREATE_ROOM mode

## Room System - Known Bugs (low priority)
- [ ] Mid-drag doesn't update other linked room instances (only syncs on release)
- [ ] Can select items across multiple room instances (funny, not breaking)

## Pending GitHub Issues (need manual merge)
- [ ] #5: Very short belts get occluded by ports (z-order fix needed) - session errored, needs retry

## Known Incomplete Items
- [x] Belt routing: Dubins path (circle-line-circle) implementation
- [ ] Measure actual in-game belt turning radius
- [ ] Icons from Satisfactory wiki need to be added to data/icons/
- [ ] Recipe database needs full Satisfactory recipes (currently has samples)
- [ ] Pipe visual theming (currently same as belts)
- [x] Blueprint save/load to user library
- [ ] Linked blueprint editing restrictions
- [ ] Power summary panel
- [ ] Production summary panel
- [x] Project file save/load (.satplan)
- [x] Flow solver causal chain tracking (core + UI complete)

## Flow Solver UI - COMPLETE
- [x] Update warnings panel to display causal chains (caused_by field)
- [x] Add efficiency display to properties panel (duty_cycle, limiting_factor)
- [x] Add flow rate display to belt items on canvas
- [x] Show bottlenecks toolbar button (wired to flow solver)
- [x] Show flow rates on belts toolbar button (wired to flow solver)
- [ ] Show leftover items per port toolbar button (needs detector)
- [ ] Delete spikes/flowsim/ after UI integration verified
- [ ] Delete spikes/scipy_size_test/ after UI integration verified

## Completed
- [x] TreeView for library panel with categories
- [x] Splitter/merger smaller size (40px)
- [x] Splitter ports: 1 input (left), 3 outputs (top/right/bottom) with rotated arrows
- [x] Merger ports: 3 inputs (top/left/bottom), 1 output (right) with rotated arrows
- [x] Input arrows point inward, output arrows point outward
- [x] Chunky directional arrows on ports
- [x] Click building in library attaches to cursor
- [x] Drag from library to canvas
- [x] Mousewheel rotates building while attached to cursor
- [x] Multi-document support via tabs
- [x] Layout and View menus merged
- [x] Settings system (font, font size, grid size)
- [x] Recipe editor dialog

## Polish Items
- [x] Library panel: 3-line entries with icon spacer, info on second line
- [x] Copy/paste (Ctrl+C/V)
- [x] Keyboard shortcuts (Ctrl+A select all)
- [ ] Building detailed rendering (room for future expansion)
- [x] Toolbar (basic structure added)

## Toolbar Items (see main_window.py)
Working:
- [x] New/Open/Save
- [x] Select tool
- [x] Pan tool  
- [x] Belt tier dropdown
- [x] Zoom in/out/fit
- [x] Grid snap toggle
- [x] Grid size dropdown
- [x] Box select tool
- [x] Create room
- [x] Create blueprint from selection
- [x] Unlink blueprint
- [x] Dissolve room
- [x] Show bottlenecks
- [x] Show flow rates on belts

Stubbed:
- [ ] Show grid lines
- [ ] Show leftover items per port (needs detector)

# TODO

## Room System
- [ ] Room resizing (drag edges/corners)
- [ ] Constrain building movement to stay within room bounds
- [ ] Room name editing in properties panel

## Known Incomplete Items
- [x] Belt routing: Dubins path (circle-line-circle) implementation
- [ ] Measure actual in-game belt turning radius
- [ ] Icons from Satisfactory wiki need to be added to data/icons/
- [ ] Recipe database needs full Satisfactory recipes (currently has samples)
- [ ] Pipe visual theming (currently same as belts)
- [ ] Blueprint save/load to user library
- [ ] Linked blueprint editing restrictions
- [ ] Power summary panel
- [ ] Production summary panel
- [x] Project file save/load (.satplan)
- [ ] pyside6-deploy configuration for static builds
- [ ] Flow solver causal chain tracking (currently just flags issues)

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

Stubbed:
- [x] Box select tool
- [ ] Create room/outline
- [ ] Create blueprint from selection
- [ ] Unlink blueprint
- [ ] Show grid lines
- [ ] Show bottlenecks (needs flow solver)
- [ ] Show flow rates on belts (needs flow solver)
- [ ] Show leftover items per port (needs flow solver)

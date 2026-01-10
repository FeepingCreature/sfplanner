# Release 1.0 TODO

## Critical Bugs

- [x] **Room deletion doesn't clean up connected belts** - When deleting a room, belts leading to its ports are not removed
- [x] **Flow rates disappear after room operations** - Flow rates stop displaying after room ops until toggled off/on
- [x] **Belt properties panel broken** - Belts with flow show "Item (no item)" and "Current Flow: -"
- [x] **Room copypaste cannot be undone** - it doesn't even show up on the context stack.

## UI/UX Improvements

- [x] **Flow visualization toggles** - Efficiency and flow rate toggles now work independently and correctly on file load
- [ ] **Warning panel click-to-select** - Many warnings don't support clicking to select the relevant element
- [x] **Merger/Splitter properties** - Show item type and per-port flow rates in properties panel
- [x] **Grid snap redraw** - Canvas doesn't redraw immediately when snap dropdown is changed
- [ ] **Occupied Port** - Dragging belt *to* an occupied port should delete the belt currently going to it.

## Persistence & State

- [ ] **UI state autopersist** - Save/restore PyQtAds panel positioning, window size, etc.
- [ ] **View menu layouts** - Add saved layouts list with default layout and "Save layout" option

## Data & Configuration

- [ ] **Recipe overhaul** - Buildings should only show recipes in their category, consistent naming, complete wiki coverage
- [ ] **Settings expansion** - Move user-modifiable constants into Settings dialog (grid sizes, colors, etc.)

## Documentation & Release

- [ ] **README** - Project description, screenshots, installation instructions
- [ ] **Screenshot** - High-quality screenshot for README/marketing
- [ ] **Release process** - Build scripts for Linux, Windows, macOS binaries
- [ ] **GitHub Actions** - CI/CD hook for automated release builds

---

## Additional Items

- [ ] **Recent files menu** - File > Recent Files for quick access
- [ ] **Zoom to fit** - Button/shortcut to zoom canvas to show all content
- [ ] **Export to image** - Export factory layout as PNG/SVG for sharing
- [ ] **Version compatibility** - Document file format version, handle upgrades gracefully
- [x] **License file** - GPL-3.0 (MIT linprog is compatible)

## Error Handling

- [ ] **File load errors** - Log errors to console and show error dialog on corrupted/incompatible files

## Nice-to-Have (Post 1.0)

- [ ] Blueprint library organization (folders/tags)
- [ ] Search/filter in recipe selector
- [ ] Dark/light theme toggle
- [ ] Localization support
- [ ] Keyboard shortcuts documentation

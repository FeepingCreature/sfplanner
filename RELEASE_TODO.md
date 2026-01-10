# Release 1.0 TODO

## Critical Bugs

- [ ] **Room deletion doesn't clean up connected belts** - When deleting a room, belts leading to its ports are not removed
- [ ] **Flow rates disappear after room operations** - Flow rates stop displaying after room ops until toggled off/on
- [ ] **Belt properties panel broken** - Belts with flow show "Item (no item)" and "Current Flow: -"

## UI/UX Improvements

- [ ] **Warning panel click-to-select** - Many warnings don't support clicking to select the relevant element
- [ ] **Merger/Splitter properties** - Show item type and per-port flow rates in properties panel
- [ ] **Grid snap redraw** - Canvas doesn't redraw immediately when snap dropdown is changed

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

## Additional Considerations

- [ ] **Keyboard shortcuts documentation** - Help menu or tooltip showing all shortcuts
- [ ] **Undo/redo state after save** - Verify dirty flag and undo stack behavior on save/load
- [ ] **Error handling on file load** - Graceful handling of corrupted/incompatible save files
- [ ] **Recent files menu** - File > Recent Files for quick access
- [ ] **Zoom to fit** - Button/shortcut to zoom canvas to show all content
- [ ] **Export to image** - Export factory layout as PNG/SVG for sharing
- [ ] **Version compatibility** - Document file format version, handle upgrades gracefully
- [ ] **License file** - Ensure LICENSE is present and correct
- [ ] **Performance with large factories** - Test/profile with 100+ buildings

## Nice-to-Have (Post 1.0)

- [ ] Blueprint library organization (folders/tags)
- [ ] Search/filter in recipe selector
- [ ] Dark/light theme toggle
- [ ] Localization support
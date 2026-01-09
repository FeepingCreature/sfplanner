# Satisfactory Production Planner

A PCB-style factory floor planner for Satisfactory with manual building/belt placement.

## Tool Framework Feedback
The Forge tool framework is malleable - please suggest improvements and wishes for better tooling!

## Tech Stack
- Python 3.11+, PySide6, PySide6-QtAds for docking
- pytest + pytest-qt for testing
- mypy for type checking, ruff for lint/format
- pyside6-deploy (Nuitka) for static executables

## Project Structure
- `SPEC.md` - Full specification document
- `src/satisfactory_planner/` - Main application (not yet created)
- `spikes/` - Experimental prototypes
- `tools/` - Custom Forge tools

## LP Solver Design Notes

**NO FAIRNESS CONSTRAINTS** - Splitter output equality constraints are NEVER correct for steady-state flow simulation. They break tree layouts and over-constrain the LP. The LP should optimize based on actual downstream demand, not artificial "fair" distribution. Bottleneck detection is done via two-pass comparison (with/without belt limits), not by forcing equal splits.

## Commands
```bash
# Run panel system spike
cd spikes/panel_system && python main.py

# Run tests, type check, lint
pytest
mypy src/
ruff check src/
ruff format src/
```

## Port Rendering Model

**Ports are puzzle pieces** - Input and output ports should look like matching puzzle pieces that fit together:
- **Output ports** (green): Half-circle facing outward from building, belt starts here
- **Input ports** (yellow): Half-circle facing outward from building, belt ends here
- Both face the same direction (outward) so when you connect them, they visually "dock"

The angle parameter to `draw_half_circle_path()` is the direction the curved part faces:
- A port on the LEFT edge of a building faces LEFT (angle=180)
- A port on the RIGHT edge of a building faces RIGHT (angle=0)

This means belts flow INTO input ports and OUT OF output ports, with the half-circles acting as connectors.

## Qt Gotchas

**Defer to next frame when child items misbehave** - Qt sometimes needs to finish processing `addItem()` before child item geometry/visibility is valid. If items are invisible or mispositioned after being added, use `QTimer.singleShot(0, callback)` to defer the fix to the next event loop iteration.

## Web Tools (web_search / web_fetch)

**Compact aggressively after use** - these add lots of tokens to context.

- `web_search`: Uses duckduckgo-search library. ~200-500 tokens for 5 results.
- `web_fetch`: Fetches URL, converts to markdown via html2text. ~1k-10k+ tokens.

Both return `_token_estimate` field. Compact immediately after extracting needed info.

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

**PARTIAL FACTORY DESIGN** - The planner supports designing incomplete factories. Missing inputs generate warnings but don't affect efficiency. The flow solver assumes missing inputs will be filled in later (infinite supply). Use Source/Sink buildings to explicitly mark external inputs/outputs if you want to clear warnings.

**EFFICIENCY = DOWNSTREAM LIMITING** - Building efficiency measures how well downstream can consume what's being produced, NOT whether inputs are connected. It's `min(actual/intended)` across all *connected* inputs and outputs. Missing inputs show 100% efficiency (would run full speed if connected) with a separate INPUT_MISSING warning. This lets you see downstream bottlenecks even in partial designs.

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

## IMPORTANT: Always Run Tests Before Committing

Always run `<run_tests/>` before `<commit/>`. The test suite includes type checking (mypy) which catches type errors that would otherwise slip through. Never commit without passing tests.

## IMPORTANT: run_tests Formats Files

`run_tests` (which runs `make test`) includes `ruff format` which auto-formats all Python files. This means:

1. After `run_tests`, file contents may have changed (line wrapping, import sorting, trailing commas, etc.)
2. If you need to do a follow-up edit after `run_tests`, the search text must match the **formatted** version, not what you originally wrote
3. When chaining multiple edits with `run_tests` in between, be aware the file has been reformatted

Example: You write a multi-line function signature, but ruff collapses it to one line. Your next edit searching for the multi-line version will fail.

## Port Rendering Model

**Ports are puzzle pieces** - Input and output ports are complementary shapes that fit together:
- **Output ports** (green): Half-circle curving OUTWARD (the "tab") - something to grab from
- **Input ports** (yellow): Half-circle curving INWARD (the "blank") - a receptacle to receive into

They face **opposite directions** so they interlock when connected, like puzzle pieces.

The angle parameter to `draw_half_circle_path()` is the direction the curved part faces:
- Output on RIGHT edge: curves RIGHT (angle=0) - protruding outward
- Input on LEFT edge: curves RIGHT (angle=0) - opening inward to receive from left

When a belt connects output→input, both half-circles face the same direction (toward the input), creating a visual "handoff".

## Qt Gotchas

**Defer to next frame when child items misbehave** - Qt sometimes needs to finish processing `addItem()` before child item geometry/visibility is valid. If items are invisible or mispositioned after being added, use `QTimer.singleShot(0, callback)` to defer the fix to the next event loop iteration.

## File Loading Strategy

**Load files directly instead of grepping repeatedly.** Three `grep_context` calls cost more than one `update_context` to load the file. When you need to understand a file:

1. If you know which file - just load it with `update_context`
2. If you need to find which file - one `grep_context` to locate, then load the file
3. Don't grep the same file multiple times - load it once

**Bad pattern:**
```
grep_context("pattern1", file="foo.py")  # peek at foo.py
grep_context("pattern2", file="foo.py")  # peek again
grep_context("pattern3", file="foo.py")  # peek again
```

**Good pattern:**
```
update_context(add=["foo.py"])  # load once, see everything
```

## Type Design: Use Domain Types From The Start

Types express *meaning*, not just data shapes. When an operation conceptually targets an `ItemKey` (a flow graph entity), passing around `building_id: str` is a category error - like referring to a person by their SSN throughout a conversation instead of just referring to them.

**Warning signs you're doing it wrong:**
- Reaching into `.element_id` to extract a string, then later reconstructing the full key
- Iterating a dict to find something by a partial match when you could index directly
- Passing `building_id: str` when the caller has an `ItemKey` available

**Right approach:** Accept the domain type (`ItemKey`) at the API boundary, extract primitives only when needed for lower-level operations (like model lookups that use string IDs).

This applies to any typed wrapper: `ItemKey`, `RecipeId`, `ItemId`, etc. If the caller has the full type, don't strip it down to a string just to rebuild it later.

**When uncertain:** If you notice yourself doing type gymnastics (extracting, reconstructing, searching by partial key) and aren't sure if it's necessary, add a `# FIXME: should this use ItemKey directly?` comment. Better to flag the confusion than silently propagate a design smell.

**Flag domain model confusion too:** If you find yourself making an assumption about the domain that feels shaky (e.g., "this port index corresponds to this recipe input"), flag it with a FIXME or ask. The code should reflect actual game semantics, not convenient shortcuts.

**Push back on user requests that smell wrong:** If the user asks for something that contradicts what was just discussed, or seems to violate domain semantics, push back and ask for clarification rather than silently implementing something incorrect. The user can make mistakes too!

## GitHub Issues Workflow

We track GitHub issues with a conversational workflow:

1. **ISSUES.md** - Human-readable status tracking (awaiting feedback, blocked, etc.)
2. **.forge/github_issues_seen.json** - Timestamps for detecting new comments
3. **tools/GITHUB_ISSUES.md** - Full workflow documentation

**Quick check for new activity:**
```
github_issues(action="list")  # Get all open issues
# Compare updated_at against seen.json timestamps
# Issues with newer updated_at have new comments
```

**After commenting on an issue:** Update seen.json with the current timestamp.

**Issue lifecycle:** New → In Progress → Awaiting Feedback → Closed (with commit links)

## Web Tools (web_search / web_fetch)

**Compact aggressively after use** - these add lots of tokens to context.

- `web_search`: Uses duckduckgo-search library. ~200-500 tokens for 5 results.
- `web_fetch`: Fetches URL, converts to markdown via html2text. ~1k-10k+ tokens.

Both return `_token_estimate` field. Compact immediately after extracting needed info.

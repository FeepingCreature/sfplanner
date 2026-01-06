# Satisfactory Production Planner

A PCB-style factory floor planner for Satisfactory with manual building/belt placement.

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

## Web Tools (web_search / web_fetch)

**Compact aggressively after use** - these add lots of tokens to context.

- `web_search`: Uses duckduckgo-search library. ~200-500 tokens for 5 results.
- `web_fetch`: Fetches URL, converts to markdown via html2text. ~1k-10k+ tokens.

Both return `_token_estimate` field. Compact immediately after extracting needed info.

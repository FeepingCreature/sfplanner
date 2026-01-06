# Satisfactory Production Planner

A PCB-style factory floor planner for Satisfactory with manual building/belt placement.

## Tech Stack
- Python 3.11+, PySide6, PySide6-QtAds for docking
- pytest + pytest-qt for testing
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

# Run tests (once created)
pytest
```

## Tool Usage Notes

### web_search / web_fetch
These tools can add significant content to context. Check the `_token_estimate` field in results and **compact aggressively** after extracting needed information.

Typical token costs:
- web_search: 200-500 tokens for 5 results
- web_fetch: 1000-10000+ tokens depending on page size

### Dependencies for tools
```bash
pip install duckduckgo-search html2text
```

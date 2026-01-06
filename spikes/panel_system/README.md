# Panel System Spike

Testing PyQtAds (Qt Advanced Docking System) for Blender-style panel layout.

## What we're testing

1. ✅ Dock panels to edges
2. ✅ Tab panels together  
3. ✅ Float panels
4. ✅ Split areas horizontally/vertically
5. ✅ Save layout to file
6. ✅ Restore layout from file
7. ✅ Central widget that can't be closed

## Setup

```bash
cd spikes/panel_system
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
```

## Run

```bash
python main.py
```

## Test these interactions

1. **Drag "Library" panel** to the bottom - should dock there
2. **Drag "Warnings" onto "Properties"** - should create tabs
3. **Double-click a panel title** - should float it
4. **Drag the splitter** between Library and Canvas
5. **Layout > Save Layout** - save to a file
6. **Rearrange everything**, then **Layout > Load Layout** - should restore
7. **View menu** - toggle panel visibility

## Result

If all of the above work smoothly, we adopt PyQtAds. If not, note what fails
and we'll evaluate alternatives.

## Notes

- PyQtAds wraps the C++ Qt-Advanced-Docking-System
- Package: `PyQtAds[PySide6]`, import: `PySide6QtAds`
- Layouts are saved as binary QByteArray data

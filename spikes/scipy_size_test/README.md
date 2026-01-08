# SciPy Size Test

Testing packaged executable size with different LP solvers.

## Setup

```bash
cd spikes/scipy_size_test
uv venv --seed
source .venv/bin/activate
uv pip install PySide6 nuitka
```

## Option 1: scipy (DOES NOT WORK)

```bash
uv pip install numpy scipy
python main.py  # Works
pyside6-deploy main.py  # 78MB, crashes with missing modules
```

**Result**: 78MB, broken. scipy has too many hidden Cython dependencies.

## Option 2: solvOR (pure Python)

```bash
uv pip install solvor
python main_pure.py
pyside6-deploy main_pure.py
ls -lh deployment/
```

This should be much smaller since solvOR has no compiled dependencies.

## What We're Testing

Both scripts solve the same LP problem:
- Maximize: x1 + x2
- Subject to: x1 + x2 <= 10, x1 <= 6, x2 <= 4
- Expected solution: x1=6, x2=4, max=10

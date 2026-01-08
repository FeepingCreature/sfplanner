# SciPy Size Test

Minimal test to check packaged executable size when including scipy for LP solving.

## Setup

```bash
cd spikes/scipy_size_test
uv venv
source .venv/bin/activate
uv pip install PySide6 numpy scipy
```

## Test Run (unpackaged)

```bash
python main.py
```

Should show a window with "Solution: x1=6.00, x2=4.00, max=10.00"

## Package with pyside6-deploy

```bash
uv pip install nuitka
pyside6-deploy main.py
```

The executable will be in `deployment/`. Check its size:

```bash
ls -lh deployment/
```

## What We're Testing

The script uses:
- `scipy.optimize.linprog` with method="highs" (same as flowsim)
- `numpy` arrays for constraint matrices
- Minimal PySide6 GUI

This should give us a realistic estimate of the size overhead from scipy/numpy.

"""Warning detectors for flow simulation.

Each detector is a pure function: (SolvedModel) → list[Warning]
"""

from models import Warning
from solver import SolvedModel

from .info import detect_spare_capacity
from .overcapacity import detect_overcapacity
from .underflow import detect_underflow


def detect_all_warnings(model: SolvedModel) -> list[Warning]:
    """Run all warning detectors and combine results."""
    warnings: list[Warning] = []
    warnings.extend(detect_overcapacity(model))
    warnings.extend(detect_underflow(model))
    warnings.extend(detect_spare_capacity(model))
    return warnings


__all__ = [
    "detect_all_warnings",
    "detect_overcapacity",
    "detect_underflow",
    "detect_spare_capacity",
]

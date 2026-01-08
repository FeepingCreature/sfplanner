"""Warning detectors for flow simulation.

Each detector is a pure function: (SolvedModel) → list[Warning]
The dangling detector works on FlowGraph directly (pre-solve).
"""

# Import SolvedModel here to avoid circular imports
from satisfactory_planner.core.flow_lp_solver import SolvedModel
from satisfactory_planner.core.flow_solver import Warning

from .dangling import detect_dangling_ports
from .info import detect_spare_capacity
from .overcapacity import detect_overcapacity
from .underflow import detect_underflow


def detect_all_warnings(model: SolvedModel) -> list[Warning]:
    """Run all warning detectors and combine results."""
    warnings: list[Warning] = []
    warnings.extend(detect_dangling_ports(model.graph))
    warnings.extend(detect_overcapacity(model))
    warnings.extend(detect_underflow(model))
    warnings.extend(detect_spare_capacity(model))
    return warnings


__all__ = [
    "detect_all_warnings",
    "detect_dangling_ports",
    "detect_overcapacity",
    "detect_underflow",
    "detect_spare_capacity",
]

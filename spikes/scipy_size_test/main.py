"""Minimal scipy LP solver test for packaging size measurement.

Run with pyside6-deploy to check final executable size.
"""

import sys

import numpy as np
from PySide6.QtWidgets import QApplication, QLabel, QMainWindow, QVBoxLayout, QWidget
from scipy.optimize import linprog


def run_simple_lp() -> tuple[bool, str]:
    """Run a simple LP problem similar to our flow solver.

    Minimizes: -x1 - x2 (maximize x1 + x2)
    Subject to:
        x1 + x2 <= 10
        x1 <= 6
        x2 <= 4
        x1, x2 >= 0
    """
    # Objective: minimize -x1 - x2
    c = np.array([-1.0, -1.0])

    # Inequality constraints: A_ub @ x <= b_ub
    A_ub = np.array(
        [
            [1.0, 1.0],  # x1 + x2 <= 10
            [1.0, 0.0],  # x1 <= 6
            [0.0, 1.0],  # x2 <= 4
        ]
    )
    b_ub = np.array([10.0, 6.0, 4.0])

    # Bounds: x1, x2 >= 0
    bounds = [(0, None), (0, None)]

    # Solve using HiGHS (same as our flow solver)
    result = linprog(c, A_ub=A_ub, b_ub=b_ub, bounds=bounds, method="highs")

    if result.success:
        x1, x2 = result.x
        return True, f"Solution: x1={x1:.2f}, x2={x2:.2f}, max={-result.fun:.2f}"
    else:
        return False, f"Failed: {result.message}"


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("SciPy Size Test")
        self.setMinimumSize(400, 200)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # Run LP and show result
        success, message = run_simple_lp()
        status = "✅" if success else "❌"

        layout.addWidget(QLabel("<h2>SciPy LP Solver Test</h2>"))
        layout.addWidget(QLabel(f"<p>{status} {message}</p>"))
        layout.addWidget(QLabel(f"<p>NumPy version: {np.__version__}</p>"))
        layout.addWidget(QLabel("<p>SciPy linprog method: highs</p>"))


def main() -> None:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

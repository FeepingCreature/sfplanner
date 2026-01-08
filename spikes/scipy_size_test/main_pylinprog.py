"""Pure Python LP solver test using pylinprog.

Uses dmishin/pylinprog - a pure Python simplex implementation.
"""

import sys

from PySide6.QtWidgets import QApplication, QLabel, QMainWindow, QVBoxLayout, QWidget

# pylinprog is a single file, we'll vendor it or pip install from git
from linprog import linsolve, RESOLUTION_SOLVED


def run_simple_lp() -> tuple[bool, str]:
    """Run a simple LP problem using pure Python simplex solver.

    Maximize: x1 + x2
    Subject to:
        x1 + x2 <= 10
        x1 <= 6
        x2 <= 4
        x1, x2 >= 0

    linsolve minimizes, so we negate the objective.
    """
    # Objective: minimize -(x1 + x2) = maximize x1 + x2
    c = [-1.0, -1.0]

    # Inequality constraints: A @ x <= b
    A = [
        [1.0, 1.0],  # x1 + x2 <= 10
        [1.0, 0.0],  # x1 <= 6
        [0.0, 1.0],  # x2 <= 4
    ]
    b = [10.0, 6.0, 4.0]

    # Solve - variables are non-negative by default with nonneg_variables
    resolution, solution = linsolve(
        c, 
        ineq_left=A, 
        ineq_right=b,
        nonneg_variables=[0, 1]  # x1, x2 >= 0
    )

    if resolution == RESOLUTION_SOLVED and solution is not None:
        x1, x2 = solution
        obj = x1 + x2
        return True, f"Solution: x1={x1:.2f}, x2={x2:.2f}, max={obj:.2f}"
    else:
        return False, f"Failed: resolution={resolution}"


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("pylinprog LP Test")
        self.setMinimumSize(400, 200)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # Run LP and show result
        success, message = run_simple_lp()
        status = "✅" if success else "❌"

        layout.addWidget(QLabel("<h2>pylinprog LP Solver Test</h2>"))
        layout.addWidget(QLabel(f"<p>{status} {message}</p>"))
        layout.addWidget(QLabel("<p>Using: pylinprog (pure Python simplex)</p>"))
        layout.addWidget(QLabel("<p>No scipy/numpy dependencies!</p>"))


def main() -> None:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

"""Pure Python LP solver test for packaging size measurement.

Uses solvOR instead of scipy - no compiled dependencies.
"""

import sys

from PySide6.QtWidgets import QApplication, QLabel, QMainWindow, QVBoxLayout, QWidget
from solvor import solve_lp


def run_simple_lp() -> tuple[bool, str]:
    """Run a simple LP problem using pure Python solver.

    Maximizes: x1 + x2
    Subject to:
        x1 + x2 <= 10
        x1 <= 6
        x2 <= 4
        x1, x2 >= 0

    solvOR solves: max c^T x subject to Ax <= b, x >= 0
    """
    # Objective: maximize x1 + x2
    c = [1.0, 1.0]

    # Inequality constraints: A @ x <= b
    A = [
        [1.0, 1.0],  # x1 + x2 <= 10
        [1.0, 0.0],  # x1 <= 6
        [0.0, 1.0],  # x2 <= 4
    ]
    b = [10.0, 6.0, 4.0]

    # Solve
    result = solve_lp(c, A, b)

    if result.solution is not None:
        x1, x2 = result.solution
        return True, f"Solution: x1={x1:.2f}, x2={x2:.2f}, max={result.objective:.2f}"
    else:
        return False, "Failed: No solution found"


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Pure Python LP Test")
        self.setMinimumSize(400, 200)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # Run LP and show result
        success, message = run_simple_lp()
        status = "✅" if success else "❌"

        layout.addWidget(QLabel("<h2>Pure Python LP Solver Test</h2>"))
        layout.addWidget(QLabel(f"<p>{status} {message}</p>"))
        layout.addWidget(QLabel("<p>Using: solvOR (pure Python)</p>"))
        layout.addWidget(QLabel("<p>No scipy/numpy dependencies!</p>"))


def main() -> None:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

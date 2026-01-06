"""Main entry point for Satisfactory Planner."""

import sys

from PySide6.QtWidgets import QApplication, QMainWindow


def main() -> None:
    """Run the application."""
    app = QApplication(sys.argv)
    window = QMainWindow()
    window.setWindowTitle("Satisfactory Planner")
    window.resize(1200, 800)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

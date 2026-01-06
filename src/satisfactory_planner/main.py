"""Main entry point for Satisfactory Planner."""

import sys

from PySide6.QtWidgets import QApplication

from satisfactory_planner.ui.main_window import MainWindow


def main() -> None:
    """Run the application."""
    app = QApplication(sys.argv)
    app.setApplicationName("Satisfactory Planner")
    app.setApplicationVersion("0.1.0")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()

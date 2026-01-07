"""Main entry point for Satisfactory Planner."""

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from satisfactory_planner.ui.main_window import MainWindow


def main() -> None:
    """Run the application."""
    app = QApplication(sys.argv)
    app.setApplicationName("Satisfactory Planner")
    app.setApplicationVersion("0.1.0")

    window = MainWindow()
    
    # Open file from command line argument if provided
    args = app.arguments()
    if len(args) > 1:
        file_path = args[1]
        if Path(file_path).exists() and file_path.endswith(".sfp"):
            window._open_file(file_path)
    
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()

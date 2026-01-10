"""Main entry point for Satisfactory Planner."""

import logging
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from satisfactory_planner.ui.main_window import MainWindow

# Configure logging for debugging
logging.basicConfig(
    level=logging.WARNING,  # Default to WARNING for most modules
    format="%(name)s: %(message)s",
)

# Enable DEBUG for our UI modules to trace belt/building updates
logging.getLogger("satisfactory_planner.ui.items.building_item").setLevel(logging.DEBUG)
logging.getLogger("satisfactory_planner.ui.items.belt_item").setLevel(logging.DEBUG)
logging.getLogger("satisfactory_planner.ui.items.room_item").setLevel(logging.DEBUG)
logging.getLogger("satisfactory_planner.ui.canvas.factory_canvas").setLevel(logging.DEBUG)


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

#!/usr/bin/env python3
"""Satisfactory Production Planner - Main entry point."""

import sys
import logging
from PyQt6.QtWidgets import QApplication
from satisfactory_planner.gui.main_window import MainWindow


def main():
    # Configure logging
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(name)s - %(levelname)s - %(message)s'
    )
    
    app = QApplication(sys.argv)
    app.setApplicationName("Satisfactory Production Planner")
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

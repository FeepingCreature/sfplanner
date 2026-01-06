"""Smoke tests to verify basic setup works."""


def test_import() -> None:
    """Verify the package can be imported."""
    import satisfactory_planner

    assert satisfactory_planner.__version__ == "0.1.0"


def test_main_window(qtbot) -> None:  # type: ignore[no-untyped-def]
    """Verify main window can be created."""
    from PySide6.QtWidgets import QMainWindow

    window = QMainWindow()
    window.setWindowTitle("Test")
    qtbot.addWidget(window)

    assert window.windowTitle() == "Test"

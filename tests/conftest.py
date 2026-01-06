"""Pytest configuration and fixtures."""

import pytest
from pytestqt.qtbot import QtBot


@pytest.fixture
def qtbot(qtbot: QtBot) -> QtBot:
    """Re-export qtbot with proper typing."""
    return qtbot

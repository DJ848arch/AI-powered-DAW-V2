"""Pytest fixtures for ARIA characterization tests.

QT_QPA_PLATFORM must be set before any PyQt6 import so widgets can
be constructed headlessly (offscreen).
"""

import os
import sys
from pathlib import Path

# Set before importing PyQt6 (test modules import Qt at collection time).
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import pytest


@pytest.fixture(scope="session", autouse=True)
def qapp():
    """Session-wide QApplication. Autouse so QObject/QWidget construction works."""
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication(["aria-characterization-tests"])
    yield app

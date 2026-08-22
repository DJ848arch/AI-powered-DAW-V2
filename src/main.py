"""
AI-Integrated DAW - Main Entry Point
Digital Audio Workstation with AI agent integration
"""

import sys
import os

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from main_window import MainWindow


def setup_application():
    """Set up the application"""
    app = QApplication(sys.argv)
    
    # Application info
    app.setApplicationName("AI-Integrated DAW")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("ARIA")
    
    # Set application style
    app.setStyle('Fusion')
    
    # Set global stylesheet
    app.setStyleSheet("""
        QMainWindow {
            background: #2a2a2a;
        }
        QWidget {
            font-family: 'Segoe UI', 'Arial', sans-serif;
        }
        QMenuBar {
            background: #333;
            color: #ccc;
            border-bottom: 1px solid #444;
        }
        QMenuBar::item {
            background: transparent;
            padding: 6px 12px;
        }
        QMenuBar::item:selected {
            background: #444;
        }
        QMenu {
            background: #333;
            color: #ccc;
            border: 1px solid #444;
        }
        QMenu::item {
            padding: 6px 24px;
        }
        QMenu::item:selected {
            background: #4a9eff;
            color: white;
        }
        QToolBar {
            background: #333;
            border: none;
            spacing: 4px;
            padding: 4px;
        }
        QStatusBar {
            background: #333;
            color: #ccc;
            border-top: 1px solid #444;
        }
        QScrollBar:horizontal {
            background: #2a2a2a;
            height: 12px;
        }
        QScrollBar:vertical {
            background: #2a2a2a;
            width: 12px;
        }
        QScrollBar::handle {
            background: #555;
            border-radius: 2px;
        }
        QScrollBar::handle:hover {
            background: #666;
        }
        QDockWidget {
            titlebar-close-icon: url(close.png);
            titlebar-normal-icon: url(undock.png);
        }
        QDockWidget::title {
            background: #333;
            padding: 6px;
            border: 1px solid #444;
        }
        QDockWidget::close-button, QDockWidget::float-button {
            background: #444;
            border-radius: 2px;
            padding: 2px;
        }
        QDockWidget::close-button:hover, QDockWidget::float-button:hover {
            background: #555;
        }
    """)
    
    return app


def main():
    """Main entry point"""
    # Enable high DPI scaling
    if hasattr(Qt, 'AA_EnableHighDpiScaling'):
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_EnableHighDpiScaling, True)
    if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)
    
    # Create application
    app = setup_application()
    
    # Create and show main window
    window = MainWindow()
    window.show()
    
    # Run application
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

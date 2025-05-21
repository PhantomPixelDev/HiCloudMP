import sys
import os
import json
import tempfile
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPalette, QColor

# Import custom modules
from utils import HAS_WIN32
from player import MusicPlayer

if __name__ == '__main__':
    app = QApplication(sys.argv)
    
    # Apply dark theme
    app.setStyle("Fusion")
    
    # Modern dark palette with blue-purple accents
    dark_palette = QPalette()
    dark_palette.setColor(QPalette.Window, QColor(30, 30, 40))  # Darker blue-tinted background
    dark_palette.setColor(QPalette.WindowText, QColor(240, 240, 255))  # Slightly blue-tinted white
    dark_palette.setColor(QPalette.Base, QColor(25, 25, 35))  # Darker base
    dark_palette.setColor(QPalette.AlternateBase, QColor(35, 35, 45))  # Slightly lighter alternate
    dark_palette.setColor(QPalette.ToolTipBase, QColor(40, 35, 60))  # Purple-tinted tooltip
    dark_palette.setColor(QPalette.ToolTipText, QColor(240, 240, 255))
    dark_palette.setColor(QPalette.Text, QColor(240, 240, 255))
    dark_palette.setColor(QPalette.Button, QColor(45, 40, 65))  # Purple-tinted button
    dark_palette.setColor(QPalette.ButtonText, QColor(240, 240, 255))
    dark_palette.setColor(QPalette.Link, QColor(120, 100, 255))  # Bright purple link
    dark_palette.setColor(QPalette.Highlight, QColor(100, 80, 255))  # Purple highlight
    dark_palette.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
    dark_palette.setColor(QPalette.Active, QPalette.Button, QColor(55, 50, 75))  # Active button state
    dark_palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(150, 150, 170))  # Disabled text
    dark_palette.setColor(QPalette.Disabled, QPalette.WindowText, QColor(150, 150, 170))
    dark_palette.setColor(QPalette.Disabled, QPalette.Text, QColor(150, 150, 170))
    app.setPalette(dark_palette)
    
    # Set stylesheet
    app.setStyleSheet("""
        QToolTip { color: #ffffff; background-color: #2a82da; border: 1px solid white; }
        QTabBar::tab { background-color: #353535; color: white; padding: 6px; }
        QTabBar::tab:selected { background-color: #2a82da; }
        QHeaderView::section { background-color: #353535; color: white; padding: 4px; }
        QTreeWidget { outline: none; }
        QListWidget { outline: none; }
        QPushButton { padding: 6px 12px; border-radius: 4px; background-color: #2a82da; color: white; }
        QPushButton:hover { background-color: #3b93e6; }
        QPushButton:pressed { background-color: #206cb9; }
        QToolButton { border-radius: 4px; }
        QToolButton:hover { background-color: #353535; }
        QToolButton:checked { background-color: #2a82da; color: white; }
    """)
    
    player = MusicPlayer()
    player.show()
    sys.exit(app.exec()) 
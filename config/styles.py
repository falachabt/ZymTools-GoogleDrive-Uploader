"""
Styles CSS pour l'application Google Drive Explorer
"""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication


def apply_dark_theme(app: QApplication):
    """Applique le thème sombre moderne à l'application"""
    app.setStyle('Fusion')

    # Palette de couleurs sombre élégante
    palette = app.palette()
    palette.setColor(palette.Window, Qt.darkGray)
    palette.setColor(palette.WindowText, Qt.white)
    palette.setColor(palette.Base, Qt.black)
    palette.setColor(palette.AlternateBase, Qt.darkGray)
    palette.setColor(palette.ToolTipBase, Qt.white)
    palette.setColor(palette.ToolTipText, Qt.white)
    palette.setColor(palette.Text, Qt.white)
    palette.setColor(palette.Button, Qt.darkGray)
    palette.setColor(palette.ButtonText, Qt.white)
    palette.setColor(palette.BrightText, Qt.red)
    palette.setColor(palette.Link, Qt.blue)
    palette.setColor(palette.Highlight, Qt.blue)
    palette.setColor(palette.HighlightedText, Qt.black)
    app.setPalette(palette)


def get_application_stylesheet():
    """Retourne le CSS complet pour l'application"""
    return """
        /* Style général de l'application */
        QMainWindow {
            background-color: #2b2b2b;
            color: white;
        }

        /* Barre d'outils stylée */
        QToolBar {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                       stop:0 #4a4a4a, stop:1 #3c3c3c);
            border: 1px solid #555;
            border-radius: 5px;
            spacing: 8px;
            padding: 5px;
            margin: 2px;
        }

        QToolBar QAction {
            color: white;
            padding: 8px 12px;
            margin: 2px;
            border-radius: 6px;
            font-weight: bold;
            background: transparent;
        }

        QToolBar QAction:hover {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                       stop:0 #6a6a6a, stop:1 #555);
            border: 1px solid #777;
        }

        QToolBar QAction:pressed {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                       stop:0 #3a3a3a, stop:1 #2a2a2a);
        }

        /* Barre de statut */
        QStatusBar {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                       stop:0 #4a4a4a, stop:1 #3c3c3c);
            color: white;
            border-top: 1px solid #555;
            padding: 3px;
        }

        /* Vues d'arbre stylées */
        QTreeView {
            background-color: #2b2b2b;
            color: white;
            alternate-background-color: #353535;
            selection-background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                                       stop:0 #4a90e2, stop:1 #357abd);
            selection-color: white;
            border: 1px solid #555;
            border-radius: 5px;
            gridline-color: #444;
        }

        QTreeView::item {
            padding: 5px;
            border-bottom: 1px solid #333;
        }

        QTreeView::item:hover {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                       stop:0 #404040, stop:1 #353535);
        }

        QTreeView::item:selected {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                       stop:0 #4a90e2, stop:1 #357abd);
        }

        /* En-têtes des colonnes */
        QHeaderView::section {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                       stop:0 #5a5a5a, stop:1 #4a4a4a);
            color: white;
            padding: 8px;
            border: 1px solid #666;
            border-radius: 3px;
            font-weight: bold;
        }

        QHeaderView::section:pressed {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                       stop:0 #3a3a3a, stop:1 #2a2a2a);
        }

        /* Boutons stylés */
        QPushButton {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                       stop:0 #5a5a5a, stop:1 #4a4a4a);
            color: white;
            border: 1px solid #666;
            padding: 8px 15px;
            border-radius: 6px;
            font-weight: bold;
            min-width: 80px;
        }

        QPushButton:hover {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                       stop:0 #6a6a6a, stop:1 #5a5a5a);
            border: 1px solid #777;
        }

        QPushButton:pressed {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                       stop:0 #3a3a3a, stop:1 #2a2a2a);
        }

        QPushButton:disabled {
            background: #2a2a2a;
            color: #666;
            border: 1px solid #444;
        }

        /* Champs de texte */
        QLineEdit {
            background-color: #3c3c3c;
            color: white;
            border: 2px solid #555;
            padding: 8px;
            border-radius: 6px;
            font-size: 11pt;
        }

        QLineEdit:focus {
            border: 2px solid #4a90e2;
            background-color: #404040;
        }

        /* ComboBox */
        QComboBox {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                       stop:0 #5a5a5a, stop:1 #4a4a4a);
            color: white;
            border: 1px solid #666;
            padding: 8px;
            border-radius: 6px;
            min-width: 100px;
        }

        QComboBox:hover {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                       stop:0 #6a6a6a, stop:1 #5a5a5a);
        }

        QComboBox::drop-down {
            border: none;
            width: 20px;
        }

        QComboBox::down-arrow {
            image: none;
            border-style: solid;
            border-width: 5px 5px 0px 5px;
            border-color: white transparent transparent transparent;
        }

        QComboBox QAbstractItemView {
            background-color: #3c3c3c;
            color: white;
            border: 1px solid #555;
            selection-background-color: #4a90e2;
        }

        /* Barre de progression stylée */
        QProgressBar {
            border: 2px solid #555;
            border-radius: 8px;
            text-align: center;
            background-color: #3c3c3c;
            color: white;
            font-weight: bold;
            height: 25px;
        }

        QProgressBar::chunk {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                       stop:0 #4a90e2, stop:0.5 #357abd, stop:1 #4a90e2);
            border-radius: 6px;
            margin: 1px;
        }

        /* Labels */
        QLabel {
            color: white;
            font-weight: bold;
        }

        /* Splitter */
        QSplitter::handle {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                       stop:0 #4a4a4a, stop:1 #5a5a5a);
            width: 5px;
            border-radius: 2px;
        }

        QSplitter::handle:hover {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                       stop:0 #6a6a6a, stop:1 #7a7a7a);
        }

        /* Menus contextuels */
        QMenu {
            background-color: #3c3c3c;
            color: white;
            border: 1px solid #555;
            border-radius: 5px;
            padding: 5px;
        }

        QMenu::item {
            padding: 8px 25px;
            border-radius: 3px;
        }

        QMenu::item:selected {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                       stop:0 #4a90e2, stop:1 #357abd);
        }

        QMenu::separator {
            height: 1px;
            background: #555;
            margin: 5px 0px;
        }

        /* Dialogues */
        QDialog {
            background-color: #2b2b2b;
            color: white;
        }

        QDialogButtonBox QPushButton {
            min-width: 100px;
            margin: 5px;
        }

        /* Scrollbars stylées */
        QScrollBar:vertical {
            background: #2b2b2b;
            width: 12px;
            border-radius: 6px;
        }

        QScrollBar::handle:vertical {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                       stop:0 #5a5a5a, stop:1 #6a6a6a);
            border-radius: 6px;
            min-height: 20px;
        }

        QScrollBar::handle:vertical:hover {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                       stop:0 #6a6a6a, stop:1 #7a7a7a);
        }

        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
            height: 0px;
        }

        QScrollBar:horizontal {
            background: #2b2b2b;
            height: 12px;
            border-radius: 6px;
        }

        QScrollBar::handle:horizontal {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                       stop:0 #5a5a5a, stop:1 #6a6a6a);
            border-radius: 6px;
            min-width: 20px;
        }

        QScrollBar::handle:horizontal:hover {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                       stop:0 #6a6a6a, stop:1 #7a7a7a);
        }

        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
            width: 0px;
        }
    """

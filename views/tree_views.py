"""
Vues d'arbre personnalisées avec support du drag and drop
"""

from typing import List
from PyQt5.QtWidgets import QTreeView
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QDragEnterEvent, QDropEvent


class LocalTreeView(QTreeView):
    """Vue personnalisée pour les fichiers locaux avec support du drag and drop"""

    files_dropped = pyqtSignal(list)  # Signal émis quand des fichiers sont déposés

    def __init__(self):
        """Initialise la vue d'arbre locale"""
        super().__init__()
        self.setAcceptDrops(True)
        self.setDragEnabled(True)
        self.setDragDropMode(QTreeView.DragDrop)
        self.setAlternatingRowColors(True)
        self.setSelectionMode(QTreeView.ExtendedSelection)
        self.setSortingEnabled(True)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        """
        Gère l'événement d'entrée de drag

        Args:
            event: Événement de drag
        """
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:
        """
        Gère l'événement de déplacement de drag

        Args:
            event: Événement de drag
        """
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        """
        Gère l'événement de drop

        Args:
            event: Événement de drop
        """
        if event.mimeData().hasUrls():
            file_paths = []
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    file_paths.append(url.toLocalFile())

            if file_paths:
                self.files_dropped.emit(file_paths)
                event.acceptProposedAction()
        else:
            super().dropEvent(event)

    def set_column_widths(self, widths: List[int]) -> None:
        """
        Définit la largeur des colonnes

        Args:
            widths: Liste des largeurs pour chaque colonne
        """
        for i, width in enumerate(widths):
            if i < self.model().columnCount():
                self.setColumnWidth(i, width)

    def resize_columns_to_contents(self) -> None:
        """Redimensionne automatiquement les colonnes selon leur contenu"""
        for i in range(self.model().columnCount()):
            self.resizeColumnToContents(i)


class DriveTreeView(QTreeView):
    """Vue personnalisée pour Google Drive avec support du drag and drop"""

    files_dropped = pyqtSignal(list)  # Signal pour fichiers internes déplacés
    local_files_dropped = pyqtSignal(list)  # Signal pour fichiers locaux déposés

    def __init__(self):
        """Initialise la vue d'arbre Google Drive"""
        super().__init__()
        self.setAcceptDrops(True)
        self.setDragEnabled(True)
        self.setDragDropMode(QTreeView.DragDrop)
        self.setAlternatingRowColors(True)
        self.setSelectionMode(QTreeView.ExtendedSelection)
        self.setSortingEnabled(True)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        """
        Gère l'événement d'entrée de drag

        Args:
            event: Événement de drag
        """
        if event.mimeData().hasUrls() or event.mimeData().hasText():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:
        """
        Gère l'événement de déplacement de drag

        Args:
            event: Événement de drag
        """
        if event.mimeData().hasUrls() or event.mimeData().hasText():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        """
        Gère l'événement de drop

        Args:
            event: Événement de drop
        """
        if event.mimeData().hasUrls():
            # Fichiers locaux déposés
            file_paths = []
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    file_paths.append(url.toLocalFile())

            if file_paths:
                self.local_files_dropped.emit(file_paths)
                event.acceptProposedAction()
        elif event.mimeData().hasText():
            # Potentiellement des fichiers Google Drive internes
            # Pour l'instant, on ne gère pas le déplacement interne
            super().dropEvent(event)
        else:
            super().dropEvent(event)

    def set_column_widths(self, widths: List[int]) -> None:
        """
        Définit la largeur des colonnes

        Args:
            widths: Liste des largeurs pour chaque colonne
        """
        for i, width in enumerate(widths):
            if i < self.model().columnCount():
                self.setColumnWidth(i, width)

    def hide_column(self, column: int) -> None:
        """
        Cache une colonne

        Args:
            column: Index de la colonne à cacher
        """
        self.setColumnHidden(column, True)

    def show_column(self, column: int) -> None:
        """
        Affiche une colonne

        Args:
            column: Index de la colonne à afficher
        """
        self.setColumnHidden(column, False)

    def resize_columns_to_contents(self) -> None:
        """Redimensionne automatiquement les colonnes selon leur contenu"""
        for i in range(self.model().columnCount()):
            if not self.isColumnHidden(i):
                self.resizeColumnToContents(i)

    def get_selected_items(self) -> List[dict]:
        """
        Récupère les éléments sélectionnés

        Returns:
            Liste des informations des éléments sélectionnés
        """
        selected_items = []
        indexes = self.selectedIndexes()

        if not indexes:
            return selected_items

        # Grouper par ligne
        rows = {}
        for index in indexes:
            row = index.row()
            if row not in rows:
                rows[row] = {}
            rows[row][index.column()] = self.model().item(row, index.column())

        # Convertir en liste d'informations
        for row, items in rows.items():
            if 0 in items and items[0]:  # Au moins le nom doit être présent
                item_info = {
                    'row': row,
                    'name': items.get(0, '').text() if items.get(0) else '',
                    'size': items.get(1, '').text() if items.get(1) else '',
                    'date': items.get(2, '').text() if items.get(2) else '',
                    'type': items.get(3, '').text() if items.get(3) else '',
                    'id': items.get(4, '').text() if items.get(4) else '',
                }
                selected_items.append(item_info)

        return selected_items

    def clear_selection_and_focus(self) -> None:
        """Efface la sélection et le focus"""
        self.clearSelection()
        self.clearFocus()
"""
Modèles de données pour les listes de fichiers
"""

import os
from typing import List, Tuple
from PyQt5.QtGui import QStandardItemModel


class FileListModel(QStandardItemModel):
    """Modèle personnalisé pour les listes de fichiers Google Drive"""

    def __init__(self, headers: List[str]):
        """
        Initialise le modèle

        Args:
            headers: Liste des en-têtes de colonnes
        """
        super().__init__()
        self.setHorizontalHeaderLabels(headers + ["Statut"])
        self.current_path_id = 'root'
        self.current_drive_id = 'root'
        self.path_history: List[Tuple[str, str]] = [('Racine', 'root')]

    def reset_to_root(self) -> None:
        """Remet le modèle à la racine"""
        self.current_path_id = 'root'
        self.current_drive_id = 'root'
        self.path_history = [('Racine', 'root')]

    def navigate_to_folder(self, folder_name: str, folder_id: str) -> None:
        """
        Navigue vers un dossier

        Args:
            folder_name: Nom du dossier
            folder_id: ID du dossier
        """
        self.path_history.append((folder_name, folder_id))
        self.current_path_id = folder_id

    def go_back(self) -> bool:
        """
        Remonte d'un niveau dans l'arborescence

        Returns:
            True si le retour est possible, False sinon
        """
        if len(self.path_history) > 1:
            self.path_history.pop()
            parent_name, parent_id = self.path_history[-1]
            self.current_path_id = parent_id
            return True
        return False

    def get_path_string(self) -> str:
        """
        Retourne le chemin actuel sous forme de chaîne

        Returns:
            Chaîne représentant le chemin
        """
        if self.current_path_id == 'root':
            return "☁️ Racine"
        else:
            path_text = " / ".join([name for name, _ in self.path_history])
            return f"☁️ {path_text}"

    def can_go_back(self) -> bool:
        """
        Vérifie si on peut remonter d'un niveau

        Returns:
            True si possible, False sinon
        """
        return len(self.path_history) > 1


class LocalFileModel(QStandardItemModel):
    """Modèle pour les fichiers locaux"""

    def __init__(self, headers: List[str]):
        """
        Initialise le modèle local

        Args:
            headers: Liste des en-têtes de colonnes
        """
        super().__init__()
        self.setHorizontalHeaderLabels(headers + ["Statut"])
        self.current_path = os.path.expanduser("~")

    def set_current_path(self, path: str) -> None:
        """
        Définit le chemin actuel

        Args:
            path: Nouveau chemin
        """
        if os.path.isdir(path):
            self.current_path = path

    def can_go_up(self) -> bool:
        """
        Vérifie si on peut remonter d'un niveau

        Returns:
            True si possible, False sinon
        """
        return self.current_path != os.path.dirname(self.current_path)

    def go_up(self) -> str:
        """
        Remonte d'un niveau dans l'arborescence

        Returns:
            Nouveau chemin parent
        """
        if self.can_go_up():
            self.current_path = os.path.dirname(self.current_path)
        return self.current_path

    def navigate_to(self, folder_name: str) -> str:
        """
        Navigue vers un sous-dossier

        Args:
            folder_name: Nom du dossier

        Returns:
            Nouveau chemin
        """
        new_path = os.path.join(self.current_path, folder_name)
        if os.path.isdir(new_path):
            self.current_path = new_path
        return self.current_path

    def get_parent_path(self) -> str:
        """
        Retourne le chemin du dossier parent

        Returns:
            Chemin du parent
        """
        return os.path.dirname(self.current_path)

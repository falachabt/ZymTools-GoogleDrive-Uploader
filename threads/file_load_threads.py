"""
Threads pour charger les fichiers en arrière-plan
"""

import os
from typing import List, Dict, Any, Tuple
from PyQt5.QtCore import QThread, pyqtSignal

from core.google_drive_client import GoogleDriveClient


class LocalFileLoadThread(QThread):
    """Thread pour charger les fichiers locaux en arrière-plan"""

    files_loaded = pyqtSignal(str, list)  # path, file_list
    error_occurred = pyqtSignal(str, str)  # path, error_message

    def __init__(self, path: str):
        """
        Initialise le thread de chargement local

        Args:
            path: Chemin du dossier à charger
        """
        super().__init__()
        self.path = path

    def run(self) -> None:
        """Charge les fichiers locaux"""
        try:
            file_list = []

            # Ajouter l'élément "Remonter" si nécessaire
            if self.path != os.path.dirname(self.path):
                file_list.append({
                    'name': '..',
                    'type': 'parent',
                    'size': '',
                    'modified': '',
                    'is_dir': True
                })

            # Lister les fichiers et dossiers
            items = []
            for item in os.listdir(self.path):
                item_path = os.path.join(self.path, item)
                try:
                    stats = os.stat(item_path)
                    is_dir = os.path.isdir(item_path)

                    file_info = {
                        'name': item,
                        'type': 'folder' if is_dir else 'file',
                        'size': '' if is_dir else stats.st_size,
                        'modified': stats.st_mtime,
                        'is_dir': is_dir,
                        'path': item_path
                    }
                    items.append(file_info)
                except Exception:
                    # Ignorer les fichiers inaccessibles
                    pass

            # Trier: dossiers d'abord, puis par nom
            items.sort(key=lambda x: (not x['is_dir'], x['name'].lower()))
            file_list.extend(items)

            self.files_loaded.emit(self.path, file_list)

        except Exception as e:
            self.error_occurred.emit(self.path, str(e))


class DriveFileLoadThread(QThread):
    """Thread pour charger les fichiers Google Drive en arrière-plan"""

    files_loaded = pyqtSignal(str, list)  # folder_id, file_list
    error_occurred = pyqtSignal(str, str)  # folder_id, error_message

    def __init__(self, drive_client: GoogleDriveClient, folder_id: str,
                 current_path_history: List[Tuple[str, str]]):
        """
        Initialise le thread de chargement Google Drive

        Args:
            drive_client: Client Google Drive
            folder_id: ID du dossier à charger
            current_path_history: Historique du chemin actuel
        """
        super().__init__()
        self.drive_client = drive_client
        self.folder_id = folder_id
        self.current_path_history = current_path_history

    def run(self) -> None:
        """Charge les fichiers Google Drive"""
        try:
            file_list = []

            # Ajouter l'élément "Remonter" si nécessaire
            if len(self.current_path_history) > 1:
                parent_id = self.current_path_history[-2][1]
                file_list.append({
                    'name': '..',
                    'type': 'parent',
                    'size': '',
                    'modified': '',
                    'mimeType': 'application/vnd.google-apps.folder',
                    'id': parent_id,
                    'is_dir': True
                })

            # Obtenir les fichiers du dossier
            files = self.drive_client.list_files(self.folder_id)

            # Traiter et trier les fichiers
            folders = []
            other_files = []

            for file in files:
                file_info = {
                    'name': file.get('name', ''),
                    'type': 'folder' if file.get('mimeType') == 'application/vnd.google-apps.folder' else 'file',
                    'size': int(file.get('size', 0)) if 'size' in file else 0,
                    'modified': file.get('modifiedTime', ''),
                    'mimeType': file.get('mimeType', ''),
                    'id': file.get('id', ''),
                    'is_dir': file.get('mimeType') == 'application/vnd.google-apps.folder'
                }

                if file_info['is_dir']:
                    folders.append(file_info)
                else:
                    other_files.append(file_info)

            # Trier par nom
            folders.sort(key=lambda x: x['name'].lower())
            other_files.sort(key=lambda x: x['name'].lower())

            file_list.extend(folders + other_files)

            self.files_loaded.emit(self.folder_id, file_list)

        except Exception as e:
            self.error_occurred.emit(self.folder_id, str(e))

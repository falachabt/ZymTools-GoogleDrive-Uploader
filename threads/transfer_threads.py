"""
Threads pour les opérations d'upload et download
"""

import os
import time
from PyQt5.QtCore import QThread, pyqtSignal

from core.google_drive_client import GoogleDriveClient


class UploadThread(QThread):
    """Thread pour uploader les fichiers en arrière-plan"""

    progress_signal = pyqtSignal(int)
    completed_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)
    status_signal = pyqtSignal(str)
    time_signal = pyqtSignal(float)

    def __init__(self, drive_client: GoogleDriveClient, file_path: str,
                 parent_id: str = 'root', is_shared_drive: bool = False):
        """
        Initialise le thread d'upload

        Args:
            drive_client: Client Google Drive
            file_path: Chemin du fichier à uploader
            parent_id: ID du dossier parent de destination
            is_shared_drive: True si c'est un Shared Drive
        """
        super().__init__()
        self.drive_client = drive_client
        self.file_path = file_path
        self.parent_id = parent_id
        self.is_shared_drive = is_shared_drive
        self.file_size = os.path.getsize(file_path) if os.path.isfile(file_path) else 0

    def run(self) -> None:
        """Exécute l'upload du fichier"""
        start_time = time.time()
        try:
            file_id = self.drive_client.upload_file(
                self.file_path,
                self.parent_id,
                self.progress_signal,
                self.status_signal,
                self.is_shared_drive
            )
            self.completed_signal.emit(file_id)
            total_time = time.time() - start_time
            self.time_signal.emit(total_time)
        except Exception as e:
            self.error_signal.emit(str(e))


class FolderUploadThread(QThread):
    """Thread pour uploader les dossiers complets en arrière-plan"""

    progress_signal = pyqtSignal(int)
    completed_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)
    status_signal = pyqtSignal(str)
    time_signal = pyqtSignal(float)

    def __init__(self, drive_client: GoogleDriveClient, folder_path: str,
                 parent_id: str = 'root', is_shared_drive: bool = False):
        """
        Initialise le thread d'upload de dossier

        Args:
            drive_client: Client Google Drive
            folder_path: Chemin du dossier à uploader
            parent_id: ID du dossier parent de destination
            is_shared_drive: True si c'est un Shared Drive
        """
        super().__init__()
        self.drive_client = drive_client
        self.folder_path = folder_path
        self.parent_id = parent_id
        self.is_shared_drive = is_shared_drive
        self.total_files = 0
        self.uploaded_files = 0

    def count_files(self, path: str) -> int:
        """
        Compte le nombre total de fichiers dans un dossier

        Args:
            path: Chemin du dossier

        Returns:
            Nombre de fichiers
        """
        count = 0
        for root, dirs, files in os.walk(path):
            count += len(files)
        return count

    def upload_folder_recursive(self, local_path: str, drive_parent_id: str) -> str:
        """
        Upload récursivement un dossier et son contenu

        Args:
            local_path: Chemin local du dossier
            drive_parent_id: ID du dossier parent dans Google Drive

        Returns:
            ID du dossier créé dans Google Drive
        """
        folder_name = os.path.basename(local_path)
        folder_id = self.drive_client.create_folder(folder_name, drive_parent_id, self.is_shared_drive)
        self.status_signal.emit(f"📁 Dossier créé: {folder_name}")

        for item in os.listdir(local_path):
            item_path = os.path.join(local_path, item)
            if os.path.isdir(item_path):
                self.upload_folder_recursive(item_path, folder_id)
            else:
                try:
                    self.status_signal.emit(f"⬆️ Upload: {os.path.basename(item_path)}")
                    self.drive_client.upload_file(item_path, folder_id, None, None, self.is_shared_drive)
                    self.uploaded_files += 1
                    progress = int((self.uploaded_files / self.total_files) * 100)
                    self.progress_signal.emit(progress)
                except Exception as e:
                    self.error_signal.emit(f"❌ Erreur upload {item_path}: {str(e)}")

        return folder_id

    def run(self) -> None:
        """Exécute l'upload du dossier"""
        start_time = time.time()
        try:
            self.total_files = self.count_files(self.folder_path)
            self.status_signal.emit(f"🚀 Upload de {self.total_files} fichiers...")
            folder_id = self.upload_folder_recursive(self.folder_path, self.parent_id)
            self.completed_signal.emit(folder_id)
            total_time = time.time() - start_time
            self.time_signal.emit(total_time)
        except Exception as e:
            self.error_signal.emit(str(e))


class DownloadThread(QThread):
    """Thread pour télécharger les fichiers en arrière-plan"""

    progress_signal = pyqtSignal(int)
    completed_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)
    time_signal = pyqtSignal(float)

    def __init__(self, drive_client: GoogleDriveClient, file_id: str,
                 file_name: str, local_dir: str):
        """
        Initialise le thread de téléchargement

        Args:
            drive_client: Client Google Drive
            file_id: ID du fichier à télécharger
            file_name: Nom du fichier
            local_dir: Dossier de destination local
        """
        super().__init__()
        self.drive_client = drive_client
        self.file_id = file_id
        self.file_name = file_name
        self.local_dir = local_dir

    def run(self) -> None:
        """Exécute le téléchargement du fichier"""
        start_time = time.time()
        try:
            file_path = self.drive_client.download_file(
                self.file_id,
                self.file_name,
                self.local_dir,
                self.progress_signal
            )
            self.completed_signal.emit(file_path)
            total_time = time.time() - start_time
            self.time_signal.emit(total_time)
        except Exception as e:
            self.error_signal.emit(str(e))
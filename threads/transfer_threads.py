"""
Threads améliorés pour les opérations d'upload et download avec gestion des transferts
"""

import os
import time
from typing import Optional
from PyQt5.QtCore import QThread, pyqtSignal

from core.google_drive_client import GoogleDriveClient
from models.transfer_models import TransferManager, TransferType, TransferStatus


class UploadThread(QThread):
    """Thread amélioré pour uploader les fichiers avec gestion des transferts"""

    progress_signal = pyqtSignal(int)
    completed_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)
    status_signal = pyqtSignal(str)
    time_signal = pyqtSignal(float)

    def __init__(self, drive_client: GoogleDriveClient, file_path: str,
                 parent_id: str = 'root', is_shared_drive: bool = False,
                 transfer_manager: Optional[TransferManager] = None):
        """
        Initialise le thread d'upload amélioré

        Args:
            drive_client: Client Google Drive
            file_path: Chemin du fichier à uploader
            parent_id: ID du dossier parent de destination
            is_shared_drive: True si c'est un Shared Drive
            transfer_manager: Gestionnaire de transferts
        """
        super().__init__()
        self.drive_client = drive_client
        self.file_path = file_path
        self.parent_id = parent_id
        self.is_shared_drive = is_shared_drive
        self.transfer_manager = transfer_manager
        self.file_size = os.path.getsize(file_path) if os.path.isfile(file_path) else 0
        self.transfer_id: Optional[str] = None
        self.is_cancelled = False
        self.is_paused = False
        self.bytes_transferred = 0
        self.start_time = 0

    def run(self) -> None:
        """Exécute l'upload du fichier"""
        self.start_time = time.time()
        file_name = os.path.basename(self.file_path)

        # Créer l'entrée de transfert
        if self.transfer_manager:
            self.transfer_id = self.transfer_manager.add_transfer(
                TransferType.UPLOAD_FILE,
                self.file_path,
                f"Google Drive/{self.parent_id}",
                file_name,
                self.file_size
            )

        try:
            file_id = self.drive_client.upload_file(
                self.file_path,
                self.parent_id,
                self.progress_callback,
                self.status_callback,
                self.is_shared_drive
            )

            if not self.is_cancelled:
                self.completed_signal.emit(file_id)
                if self.transfer_manager and self.transfer_id:
                    self.transfer_manager.update_transfer_status(
                        self.transfer_id, TransferStatus.COMPLETED
                    )

                total_time = time.time() - self.start_time
                self.time_signal.emit(total_time)

        except Exception as e:
            if not self.is_cancelled:
                self.error_signal.emit(str(e))
                if self.transfer_manager and self.transfer_id:
                    self.transfer_manager.update_transfer_status(
                        self.transfer_id, TransferStatus.ERROR, str(e)
                    )

    def progress_callback(self, progress: int) -> None:
        """Callback pour le progrès d'upload"""
        if self.is_cancelled:
            return

        self.progress_signal.emit(progress)

        if self.transfer_manager and self.transfer_id:
            # Calculer les bytes transférés et la vitesse
            current_time = time.time()
            elapsed_time = current_time - self.start_time

            if elapsed_time > 0:
                self.bytes_transferred = int((progress / 100.0) * self.file_size)
                speed = self.bytes_transferred / elapsed_time

                self.transfer_manager.update_transfer_progress(
                    self.transfer_id, progress, self.bytes_transferred, speed
                )

    def status_callback(self, status: str) -> None:
        """Callback pour le statut d'upload"""
        if not self.is_cancelled:
            self.status_signal.emit(status)

    def cancel(self) -> None:
        """Annule l'upload"""
        self.is_cancelled = True
        if self.transfer_manager and self.transfer_id:
            self.transfer_manager.update_transfer_status(
                self.transfer_id, TransferStatus.CANCELLED
            )

    def pause(self) -> None:
        """Suspend l'upload (fonctionnalité future)"""
        self.is_paused = True
        if self.transfer_manager and self.transfer_id:
            self.transfer_manager.update_transfer_status(
                self.transfer_id, TransferStatus.PAUSED
            )

    def resume(self) -> None:
        """Reprend l'upload (fonctionnalité future)"""
        self.is_paused = False
        if self.transfer_manager and self.transfer_id:
            self.transfer_manager.update_transfer_status(
                self.transfer_id, TransferStatus.IN_PROGRESS
            )


class FolderUploadThread(QThread):
    """Thread amélioré pour uploader les dossiers avec gestion des transferts"""

    progress_signal = pyqtSignal(int)
    completed_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)
    status_signal = pyqtSignal(str)
    time_signal = pyqtSignal(float)

    def __init__(self, drive_client: GoogleDriveClient, folder_path: str,
                 parent_id: str = 'root', is_shared_drive: bool = False,
                 transfer_manager: Optional[TransferManager] = None):
        """
        Initialise le thread d'upload de dossier amélioré

        Args:
            drive_client: Client Google Drive
            folder_path: Chemin du dossier à uploader
            parent_id: ID du dossier parent de destination
            is_shared_drive: True si c'est un Shared Drive
            transfer_manager: Gestionnaire de transferts
        """
        super().__init__()
        self.drive_client = drive_client
        self.folder_path = folder_path
        self.parent_id = parent_id
        self.is_shared_drive = is_shared_drive
        self.transfer_manager = transfer_manager
        self.total_files = 0
        self.uploaded_files = 0
        self.transfer_id: Optional[str] = None
        self.is_cancelled = False
        self.start_time = 0
        self.total_size = 0

    def count_files_and_size(self, path: str) -> tuple:
        """
        Compte le nombre total de fichiers et leur taille dans un dossier

        Args:
            path: Chemin du dossier

        Returns:
            Tuple (nombre de fichiers, taille totale)
        """
        count = 0
        total_size = 0
        try:
            for root, dirs, files in os.walk(path):
                for file in files:
                    file_path = os.path.join(root, file)
                    try:
                        count += 1
                        total_size += os.path.getsize(file_path)
                    except (OSError, IOError):
                        pass
        except Exception:
            pass
        return count, total_size

    def upload_folder_recursive(self, local_path: str, drive_parent_id: str) -> str:
        """
        Upload récursivement un dossier et son contenu

        Args:
            local_path: Chemin local du dossier
            drive_parent_id: ID du dossier parent dans Google Drive

        Returns:
            ID du dossier créé dans Google Drive
        """
        if self.is_cancelled:
            return ""

        folder_name = os.path.basename(local_path)
        folder_id = self.drive_client.create_folder(folder_name, drive_parent_id, self.is_shared_drive)
        self.status_signal.emit(f"📁 Dossier créé: {folder_name}")

        try:
            items = os.listdir(local_path)
        except (OSError, IOError):
            return folder_id

        for item in items:
            if self.is_cancelled:
                break

            item_path = os.path.join(local_path, item)
            if os.path.isdir(item_path):
                self.upload_folder_recursive(item_path, folder_id)
            else:
                try:
                    self.status_signal.emit(f"⬆️ Upload: {os.path.basename(item_path)}")
                    self.drive_client.upload_file(item_path, folder_id, None, None, self.is_shared_drive)
                    self.uploaded_files += 1

                    # Mettre à jour le progrès
                    progress = int((self.uploaded_files / self.total_files) * 100)
                    self.progress_signal.emit(progress)

                    # Mettre à jour le transfert
                    if self.transfer_manager and self.transfer_id:
                        elapsed_time = time.time() - self.start_time
                        if elapsed_time > 0:
                            speed = (self.uploaded_files * (self.total_size / self.total_files)) / elapsed_time
                            self.transfer_manager.update_transfer_progress(
                                self.transfer_id, progress,
                                self.uploaded_files * (self.total_size // self.total_files), speed
                            )

                except Exception as e:
                    self.error_signal.emit(f"❌ Erreur upload {item_path}: {str(e)}")

        return folder_id

    def run(self) -> None:
        """Exécute l'upload du dossier"""
        self.start_time = time.time()
        folder_name = os.path.basename(self.folder_path)

        # Compter les fichiers et calculer la taille totale
        self.total_files, self.total_size = self.count_files_and_size(self.folder_path)

        # Créer l'entrée de transfert
        if self.transfer_manager:
            self.transfer_id = self.transfer_manager.add_transfer(
                TransferType.UPLOAD_FOLDER,
                self.folder_path,
                f"Google Drive/{self.parent_id}",
                folder_name,
                self.total_size
            )

        try:
            self.status_signal.emit(f"🚀 Upload de {self.total_files} fichiers...")
            folder_id = self.upload_folder_recursive(self.folder_path, self.parent_id)

            if not self.is_cancelled:
                self.completed_signal.emit(folder_id)
                if self.transfer_manager and self.transfer_id:
                    self.transfer_manager.update_transfer_status(
                        self.transfer_id, TransferStatus.COMPLETED
                    )

                total_time = time.time() - self.start_time
                self.time_signal.emit(total_time)

        except Exception as e:
            if not self.is_cancelled:
                self.error_signal.emit(str(e))
                if self.transfer_manager and self.transfer_id:
                    self.transfer_manager.update_transfer_status(
                        self.transfer_id, TransferStatus.ERROR, str(e)
                    )

    def cancel(self) -> None:
        """Annule l'upload du dossier"""
        self.is_cancelled = True
        if self.transfer_manager and self.transfer_id:
            self.transfer_manager.update_transfer_status(
                self.transfer_id, TransferStatus.CANCELLED
            )


class DownloadThread(QThread):
    """Thread amélioré pour télécharger les fichiers avec gestion des transferts"""

    progress_signal = pyqtSignal(int)
    completed_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)
    time_signal = pyqtSignal(float)

    def __init__(self, drive_client: GoogleDriveClient, file_id: str,
                 file_name: str, local_dir: str, file_size: int = 0,
                 transfer_manager: Optional[TransferManager] = None):
        """
        Initialise le thread de téléchargement amélioré

        Args:
            drive_client: Client Google Drive
            file_id: ID du fichier à télécharger
            file_name: Nom du fichier
            local_dir: Dossier de destination local
            file_size: Taille du fichier (pour le calcul de vitesse)
            transfer_manager: Gestionnaire de transferts
        """
        super().__init__()
        self.drive_client = drive_client
        self.file_id = file_id
        self.file_name = file_name
        self.local_dir = local_dir
        self.file_size = file_size
        self.transfer_manager = transfer_manager
        self.transfer_id: Optional[str] = None
        self.is_cancelled = False
        self.start_time = 0
        self.bytes_transferred = 0

    def run(self) -> None:
        """Exécute le téléchargement du fichier"""
        self.start_time = time.time()

        # Créer l'entrée de transfert
        if self.transfer_manager:
            self.transfer_id = self.transfer_manager.add_transfer(
                TransferType.DOWNLOAD_FILE,
                f"Google Drive/{self.file_id}",
                self.local_dir,
                self.file_name,
                self.file_size
            )

        try:
            file_path = self.drive_client.download_file(
                self.file_id,
                self.file_name,
                self.local_dir,
                self.progress_callback
            )

            if not self.is_cancelled:
                self.completed_signal.emit(file_path)
                if self.transfer_manager and self.transfer_id:
                    self.transfer_manager.update_transfer_status(
                        self.transfer_id, TransferStatus.COMPLETED
                    )

                total_time = time.time() - self.start_time
                self.time_signal.emit(total_time)

        except Exception as e:
            if not self.is_cancelled:
                self.error_signal.emit(str(e))
                if self.transfer_manager and self.transfer_id:
                    self.transfer_manager.update_transfer_status(
                        self.transfer_id, TransferStatus.ERROR, str(e)
                    )

    def progress_callback(self, progress: int) -> None:
        """Callback pour le progrès de téléchargement"""
        if self.is_cancelled:
            return

        self.progress_signal.emit(progress)

        if self.transfer_manager and self.transfer_id and self.file_size > 0:
            # Calculer les bytes transférés et la vitesse
            current_time = time.time()
            elapsed_time = current_time - self.start_time

            if elapsed_time > 0:
                self.bytes_transferred = int((progress / 100.0) * self.file_size)
                speed = self.bytes_transferred / elapsed_time

                self.transfer_manager.update_transfer_progress(
                    self.transfer_id, progress, self.bytes_transferred, speed
                )

    def cancel(self) -> None:
        """Annule le téléchargement"""
        self.is_cancelled = True
        if self.transfer_manager and self.transfer_id:
            self.transfer_manager.update_transfer_status(
                self.transfer_id, TransferStatus.CANCELLED
            )
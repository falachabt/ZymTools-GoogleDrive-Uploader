"""
Threads améliorés pour les opérations d'upload et download avec gestion des transferts et parallélisme
"""

import os
import time
from typing import Optional, List, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
from PyQt5.QtCore import QThread, pyqtSignal, QMutex, QMutexLocker

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
    """Thread amélioré pour uploader les dossiers avec parallélisme et gestion des transferts"""

    progress_signal = pyqtSignal(int)
    completed_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)
    status_signal = pyqtSignal(str)
    time_signal = pyqtSignal(float)

    def __init__(self, drive_client: GoogleDriveClient, folder_path: str,
                 parent_id: str = 'root', is_shared_drive: bool = False,
                 transfer_manager: Optional[TransferManager] = None,
                 max_parallel_uploads: int = 2):
        """
        Initialise le thread d'upload de dossier avec parallélisme

        Args:
            drive_client: Client Google Drive
            folder_path: Chemin du dossier à uploader
            parent_id: ID du dossier parent de destination
            is_shared_drive: True si c'est un Shared Drive
            transfer_manager: Gestionnaire de transferts
            max_parallel_uploads: Nombre maximum d'uploads simultanés
        """
        super().__init__()
        self.drive_client = drive_client
        self.folder_path = folder_path
        self.parent_id = parent_id
        self.is_shared_drive = is_shared_drive
        self.transfer_manager = transfer_manager
        self.max_parallel_uploads = max_parallel_uploads
        self.total_files = 0
        self.uploaded_files = 0
        self.transfer_id: Optional[str] = None
        self.is_cancelled = False
        self.start_time = 0
        self.total_size = 0

        # Mutex pour protéger les accès concurrents
        self.progress_mutex = QMutex()
        self.cancelled_mutex = QMutex()

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

    def collect_all_files(self, folder_path: str) -> List[Dict[str, Any]]:
        """
        Collecte tous les fichiers et dossiers de manière récursive

        Args:
            folder_path: Chemin du dossier à analyser

        Returns:
            Liste des fichiers avec leurs informations
        """
        files_to_process = []

        for root, dirs, files in os.walk(folder_path):
            # Calculer le chemin relatif pour recréer la structure
            rel_path = os.path.relpath(root, folder_path)

            for file in files:
                file_path = os.path.join(root, file)
                files_to_process.append({
                    'file_path': file_path,
                    'file_name': file,
                    'relative_dir': rel_path if rel_path != '.' else '',
                    'size': os.path.getsize(file_path) if os.path.exists(file_path) else 0
                })

        return files_to_process

    def create_folder_structure(self, folder_path: str, parent_id: str) -> Dict[str, str]:
        """
        Crée la structure de dossiers sur Google Drive

        Args:
            folder_path: Chemin du dossier local
            parent_id: ID du dossier parent sur Drive

        Returns:
            Dictionnaire mapping chemin relatif -> ID du dossier Drive
        """
        folder_mapping = {'': parent_id}  # Racine

        try:
            # Parcourir tous les dossiers
            for root, dirs, files in os.walk(folder_path):
                rel_path = os.path.relpath(root, folder_path)

                if rel_path == '.':
                    continue

                # Trouver le dossier parent
                parent_rel_path = os.path.dirname(rel_path)
                if parent_rel_path == '.':
                    parent_rel_path = ''

                if parent_rel_path in folder_mapping:
                    parent_drive_id = folder_mapping[parent_rel_path]
                    folder_name = os.path.basename(root)

                    # Créer le dossier sur Drive
                    self.status_signal.emit(f"📁 Création du dossier: {rel_path}")
                    folder_id = self.drive_client.create_folder(
                        folder_name, parent_drive_id, self.is_shared_drive
                    )
                    folder_mapping[rel_path] = folder_id

        except Exception as e:
            self.error_signal.emit(f"Erreur lors de la création des dossiers: {str(e)}")

        return folder_mapping

    def upload_file_batch(self, file_batch: List[Dict[str, Any]],
                         folder_mapping: Dict[str, str]) -> List[Dict[str, Any]]:
        """
        Upload un batch de fichiers en parallèle

        Args:
            file_batch: Liste des fichiers à uploader
            folder_mapping: Mapping des dossiers relatifs vers IDs Drive

        Returns:
            Liste des résultats d'upload
        """
        results = []

        def upload_single_file(file_info):
            """Upload un seul fichier"""
            try:
                with QMutexLocker(self.cancelled_mutex):
                    if self.is_cancelled:
                        return {'success': False, 'cancelled': True, 'file_info': file_info}

                # Déterminer le dossier parent
                parent_id = folder_mapping.get(file_info['relative_dir'], self.parent_id)

                # Upload du fichier
                file_id = self.drive_client.upload_file(
                    file_info['file_path'],
                    parent_id,
                    None,  # Pas de callback de progrès individuel
                    None,  # Pas de callback de statut individuel
                    self.is_shared_drive
                )

                return {
                    'success': True,
                    'file_id': file_id,
                    'file_info': file_info
                }

            except Exception as e:
                print("Erreur lors de l'upload du fichier:", file_info['file_name'], str(e))
                return {
                    'success': False,
                    'error': str(e),
                    'file_info': file_info
                }

        # Utiliser ThreadPoolExecutor pour le parallélisme
        with ThreadPoolExecutor(max_workers=self.max_parallel_uploads) as executor:
            # Soumettre tous les uploads
            future_to_file = {
                executor.submit(upload_single_file, file_info): file_info
                for file_info in file_batch
            }

            # Traiter les résultats au fur et à mesure
            for future in as_completed(future_to_file):
                result = future.result()
                results.append(result)

                # Mettre à jour le progrès
                with QMutexLocker(self.progress_mutex):
                    self.uploaded_files += 1
                    progress = int((self.uploaded_files / self.total_files) * 100)
                    self.progress_signal.emit(progress)

                    # Mettre à jour le transfert
                    if self.transfer_manager and self.transfer_id:
                        elapsed_time = time.time() - self.start_time
                        if elapsed_time > 0:
                            avg_file_size = self.total_size / self.total_files if self.total_files > 0 else 0
                            speed = (self.uploaded_files * avg_file_size) / elapsed_time
                            self.transfer_manager.update_transfer_progress(
                                self.transfer_id, progress,
                                int(self.uploaded_files * avg_file_size), speed
                            )

                # Émettre le statut
                if result['success']:
                    file_name = result['file_info']['file_name']
                    self.status_signal.emit(f"✅ Terminé: {file_name}")
                else:
                    if not result.get('cancelled', False):
                        file_name = result['file_info']['file_name']
                        error = result.get('error', 'Erreur inconnue')
                        self.status_signal.emit(f"❌ Erreur {file_name}: {error}")

                # Vérifier l'annulation
                with QMutexLocker(self.cancelled_mutex):
                    if self.is_cancelled:
                        break

        return results

    def run(self) -> None:
        """Exécute l'upload du dossier avec parallélisme"""
        self.start_time = time.time()
        folder_name = os.path.basename(self.folder_path)

        try:
            # Compter les fichiers et calculer la taille totale
            self.total_files, self.total_size = self.count_files_and_size(self.folder_path)

            if self.total_files == 0:
                self.status_signal.emit("📁 Dossier vide, création du dossier uniquement...")
                folder_id = self.drive_client.create_folder(folder_name, self.parent_id, self.is_shared_drive)
                self.completed_signal.emit(folder_id)
                return

            # Créer l'entrée de transfert
            if self.transfer_manager:
                self.transfer_id = self.transfer_manager.add_transfer(
                    TransferType.UPLOAD_FOLDER,
                    self.folder_path,
                    f"Google Drive/{self.parent_id}",
                    folder_name,
                    self.total_size
                )

            self.status_signal.emit(f"🚀 Analyse de {self.total_files} fichiers...")

            # Créer le dossier racine
            main_folder_id = self.drive_client.create_folder(folder_name, self.parent_id, self.is_shared_drive)

            # Créer la structure de dossiers
            self.status_signal.emit("📁 Création de la structure de dossiers...")
            folder_mapping = self.create_folder_structure(self.folder_path, main_folder_id)

            # Collecter tous les fichiers
            all_files = self.collect_all_files(self.folder_path)

            # Diviser en batchs pour éviter de surcharger
            batch_size = max(1, min(self.max_parallel_uploads * 2, len(all_files)))
            file_batches = [all_files[i:i + batch_size] for i in range(0, len(all_files), batch_size)]

            self.status_signal.emit(f"⚡ Upload parallèle de {self.total_files} fichiers ({self.max_parallel_uploads} simultanés)...")

            # Traiter chaque batch
            all_errors = []
            for i, batch in enumerate(file_batches):
                if self.is_cancelled:
                    break

                self.status_signal.emit(f"📦 Batch {i+1}/{len(file_batches)} ({len(batch)} fichiers)...")
                results = self.upload_file_batch(batch, folder_mapping)

                # Collecter les erreurs
                for result in results:
                    if not result['success'] and not result.get('cancelled', False):
                        error_msg = f"❌ {result['file_info']['file_name']}: {result.get('error', 'Erreur inconnue')}"
                        all_errors.append(error_msg)

            if not self.is_cancelled:
                if all_errors:
                    error_summary = f"Upload terminé avec {len(all_errors)} erreur(s):\n" + "\n".join(all_errors[:5])
                    if len(all_errors) > 5:
                        error_summary += f"\n... et {len(all_errors) - 5} autres erreurs"
                    self.error_signal.emit(error_summary)

                self.completed_signal.emit(main_folder_id)
                if self.transfer_manager and self.transfer_id:
                    self.transfer_manager.update_transfer_status(
                        self.transfer_id, TransferStatus.COMPLETED
                    )

                total_time = time.time() - self.start_time
                self.time_signal.emit(total_time)

                # Statistiques finales
                success_count = self.uploaded_files - len(all_errors)
                self.status_signal.emit(f"🎉 Upload terminé: {success_count}/{self.total_files} fichiers réussis en {total_time:.1f}s")

        except Exception as e:
            if not self.is_cancelled:
                self.error_signal.emit(str(e))
                if self.transfer_manager and self.transfer_id:
                    self.transfer_manager.update_transfer_status(
                        self.transfer_id, TransferStatus.ERROR, str(e)
                    )

    def cancel(self) -> None:
        """Annule l'upload du dossier"""
        with QMutexLocker(self.cancelled_mutex):
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
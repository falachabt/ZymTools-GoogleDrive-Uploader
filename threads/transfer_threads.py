"""
Threads améliorés et sécurisés pour les opérations d'upload et download avec gestion robuste des erreurs
"""

import os
import time
import threading
from typing import Optional, List, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
from PyQt5.QtCore import QThread, pyqtSignal, QMutex, QMutexLocker
import random
from utils.google_drive_utils import  already_exists_in_folder

from core.google_drive_client import GoogleDriveClient
from models.transfer_models import TransferManager, TransferType, TransferStatus


class SafeGoogleDriveUploader:
    """Classe utilitaire pour des uploads sécurisés avec rate limiting"""

    # Verrou global pour les opérations critiques
    _upload_lock = threading.Lock()
    _last_upload_time = 0
    _upload_count = 0
    _rate_limit_window = 3  # 1 minute
    _max_uploads_per_window = 700  # Maximum 100 uploads par minute

    @staticmethod
    def get_fresh_client():
        """Crée une nouvelle instance de client Google Drive"""
        from core.google_drive_client import GoogleDriveClient
        return GoogleDriveClient()

    @classmethod
    def safe_upload_file(cls, file_path: str,
                         parent_id: str, is_shared_drive: bool = False,
                         max_retries: int = 3) -> str:
        """
        Upload sécurisé d'un fichier avec retry et rate limiting

        Args:
            drive_client: Client Google Drive
            file_path: Chemin du fichier
            parent_id: ID du dossier parent
            is_shared_drive: Si c'est un shared drive
            max_retries: Nombre maximum de tentatives

        Returns:
            ID du fichier uploadé

        Raises:
            Exception: Si l'upload échoue après tous les retries
        """
        for attempt in range(max_retries):
            try:
                # Rate limiting
                with cls._upload_lock:
                    current_time = time.time()

                    # Reset du compteur si on est dans une nouvelle fenêtre
                    if current_time - cls._last_upload_time > cls._rate_limit_window:
                        cls._upload_count = 0

                    # Vérifier la limite de taux
                    if cls._upload_count >= cls._max_uploads_per_window:
                        sleep_time = cls._rate_limit_window - (current_time - cls._last_upload_time)
                        if sleep_time > 0:
                            time.sleep(sleep_time)
                            cls._upload_count = 0

                    cls._upload_count += 1
                    cls._last_upload_time = current_time

                # Ajouter un délai aléatoire pour éviter les collisions
                if attempt > 0:
                    time.sleep(random.uniform(0.05, 0.08) * attempt)

                # Tentative d'upload avec un nouveau client
                drive_client = cls.get_fresh_client()
                try:
                    file_id = drive_client.upload_file(
                        file_path, parent_id, None, None, is_shared_drive
                    )
                    return file_id
                except Exception as e:

                    # Vérifier si le fichier existe déjà dans le dossier
                    file_name = os.path.basename(file_path)
                    if already_exists_in_folder(drive_client, parent_id, file_name):
                        # Si le fichier existe déjà, on peut skippper
                        drive_client.close()
                        break

                    # Fermer le client en cas d'erreur
                    drive_client.close()
                    raise e

            except Exception as e:
                error_msg = str(e).lower()

                # Erreurs qui méritent un retry
                if any(keyword in error_msg for keyword in [
                    'ssl', 'timeout', 'connection', 'rate', 'quota', 'temporary'
                ]):
                    if attempt < max_retries - 1:
                        wait_time = (2 ** attempt) + random.uniform(0, 1)  # Exponential backoff
                        print(f"Erreur temporaire, retry dans {wait_time:.1f}s: {e}")
                        time.sleep(wait_time)
                        continue

                # Erreur finale ou non-recoverable
                if attempt == max_retries - 1:
                    raise e

        raise Exception("Upload échoué après tous les retries")


class UploadThread(QThread):
    """Thread amélioré pour uploader les fichiers avec gestion robuste des erreurs"""

    progress_signal = pyqtSignal(int)
    completed_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)
    status_signal = pyqtSignal(str)
    time_signal = pyqtSignal(float)

    def __init__(self, drive_client: GoogleDriveClient, file_path: str,
                 parent_id: str = 'root', is_shared_drive: bool = False,
                 transfer_manager: Optional[TransferManager] = None):
        """
        Initialise le thread d'upload sécurisé

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
        self.start_time = 0

    def run(self) -> None:
        """Exécute l'upload du fichier de manière sécurisée"""
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
            self.status_signal.emit(f"⬆️ Préparation: {file_name}")

            # Upload sécurisé avec retry
            file_id = SafeGoogleDriveUploader.safe_upload_file(
                self.file_path, self.parent_id,
                self.is_shared_drive
            )

            if not self.is_cancelled:
                self.progress_signal.emit(100)
                self.completed_signal.emit(file_id)
                if self.transfer_manager and self.transfer_id:
                    self.transfer_manager.update_transfer_status(
                        self.transfer_id, TransferStatus.COMPLETED
                    )

                total_time = time.time() - self.start_time
                self.time_signal.emit(total_time)
                self.status_signal.emit(f"✅ Terminé: {file_name}")

        except Exception as e:
            if not self.is_cancelled:
                error_msg = f"Erreur upload {file_name}: {str(e)}"
                self.error_signal.emit(error_msg)
                if self.transfer_manager and self.transfer_id:
                    self.transfer_manager.update_transfer_status(
                        self.transfer_id, TransferStatus.ERROR, str(e)
                    )

    def cancel(self) -> None:
        """Annule l'upload"""
        self.is_cancelled = True
        if self.transfer_manager and self.transfer_id:
            self.transfer_manager.update_transfer_status(
                self.transfer_id, TransferStatus.CANCELLED
            )


class SafeFolderUploadThread(QThread):
    """Thread ultra-sécurisé pour uploader les dossiers avec gestion robuste des erreurs"""

    progress_signal = pyqtSignal(int)
    completed_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)
    status_signal = pyqtSignal(str)
    time_signal = pyqtSignal(float)

    def __init__(self, drive_client: GoogleDriveClient, folder_path: str,
                 parent_id: str = 'root', is_shared_drive: bool = False,
                 transfer_manager: Optional[TransferManager] = None,
                 max_parallel_uploads: int = 3):  # Par défaut 1 pour la sécurité
        """
        Initialise le thread d'upload de dossier sécurisé

        Args:
            drive_client: Client Google Drive
            folder_path: Chemin du dossier à uploader
            parent_id: ID du dossier parent de destination
            is_shared_drive: True si c'est un Shared Drive
            transfer_manager: Gestionnaire de transferts
            max_parallel_uploads: Nombre maximum d'uploads simultanés (recommandé: 1-2)
        """
        super().__init__()
        self.drive_client = drive_client
        self.folder_path = folder_path
        self.parent_id = parent_id
        self.is_shared_drive = is_shared_drive
        self.transfer_manager = transfer_manager
        # Limiter à un maximum sécurisé25
        self.max_parallel_uploads = max(max_parallel_uploads, 10 )
        self.total_files = 0
        self.uploaded_files = 0
        self.failed_files = 0
        self.transfer_id: Optional[str] = None
        self.is_cancelled = False
        self.start_time = 0
        self.total_size = 0

        # Mutex pour protéger les accès concurrents
        self.progress_mutex = QMutex()
        self.cancelled_mutex = QMutex()

    def count_files_and_size(self, path: str) -> tuple:
        """Compte les fichiers et leur taille totale"""
        count = 0
        total_size = 0
        try:
            for root, dirs, files in os.walk(path):
                for file in files:
                    if not file.lower().endswith('.tif'):
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
        """Collecte tous les fichiers de manière récursive"""
        files_to_process = []

        try:
            for root, dirs, files in os.walk(folder_path):
                rel_path = os.path.relpath(root, folder_path)

                for file in files:
                    if not file.lower().endswith('.tif'):
                        file_path = os.path.join(root, file)
                        if os.path.exists(file_path):
                            files_to_process.append({
                                'file_path': file_path,
                                'file_name': file,
                                'relative_dir': rel_path if rel_path != '.' else '',
                                'size': os.path.getsize(file_path)
                            })
        except Exception as e:
            print(f"Erreur lors de la collecte des fichiers: {e}")

        return files_to_process

    def create_folder_structure_safe(self, folder_path: str, parent_id: str) -> Dict[str, str]:
        """Crée la structure de dossiers de manière sécurisée"""
        folder_mapping = {'': parent_id}
        
        try:
            # Créer les dossiers un par un avec délais
            for root, dirs, files in os.walk(folder_path):
                rel_path = os.path.relpath(root, folder_path)

                if rel_path == '.' or self.is_cancelled:
                    continue

                parent_rel_path = os.path.dirname(rel_path)
                if parent_rel_path == '.':
                    parent_rel_path = ''

                if parent_rel_path in folder_mapping:
                    parent_drive_id = folder_mapping[parent_rel_path]
                    folder_name = os.path.basename(root)

                    self.status_signal.emit(f"📁 Création: {rel_path}")

                    # Retry pour la création de dossiers
                    for attempt in range(3):
                        try:
                            # Ajoutez ce type d’appel à chaque opération Drive pour isolation SSL :
                            fresh_client = self.get_fresh_client()
                            # Utilisez ensuite fresh_client pour vos opérations Google Drive (création de dossier, etc.)
                            folder_id = fresh_client.create_folder(
                                folder_name, parent_drive_id, self.is_shared_drive
                            )
                            folder_mapping[rel_path] = folder_id
                            break
                        except Exception as e:
                            if attempt < 2:
                                time.sleep(1 + attempt)  # Délai progressif
                                continue
                            else:
                                raise e

                    # Petit délai entre créations de dossiers
                    time.sleep(0.2)

        except Exception as e:
            self.error_signal.emit(f"Erreur création dossiers: {str(e)}")

        return folder_mapping

    def get_fresh_client(self) -> GoogleDriveClient:
        """Crée une nouvelle instance de client Google Drive"""
        return SafeGoogleDriveUploader.get_fresh_client()

    def upload_files_batch_safe(self, file_batch: List[Dict[str, Any]],
                               folder_mapping: Dict[str, str]) -> List[Dict[str, Any]]:
        """Upload un batch de fichiers de manière ultra-sécurisée"""
        results = []

        def upload_single_file_safe(file_info):
            """Upload sécurisé d'un seul fichier"""
            try:
                with QMutexLocker(self.cancelled_mutex):
                    if self.is_cancelled:
                        return {'success': False, 'cancelled': True, 'file_info': file_info}

                # Déterminer le dossier parent
                parent_id = folder_mapping.get(file_info['relative_dir'], self.parent_id)

                # Status update
                file_name = file_info['file_name']

                # Upload sécurisé avec retry
                file_id = SafeGoogleDriveUploader.safe_upload_file(
                    file_info['file_path'], parent_id,
                    self.is_shared_drive
                )

                return {
                    'success': True,
                    'file_id': file_id,
                    'file_info': file_info
                }

            except Exception as e:
                return {
                    'success': False,
                    'error': str(e),
                    'file_info': file_info
                }

        # Upload séquentiel si max_parallel_uploads = 1, sinon parallèle limité
        if self.max_parallel_uploads == 1:
            # Upload séquentiel - plus sûr
            for file_info in file_batch:
                if self.is_cancelled:
                    break

                result = upload_single_file_safe(file_info)
                results.append(result)

                # Mettre à jour le progrès
                with QMutexLocker(self.progress_mutex):
                    if result['success']:
                        self.uploaded_files += 1
                    else:
                        self.failed_files += 1

                    progress = int(((self.uploaded_files + self.failed_files) / self.total_files) * 100)
                    self.progress_signal.emit(progress)

                    # Mettre à jour le transfert
                    if self.transfer_manager and self.transfer_id:
                        elapsed_time = time.time() - self.start_time
                        if elapsed_time > 0:
                            avg_file_size = self.total_size / self.total_files if self.total_files > 0 else 0
                            speed = ((self.uploaded_files + self.failed_files) * avg_file_size) / elapsed_time
                            self.transfer_manager.update_transfer_progress(
                                self.transfer_id, progress,
                                int((self.uploaded_files + self.failed_files) * avg_file_size), speed
                            )

                # Status
                if result['success']:
                    self.status_signal.emit(f"✅ Terminé: {result['file_info']['file_name']}")
                else:
                    if not result.get('cancelled', False):
                        self.status_signal.emit(f"❌ Erreur: {result['file_info']['file_name']}")

                # Délai entre uploads pour éviter le rate limiting
                if not self.is_cancelled:
                    time.sleep(0.001)  # 100ms entre chaque fichier
        else:
            # Upload parallèle très limité et sécurisé
            with ThreadPoolExecutor(max_workers=self.max_parallel_uploads) as executor:
                # Soumettre les uploads avec délais
                futures = []
                for i, file_info in enumerate(file_batch):
                    if self.is_cancelled:
                        break

                    future = executor.submit(upload_single_file_safe, file_info)
                    futures.append(future)

                    # Délai entre soumissions pour éviter la surcharge
                    if i < len(file_batch) - 1:
                        time.sleep(0.003)

                # Traiter les résultats
                for future in as_completed(futures):
                    if self.is_cancelled:
                        break

                    result = future.result()
                    results.append(result)

                    # Mettre à jour le progrès (même code que séquentiel)
                    with QMutexLocker(self.progress_mutex):
                        if result['success']:
                            self.uploaded_files += 1
                        else:
                            self.failed_files += 1

                        progress = int(((self.uploaded_files + self.failed_files) / self.total_files) * 100)
                        self.progress_signal.emit(progress)

                        if self.transfer_manager and self.transfer_id:
                            elapsed_time = time.time() - self.start_time
                            if elapsed_time > 0:
                                avg_file_size = self.total_size / self.total_files if self.total_files > 0 else 0
                                speed = ((self.uploaded_files + self.failed_files) * avg_file_size) / elapsed_time
                                self.transfer_manager.update_transfer_progress(
                                    self.transfer_id, progress,
                                    int((self.uploaded_files + self.failed_files) * avg_file_size), speed
                                )

                    # Status
                    if result['success']:
                        self.status_signal.emit(f"✅ Terminé: {result['file_info']['file_name']}")
                    else:
                        if not result.get('cancelled', False):
                            self.status_signal.emit(f"❌ Erreur: {result['file_info']['file_name']}")

        return results

    def run(self) -> None:
        """Exécute l'upload du dossier de manière ultra-sécurisée"""
        self.start_time = time.time()
        folder_name = os.path.basename(self.folder_path)

        try:
            # Compter les fichiers
            self.total_files, self.total_size = self.count_files_and_size(self.folder_path)

            if self.total_files == 0:
                self.status_signal.emit("📁 Dossier vide, création uniquement...")
                # Ajoutez ce type d’appel à chaque opération Drive pour isolation SSL :
                fresh_client = self.get_fresh_client()
                # Utilisez ensuite fresh_client pour vos opérations Google Drive (création de dossier, etc.)
                folder_id = fresh_client.create_folder(folder_name, self.parent_id, self.is_shared_drive)
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

            self.status_signal.emit(f"🚀 Analyse: {self.total_files} fichiers...")

            # Créer le dossier racine
            # Ajoutez ce type d’appel à chaque opération Drive pour isolation SSL :
            fresh_client = self.get_fresh_client()
            # Utilisez ensuite fresh_client pour vos opérations Google Drive (création de dossier, etc.)
            main_folder_id = fresh_client.create_folder(folder_name, self.parent_id, self.is_shared_drive)

            # Créer la structure de dossiers de manière sécurisée
            self.status_signal.emit("📁 Création structure...")
            folder_mapping = self.create_folder_structure_safe(self.folder_path, main_folder_id)

            if self.is_cancelled:
                return

            # Collecter tous les fichiers
            all_files = self.collect_all_files(self.folder_path)

            # Upload avec batch plus petits pour la sécurité
            batch_size = max(1, min(100, len(all_files)))  # Batch très petit
            file_batches = [all_files[i:i + batch_size] for i in range(0, len(all_files), batch_size)]

            self.status_signal.emit(f"⚡ Upload: {self.total_files} fichiers (mode: {'séquentiel' if self.max_parallel_uploads == 1 else 'parallèle limité'})...")

            # Traiter chaque batch avec délais
            all_errors = []
            for i, batch in enumerate(file_batches):
                if self.is_cancelled:
                    break

                self.status_signal.emit(f"📦 Batch {i+1}/{len(file_batches)} ({len(batch)} fichiers)...")
                results = self.upload_files_batch_safe(batch, folder_mapping)

                # Collecter les erreurs
                for result in results:
                    if not result['success'] and not result.get('cancelled', False):
                        error_msg = f"❌ {result['file_info']['file_name']}: {result.get('error', 'Erreur inconnue')}"
                        all_errors.append(error_msg)

                # Délai entre batches pour éviter la surcharge
                if i < len(file_batches) - 1 and not self.is_cancelled:
                    time.sleep(0.0003)  # 1 seconde entre batches

            if not self.is_cancelled:
                # Rapport final
                success_count = self.uploaded_files
                total_time = time.time() - self.start_time

                if all_errors:
                    error_summary = f"Upload terminé avec {len(all_errors)} erreur(s):\n" + "\n".join(all_errors[:3])
                    if len(all_errors) > 3:
                        error_summary += f"\n... et {len(all_errors) - 3} autres erreurs"
                    self.error_signal.emit(error_summary)

                # Considérer comme terminé même avec quelques erreurs
                self.completed_signal.emit(main_folder_id)
                if self.transfer_manager and self.transfer_id:
                    final_status = TransferStatus.COMPLETED if len(all_errors) == 0 else TransferStatus.ERROR
                    self.transfer_manager.update_transfer_status(self.transfer_id, final_status)

                self.time_signal.emit(total_time)
                self.status_signal.emit(f"🎉 Terminé: {success_count}/{self.total_files} fichiers en {total_time:.1f}s")

        except Exception as e:
            if not self.is_cancelled:
                self.error_signal.emit(f"Erreur fatale: {str(e)}")
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


# Alias pour maintenir la compatibilité
FolderUploadThread = SafeFolderUploadThread


class DownloadThread(QThread):
    """Thread sécurisé pour télécharger les fichiers"""

    progress_signal = pyqtSignal(int)
    completed_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)
    time_signal = pyqtSignal(float)

    def __init__(self, drive_client: GoogleDriveClient, file_id: str,
                 file_name: str, local_dir: str, file_size: int = 0,
                 transfer_manager: Optional[TransferManager] = None):
        """
        Initialise le thread de téléchargement sécurisé

        Args:
            drive_client: Client Google Drive
            file_id: ID du fichier à télécharger
            file_name: Nom du fichier
            local_dir: Dossier de destination local
            file_size: Taille du fichier
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

    def run(self) -> None:
        """Exécute le téléchargement sécurisé"""
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
            # Téléchargement avec retry
            for attempt in range(3):
                try:
                    file_path = self.drive_client.download_file(
                        self.file_id, self.file_name, self.local_dir, self.progress_callback
                    )

                    if not self.is_cancelled:
                        self.completed_signal.emit(file_path)
                        if self.transfer_manager and self.transfer_id:
                            self.transfer_manager.update_transfer_status(
                                self.transfer_id, TransferStatus.COMPLETED
                            )

                        total_time = time.time() - self.start_time
                        self.time_signal.emit(total_time)

                    return  # Succès, sortir de la boucle

                except Exception as e:
                    if attempt < 2:  # Retry
                        time.sleep(1 + attempt)
                        continue
                    else:
                        raise e

        except Exception as e:
            if not self.is_cancelled:
                self.error_signal.emit(str(e))
                if self.transfer_manager and self.transfer_id:
                    self.transfer_manager.update_transfer_status(
                        self.transfer_id, TransferStatus.ERROR, str(e)
                    )

    def progress_callback(self, progress: int) -> None:
        """Callback sécurisé pour le progrès"""
        if self.is_cancelled:
            return

        self.progress_signal.emit(progress)

        if self.transfer_manager and self.transfer_id and self.file_size > 0:
            current_time = time.time()
            elapsed_time = current_time - self.start_time

            if elapsed_time > 0:
                bytes_transferred = int((progress / 100.0) * self.file_size)
                speed = bytes_transferred / elapsed_time

                self.transfer_manager.update_transfer_progress(
                    self.transfer_id, progress, bytes_transferred, speed
                )

    def cancel(self) -> None:
        """Annule le téléchargement"""
        self.is_cancelled = True
        if self.transfer_manager and self.transfer_id:
            self.transfer_manager.update_transfer_status(
                self.transfer_id, TransferStatus.CANCELLED
            )
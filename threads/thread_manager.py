
"""
Gestionnaire centralisé amélioré pour toutes les opérations de threads
avec instances API séparées et gestion des files d'attente
"""

import time
import threading
from typing import Dict, List, Optional, Queue
from queue import Queue as ThreadQueue
from PyQt5.QtCore import QObject, pyqtSignal, QTimer, QMutex, QMutexLocker

from core.google_drive_client import GoogleDriveClient
from models.transfer_models import TransferManager
from .file_operation_threads import FileUploadThread, FolderUploadThread, FileDownloadThread


class ThreadManager(QObject):
    """Gestionnaire centralisé pour toutes les opérations de threads avec files d'attente"""
    
    # Signaux pour les événements de threads
    thread_started = pyqtSignal(str)  # thread_id
    thread_completed = pyqtSignal(str, str)  # thread_id, result
    thread_error = pyqtSignal(str, str)  # thread_id, error
    thread_progress = pyqtSignal(str, int)  # thread_id, progress
    queue_updated = pyqtSignal()  # Signal quand la file d'attente change
    
    def __init__(self, transfer_manager: Optional[TransferManager] = None, max_concurrent_uploads: int = 3):
        """
        Initialise le gestionnaire de threads
        
        Args:
            transfer_manager: Gestionnaire de transferts optionnel
            max_concurrent_uploads: Nombre maximum d'uploads simultanés
        """
        super().__init__()
        self.transfer_manager = transfer_manager
        self.max_concurrent_uploads = max_concurrent_uploads
        
        # Threads actifs
        self.active_threads: Dict[str, object] = {}
        self.thread_counter = 0
        
        # Files d'attente pour différents types d'opérations
        self.upload_queue: ThreadQueue = ThreadQueue()
        self.download_queue: ThreadQueue = ThreadQueue()
        
        # Compteurs pour contrôler la concurrence
        self.active_uploads = 0
        self.active_downloads = 0
        
        # Mutex pour la protection des accès concurrents
        self.upload_mutex = QMutex()
        self.download_mutex = QMutex()
        
        # Cache des clients Google Drive pour éviter les conflits SSL
        self.drive_clients_cache: List[GoogleDriveClient] = []
        self.available_clients: ThreadQueue = ThreadQueue()
        
        # Initialiser le pool de clients
        self._initialize_client_pool()
        
        # Timer pour traiter les files d'attente
        self.queue_processor_timer = QTimer()
        self.queue_processor_timer.timeout.connect(self.process_queues)
        self.queue_processor_timer.start(1000)  # Vérifier toutes les secondes
        
        # Timer de nettoyage
        self.cleanup_timer = QTimer()
        self.cleanup_timer.timeout.connect(self.cleanup_finished_threads)
        self.cleanup_timer.start(30000)  # Nettoyage toutes les 30 secondes
    
    def _initialize_client_pool(self) -> None:
        """Initialise un pool de clients Google Drive"""
        for i in range(self.max_concurrent_uploads + 2):  # +2 pour les téléchargements
            try:
                client = GoogleDriveClient()
                self.drive_clients_cache.append(client)
                self.available_clients.put(client)
            except Exception as e:
                print(f"Erreur lors de la création du client {i}: {e}")
    
    def _get_available_client(self) -> Optional[GoogleDriveClient]:
        """Récupère un client disponible du pool"""
        try:
            return self.available_clients.get_nowait()
        except:
            # Si aucun client disponible, créer un nouveau
            try:
                return GoogleDriveClient()
            except Exception as e:
                print(f"Erreur lors de la création d'un nouveau client: {e}")
                return None
    
    def _return_client(self, client: GoogleDriveClient) -> None:
        """Remet un client dans le pool"""
        try:
            self.available_clients.put_nowait(client)
        except:
            # Si la queue est pleine, ignorer
            pass
    
    def _generate_thread_id(self) -> str:
        """Génère un ID de thread unique"""
        self.thread_counter += 1
        return f"thread_{int(time.time())}_{self.thread_counter}"
    
    def queue_file_upload(self, file_path: str, parent_id: str = 'root',
                         is_shared_drive: bool = False, priority: int = 0) -> str:
        """
        Ajoute un upload de fichier à la file d'attente
        
        Args:
            file_path: Chemin du fichier à uploader
            parent_id: ID du dossier parent
            is_shared_drive: True si c'est un Shared Drive
            priority: Priorité (plus élevé = traité en premier)
        
        Returns:
            Thread ID pour le suivi
        """
        thread_id = self._generate_thread_id()
        
        upload_task = {
            'type': 'file_upload',
            'thread_id': thread_id,
            'file_path': file_path,
            'parent_id': parent_id,
            'is_shared_drive': is_shared_drive,
            'priority': priority,
            'timestamp': time.time()
        }
        
        self.upload_queue.put(upload_task)
        self.queue_updated.emit()
        
        return thread_id
    
    def queue_folder_upload(self, folder_path: str, parent_id: str = 'root',
                           is_shared_drive: bool = False, priority: int = 0,
                           max_workers: int = 2) -> str:
        """
        Ajoute un upload de dossier à la file d'attente
        
        Args:
            folder_path: Chemin du dossier à uploader
            parent_id: ID du dossier parent
            is_shared_drive: True si c'est un Shared Drive
            priority: Priorité
            max_workers: Nombre de workers pour ce dossier
        
        Returns:
            Thread ID pour le suivi
        """
        thread_id = self._generate_thread_id()
        
        upload_task = {
            'type': 'folder_upload',
            'thread_id': thread_id,
            'folder_path': folder_path,
            'parent_id': parent_id,
            'is_shared_drive': is_shared_drive,
            'priority': priority,
            'max_workers': max_workers,
            'timestamp': time.time()
        }
        
        self.upload_queue.put(upload_task)
        self.queue_updated.emit()
        
        return thread_id
    
    def queue_file_download(self, file_id: str, file_name: str,
                           local_dir: str, file_size: int = 0, priority: int = 0) -> str:
        """
        Ajoute un téléchargement de fichier à la file d'attente
        
        Returns:
            Thread ID pour le suivi
        """
        thread_id = self._generate_thread_id()
        
        download_task = {
            'type': 'file_download',
            'thread_id': thread_id,
            'file_id': file_id,
            'file_name': file_name,
            'local_dir': local_dir,
            'file_size': file_size,
            'priority': priority,
            'timestamp': time.time()
        }
        
        self.download_queue.put(download_task)
        self.queue_updated.emit()
        
        return thread_id
    
    def process_queues(self) -> None:
        """Traite les files d'attente pour démarrer de nouveaux threads"""
        # Traiter les uploads
        with QMutexLocker(self.upload_mutex):
            while (self.active_uploads < self.max_concurrent_uploads and 
                   not self.upload_queue.empty()):
                try:
                    task = self.upload_queue.get_nowait()
                    self._start_upload_task(task)
                except:
                    break
        
        # Traiter les téléchargements (moins de limite)
        with QMutexLocker(self.download_mutex):
            while (self.active_downloads < 2 and  # Max 2 téléchargements simultanés
                   not self.download_queue.empty()):
                try:
                    task = self.download_queue.get_nowait()
                    self._start_download_task(task)
                except:
                    break
    
    def _start_upload_task(self, task: dict) -> None:
        """Démarre une tâche d'upload"""
        client = self._get_available_client()
        if not client:
            # Remettre la tâche en queue si pas de client disponible
            self.upload_queue.put(task)
            return
        
        thread_id = task['thread_id']
        
        if task['type'] == 'file_upload':
            thread = FileUploadThread(
                client, task['file_path'], task['parent_id'],
                task['is_shared_drive'], self.transfer_manager
            )
        elif task['type'] == 'folder_upload':
            thread = FolderUploadThread(
                client, task['folder_path'], task['parent_id'],
                task['is_shared_drive'], self.transfer_manager,
                task.get('max_workers', 2)
            )
        else:
            self._return_client(client)
            return
        
        # Connecter les signaux
        self._setup_thread_connections(thread, thread_id, client)
        
        # Démarrer le thread
        self.active_threads[thread_id] = thread
        self.active_uploads += 1
        thread.start()
        
        self.thread_started.emit(thread_id)
    
    def _start_download_task(self, task: dict) -> None:
        """Démarre une tâche de téléchargement"""
        client = self._get_available_client()
        if not client:
            self.download_queue.put(task)
            return
        
        thread_id = task['thread_id']
        
        thread = FileDownloadThread(
            client, task['file_id'], task['file_name'],
            task['local_dir'], task['file_size'], self.transfer_manager
        )
        
        self._setup_thread_connections(thread, thread_id, client)
        
        self.active_threads[thread_id] = thread
        self.active_downloads += 1
        thread.start()
        
        self.thread_started.emit(thread_id)
    
    def _setup_thread_connections(self, thread, thread_id: str, client: GoogleDriveClient) -> None:
        """Configure les connexions de signaux pour un thread"""
        thread.progress_signal.connect(lambda p: self.thread_progress.emit(thread_id, p))
        thread.completed_signal.connect(lambda r: self._on_thread_completed(thread_id, r, client))
        thread.error_signal.connect(lambda e: self._on_thread_error(thread_id, e, client))
    
    def _on_thread_completed(self, thread_id: str, result: str, client: GoogleDriveClient) -> None:
        """Gère la completion d'un thread"""
        self._cleanup_thread(thread_id, client)
        self.thread_completed.emit(thread_id, result)
    
    def _on_thread_error(self, thread_id: str, error: str, client: GoogleDriveClient) -> None:
        """Gère les erreurs de thread"""
        self._cleanup_thread(thread_id, client)
        self.thread_error.emit(thread_id, error)
    
    def _cleanup_thread(self, thread_id: str, client: GoogleDriveClient) -> None:
        """Nettoie un thread terminé"""
        if thread_id in self.active_threads:
            thread = self.active_threads[thread_id]
            
            # Déterminer le type de thread pour décrémenter le bon compteur
            if isinstance(thread, (FileUploadThread, FolderUploadThread)):
                with QMutexLocker(self.upload_mutex):
                    self.active_uploads = max(0, self.active_uploads - 1)
            else:
                with QMutexLocker(self.download_mutex):
                    self.active_downloads = max(0, self.active_downloads - 1)
            
            del self.active_threads[thread_id]
        
        # Remettre le client dans le pool
        self._return_client(client)
        
        # Traiter la prochaine tâche
        self.process_queues()
    
    def cancel_thread(self, thread_id: str) -> bool:
        """Annule un thread spécifique"""
        if thread_id in self.active_threads:
            thread = self.active_threads[thread_id]
            if hasattr(thread, 'cancel'):
                thread.cancel()
                return True
        return False
    
    def cancel_all_uploads(self) -> None:
        """Annule tous les uploads"""
        for thread_id, thread in list(self.active_threads.items()):
            if isinstance(thread, (FileUploadThread, FolderUploadThread)):
                if hasattr(thread, 'cancel'):
                    thread.cancel()
    
    def get_queue_status(self) -> dict:
        """Retourne le statut des files d'attente"""
        return {
            'uploads_queued': self.upload_queue.qsize(),
            'downloads_queued': self.download_queue.qsize(),
            'active_uploads': self.active_uploads,
            'active_downloads': self.active_downloads,
            'max_concurrent_uploads': self.max_concurrent_uploads
        }
    
    def cleanup_finished_threads(self) -> None:
        """Nettoie les threads terminés"""
        finished_threads = []
        for thread_id, thread in self.active_threads.items():
            if not thread.isRunning():
                finished_threads.append(thread_id)
        
        for thread_id in finished_threads:
            if thread_id in self.active_threads:
                del self.active_threads[thread_id]
    
    def shutdown(self) -> None:
        """Arrête proprement le gestionnaire"""
        self.queue_processor_timer.stop()
        self.cleanup_timer.stop()
        
        # Annuler tous les threads actifs
        for thread in list(self.active_threads.values()):
            if hasattr(thread, 'cancel'):
                thread.cancel()
            if thread.isRunning():
                thread.wait(3000)  # Attendre max 3 secondes

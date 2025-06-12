
"""
Gestionnaire centralisé amélioré pour toutes les opérations de threads
avec instances API séparées et gestion des files d'attente
"""

import time
import threading
from typing import Dict, List, Optional
from queue import Queue as ThreadQueue
from PyQt5.QtCore import QObject, pyqtSignal, QTimer, QMutex, QMutexLocker

from core.google_drive_client import GoogleDriveClient
from models.transfer_models import TransferManager, TransferStatus
from .file_operation_threads import FileUploadThread, FolderUploadThread, FileDownloadThread


class ThreadManager(QObject):
    """Gestionnaire centralisé pour tous les threads d'opérations"""
    
    # Signaux pour l'interface
    operation_started = pyqtSignal(str)  # operation_id
    operation_completed = pyqtSignal(str)  # operation_id
    operation_error = pyqtSignal(str, str)  # operation_id, error_message
    
    def __init__(self, transfer_manager: TransferManager, max_concurrent_uploads: int = 3):
        super().__init__()
        self.transfer_manager = transfer_manager
        self.max_concurrent_uploads = max_concurrent_uploads
        
        # Threads actifs
        self.active_threads: Dict[str, threading.Thread] = {}
        
        # Files d'attente pour gérer les opérations séquentielles
        self.upload_queue: ThreadQueue = ThreadQueue()
        self.download_queue: ThreadQueue = ThreadQueue()
        
        # Compteurs d'opérations actives
        self.active_uploads = 0
        self.active_downloads = 0
        
        # Mutex pour les accès concurrents
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
                print(f"✅ Client Google Drive {i+1} initialisé")
            except Exception as e:
                print(f"❌ Erreur lors de la création du client {i+1}: {e}")
    
    def _get_available_client(self) -> Optional[GoogleDriveClient]:
        """Récupère un client disponible du pool"""
        try:
            return self.available_clients.get_nowait()
        except:
            # Si aucun client disponible, en créer un nouveau temporairement
            try:
                return GoogleDriveClient()
            except Exception as e:
                print(f"❌ Impossible de créer un nouveau client: {e}")
                return None
    
    def _return_client(self, client: GoogleDriveClient) -> None:
        """Retourne un client au pool"""
        try:
            self.available_clients.put_nowait(client)
        except:
            # File pleine, on ignore (le client sera garbage collected)
            pass
    
    def upload_file(self, file_path: str, parent_id: str = 'root', 
                   is_shared_drive: bool = False) -> str:
        """
        Ajoute un fichier à la file d'upload
        
        Returns:
            ID de l'opération
        """
        operation_data = {
            'type': 'upload_file',
            'file_path': file_path,
            'parent_id': parent_id,
            'is_shared_drive': is_shared_drive
        }
        
        operation_id = str(time.time())
        operation_data['operation_id'] = operation_id
        
        self.upload_queue.put(operation_data)
        print(f"📤 Fichier ajouté à la file d'upload: {file_path}")
        
        return operation_id
    
    def upload_folder(self, folder_path: str, parent_id: str = 'root',
                     is_shared_drive: bool = False, max_workers: int = 2) -> str:
        """
        Ajoute un dossier à la file d'upload
        
        Returns:
            ID de l'opération
        """
        operation_data = {
            'type': 'upload_folder',
            'folder_path': folder_path,
            'parent_id': parent_id,
            'is_shared_drive': is_shared_drive,
            'max_workers': max_workers
        }
        
        operation_id = str(time.time())
        operation_data['operation_id'] = operation_id
        
        self.upload_queue.put(operation_data)
        print(f"📁 Dossier ajouté à la file d'upload: {folder_path}")
        
        return operation_id
    
    def download_file(self, file_id: str, file_name: str, local_dir: str,
                     file_size: int = 0) -> str:
        """
        Ajoute un fichier à la file de téléchargement
        
        Returns:
            ID de l'opération
        """
        operation_data = {
            'type': 'download_file',
            'file_id': file_id,
            'file_name': file_name,
            'local_dir': local_dir,
            'file_size': file_size
        }
        
        operation_id = str(time.time())
        operation_data['operation_id'] = operation_id
        
        self.download_queue.put(operation_data)
        print(f"📥 Fichier ajouté à la file de téléchargement: {file_name}")
        
        return operation_id
    
    def process_queues(self) -> None:
        """Traite les files d'attente d'upload et de téléchargement"""
        self._process_upload_queue()
        self._process_download_queue()
    
    def _process_upload_queue(self) -> None:
        """Traite la file d'attente d'upload"""
        with QMutexLocker(self.upload_mutex):
            while (self.active_uploads < self.max_concurrent_uploads and 
                   not self.upload_queue.empty()):
                
                try:
                    operation_data = self.upload_queue.get_nowait()
                    self._start_upload_operation(operation_data)
                    self.active_uploads += 1
                except:
                    break
    
    def _process_download_queue(self) -> None:
        """Traite la file d'attente de téléchargement"""
        with QMutexLocker(self.download_mutex):
            while self.active_downloads < 2 and not self.download_queue.empty():
                try:
                    operation_data = self.download_queue.get_nowait()
                    self._start_download_operation(operation_data)
                    self.active_downloads += 1
                except:
                    break
    
    def _start_upload_operation(self, operation_data: dict) -> None:
        """Démarre une opération d'upload"""
        client = self._get_available_client()
        if not client:
            print("❌ Aucun client disponible pour l'upload")
            return
        
        operation_id = operation_data['operation_id']
        
        try:
            if operation_data['type'] == 'upload_file':
                thread = FileUploadThread(
                    client,
                    operation_data['file_path'],
                    operation_data['parent_id'],
                    operation_data['is_shared_drive'],
                    self.transfer_manager
                )
            elif operation_data['type'] == 'upload_folder':
                thread = FolderUploadThread(
                    client,
                    operation_data['folder_path'],
                    operation_data['parent_id'],
                    operation_data['is_shared_drive'],
                    self.transfer_manager,
                    operation_data['max_workers']
                )
            else:
                return
            
            # Connecter les signaux
            thread.finished.connect(lambda: self._on_upload_finished(operation_id, client))
            thread.error.connect(lambda error: self._on_upload_error(operation_id, error, client))
            
            # Démarrer le thread
            thread.start()
            self.active_threads[operation_id] = thread
            self.operation_started.emit(operation_id)
            
            print(f"🚀 Démarrage opération d'upload: {operation_id}")
            
        except Exception as e:
            print(f"❌ Erreur lors du démarrage de l'upload {operation_id}: {e}")
            self._return_client(client)
            self.operation_error.emit(operation_id, str(e))
    
    def _start_download_operation(self, operation_data: dict) -> None:
        """Démarre une opération de téléchargement"""
        client = self._get_available_client()
        if not client:
            print("❌ Aucun client disponible pour le téléchargement")
            return
        
        operation_id = operation_data['operation_id']
        
        try:
            thread = FileDownloadThread(
                client,
                operation_data['file_id'],
                operation_data['file_name'],
                operation_data['local_dir'],
                operation_data['file_size'],
                self.transfer_manager
            )
            
            # Connecter les signaux
            thread.finished.connect(lambda: self._on_download_finished(operation_id, client))
            thread.error.connect(lambda error: self._on_download_error(operation_id, error, client))
            
            # Démarrer le thread
            thread.start()
            self.active_threads[operation_id] = thread
            self.operation_started.emit(operation_id)
            
            print(f"🚀 Démarrage opération de téléchargement: {operation_id}")
            
        except Exception as e:
            print(f"❌ Erreur lors du démarrage du téléchargement {operation_id}: {e}")
            self._return_client(client)
            self.operation_error.emit(operation_id, str(e))
    
    def _on_upload_finished(self, operation_id: str, client: GoogleDriveClient) -> None:
        """Gère la fin d'une opération d'upload"""
        with QMutexLocker(self.upload_mutex):
            self.active_uploads -= 1
        
        self._return_client(client)
        self.operation_completed.emit(operation_id)
        print(f"✅ Upload terminé: {operation_id}")
    
    def _on_upload_error(self, operation_id: str, error: str, client: GoogleDriveClient) -> None:
        """Gère l'erreur d'une opération d'upload"""
        with QMutexLocker(self.upload_mutex):
            self.active_uploads -= 1
        
        self._return_client(client)
        self.operation_error.emit(operation_id, error)
        print(f"❌ Erreur upload {operation_id}: {error}")
    
    def _on_download_finished(self, operation_id: str, client: GoogleDriveClient) -> None:
        """Gère la fin d'une opération de téléchargement"""
        with QMutexLocker(self.download_mutex):
            self.active_downloads -= 1
        
        self._return_client(client)
        self.operation_completed.emit(operation_id)
        print(f"✅ Téléchargement terminé: {operation_id}")
    
    def _on_download_error(self, operation_id: str, error: str, client: GoogleDriveClient) -> None:
        """Gère l'erreur d'une opération de téléchargement"""
        with QMutexLocker(self.download_mutex):
            self.active_downloads -= 1
        
        self._return_client(client)
        self.operation_error.emit(operation_id, error)
        print(f"❌ Erreur téléchargement {operation_id}: {error}")
    
    def cleanup_finished_threads(self) -> None:
        """Nettoie les threads terminés"""
        finished_threads = []
        
        for operation_id, thread in self.active_threads.items():
            if not thread.is_alive():
                finished_threads.append(operation_id)
        
        for operation_id in finished_threads:
            del self.active_threads[operation_id]
        
        if finished_threads:
            print(f"🧹 Nettoyage de {len(finished_threads)} threads terminés")
    
    def cancel_operation(self, operation_id: str) -> None:
        """Annule une opération"""
        if operation_id in self.active_threads:
            thread = self.active_threads[operation_id]
            if hasattr(thread, 'cancel_operation'):
                thread.cancel_operation()
                print(f"🚫 Annulation demandée pour: {operation_id}")
    
    def get_active_operations_count(self) -> dict:
        """Retourne le nombre d'opérations actives"""
        return {
            'uploads': self.active_uploads,
            'downloads': self.active_downloads,
            'queued_uploads': self.upload_queue.qsize(),
            'queued_downloads': self.download_queue.qsize()
        }
    
    def shutdown(self) -> None:
        """Arrête proprement le gestionnaire"""
        print("🛑 Arrêt du gestionnaire de threads...")
        
        # Arrêter les timers
        self.queue_processor_timer.stop()
        self.cleanup_timer.stop()
        
        # Annuler toutes les opérations actives
        for operation_id in list(self.active_threads.keys()):
            self.cancel_operation(operation_id)
        
        # Attendre que tous les threads se terminent (avec timeout)
        timeout = 10  # 10 secondes
        start_time = time.time()
        
        while self.active_threads and (time.time() - start_time) < timeout:
            time.sleep(0.1)
            self.cleanup_finished_threads()
        
        print(f"✅ Gestionnaire de threads arrêté ({len(self.active_threads)} threads restants)")


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

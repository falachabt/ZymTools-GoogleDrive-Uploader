"""
Unified Upload Manager - Coordinates the queue-based upload system
"""

import os
from typing import List, Optional, Dict, Any
from PyQt5.QtCore import QObject, pyqtSignal, QTimer

from models.upload_queue import UploadQueue, QueuedFile, FileStatus, FolderInfo, QueueOrdering
from threads.queue_workers import WorkerManager
from threads.folder_scanner import FolderScanner, BatchFolderScanner
from core.google_drive_client import GoogleDriveClient


class UnifiedUploadManager(QObject):
    """
    Unified manager for the new queue-based upload system.
    Coordinates scanning, queueing, and processing of uploads.
    """
    
    # High-level signals
    upload_session_started = pyqtSignal()
    upload_session_completed = pyqtSignal()
    upload_session_paused = pyqtSignal()
    upload_session_resumed = pyqtSignal()
    
    # Progress signals
    scanning_progress = pyqtSignal(str, int, int)  # folder_path, current, total
    upload_progress = pyqtSignal(dict)  # Overall statistics
    
    # Status signals
    status_message = pyqtSignal(str)  # Status message for UI
    error_occurred = pyqtSignal(str, str)  # title, message
    
    def __init__(self, drive_client: GoogleDriveClient, num_workers: int = 3, 
                 files_per_worker: int = 10):
        """
        Initialize unified upload manager
        
        Args:
            drive_client: Google Drive client
            num_workers: Number of worker threads
            files_per_worker: Maximum files per worker thread
        """
        super().__init__()
        
        self.drive_client = drive_client
        self.num_workers = num_workers
        self.files_per_worker = files_per_worker
        
        # Core components
        self.upload_queue = UploadQueue()
        self.worker_manager = None
        self.folder_scanner = None
        self.batch_scanner = None
        
        # State tracking
        self._is_active = False
        self._is_paused = False
        
        # Statistics timer
        self._stats_timer = QTimer()
        self._stats_timer.timeout.connect(self._emit_progress_update)
        self._stats_timer.start(1000)  # Update every second
        
        # Connect queue signals
        self._connect_queue_signals()
    
    def _connect_queue_signals(self):
        """Connect upload queue signals"""
        self.upload_queue.queue_statistics_changed.connect(self._on_statistics_changed)
        self.upload_queue.file_added.connect(self._on_file_added)
        self.upload_queue.file_updated.connect(self._on_file_updated)
        self.upload_queue.folder_added.connect(self._on_folder_added)
        self.upload_queue.folder_updated.connect(self._on_folder_updated)
    
    def start_upload_session(self):
        """Start the upload session with workers"""
        if self._is_active:
            return
        
        self._is_active = True
        self._is_paused = False
        
        # Create and start worker manager
        self.worker_manager = WorkerManager(
            upload_queue=self.upload_queue,
            num_workers=self.num_workers,
            files_per_worker=self.files_per_worker
        )
        
        # Connect worker manager signals
        self.worker_manager.worker_manager_started.connect(self._on_workers_started)
        self.worker_manager.worker_manager_stopped.connect(self._on_workers_stopped)
        self.worker_manager.all_workers_idle.connect(self._on_all_workers_idle)
        
        # Start workers
        self.worker_manager.start_workers()
        
        self.upload_session_started.emit()
        self.status_message.emit("🚀 Session d'upload démarrée")
    
    def stop_upload_session(self):
        """Stop the upload session"""
        if not self._is_active:
            return
        
        self._is_active = False
        self._is_paused = False
        
        # Stop workers
        if self.worker_manager:
            self.worker_manager.stop_workers()
            self.worker_manager = None
        
        # Stop scanners
        if self.folder_scanner:
            self.folder_scanner.stop()
            self.folder_scanner = None
        
        if self.batch_scanner:
            self.batch_scanner.stop()
            self.batch_scanner = None
        
        self.upload_session_completed.emit()
        self.status_message.emit("🛑 Session d'upload arrêtée")
    
    def pause_upload_session(self):
        """Pause the upload session"""
        if not self._is_active or self._is_paused:
            return
        
        self._is_paused = True
        
        if self.worker_manager:
            self.worker_manager.pause_workers()
        
        self.upload_session_paused.emit()
        self.status_message.emit("⏸️ Session d'upload suspendue")
    
    def resume_upload_session(self):
        """Resume the upload session"""
        if not self._is_active or not self._is_paused:
            return
        
        self._is_paused = False
        
        if self.worker_manager:
            self.worker_manager.resume_workers()
        
        self.upload_session_resumed.emit()
        self.status_message.emit("▶️ Session d'upload reprise")
    
    def add_files(self, file_paths: List[str], destination_id: str, 
                 is_shared_drive: bool = False) -> int:
        """
        Add individual files to upload queue
        
        Args:
            file_paths: List of file paths to upload
            destination_id: Google Drive destination folder ID
            is_shared_drive: Whether destination is a shared drive
            
        Returns:
            Number of files added
        """
        files_to_add = []
        
        for file_path in file_paths:
            if not os.path.isfile(file_path):
                continue
            
            try:
                file_size = os.path.getsize(file_path)
                file_name = os.path.basename(file_path)
                
                queued_file = QueuedFile(
                    file_path=file_path,
                    file_name=file_name,
                    file_size=file_size,
                    source_folder=os.path.dirname(file_path),
                    relative_path="",
                    destination_folder_id=destination_id
                )
                
                files_to_add.append(queued_file)
                
            except (OSError, IOError) as e:
                self.error_occurred.emit(
                    "Erreur de fichier",
                    f"Impossible d'accéder au fichier {file_path}: {e}"
                )
                continue
        
        if files_to_add:
            added_count = self.upload_queue.add_files_batch(files_to_add)
            self.status_message.emit(f"📁 {added_count} fichier(s) ajouté(s) à la file")
            
            # Auto-start session if not active
            if not self._is_active:
                self.start_upload_session()
            
            return added_count
        
        return 0
    
    def add_folder(self, folder_path: str, destination_id: str, 
                  is_shared_drive: bool = False) -> bool:
        """
        Add a folder to upload queue (scans and adds all files)
        
        Args:
            folder_path: Local folder path to upload
            destination_id: Google Drive destination folder ID
            is_shared_drive: Whether destination is a shared drive
            
        Returns:
            True if scanning started successfully
        """
        if not os.path.isdir(folder_path):
            self.error_occurred.emit(
                "Erreur de dossier",
                f"Le dossier n'existe pas: {folder_path}"
            )
            return False
        
        # Store destination for use in scanning callbacks
        self.destination_id = destination_id
        
        # Pre-register folder for immediate UI feedback
        self.upload_queue.register_folder_for_scanning(folder_path, destination_id)
        
        # Auto-start session if not active
        if not self._is_active:
            self.start_upload_session()
        
        # Create and start folder scanner
        self.folder_scanner = FolderScanner(self.upload_queue, self.drive_client)
        
        # Connect scanner signals
        self.folder_scanner.scanning_started.connect(self._on_scanning_started)
        self.folder_scanner.scanning_progress.connect(self.scanning_progress.emit)
        self.folder_scanner.folder_created.connect(self._on_folder_created)
        self.folder_scanner.files_added.connect(self._on_files_added)
        self.folder_scanner.scanning_completed.connect(self._on_scanning_completed)
        self.folder_scanner.scanning_error.connect(self._on_scanning_error)
        
        # Start scanning
        self.folder_scanner.scan_folder(folder_path, destination_id, is_shared_drive)
        
        return True
    
    def add_folders(self, folder_paths: List[str], destination_id: str, 
                   is_shared_drive: bool = False) -> bool:
        """
        Add multiple folders to upload queue
        
        Args:
            folder_paths: List of local folder paths to upload
            destination_id: Google Drive destination folder ID
            is_shared_drive: Whether destination is a shared drive
            
        Returns:
            True if scanning started successfully
        """
        valid_folders = [path for path in folder_paths if os.path.isdir(path)]
        
        if not valid_folders:
            self.error_occurred.emit(
                "Erreur de dossiers",
                "Aucun dossier valide trouvé"
            )
            return False
        
        # Store destination for use in scanning callbacks
        self.destination_id = destination_id
        
        # Pre-register all folders for immediate UI feedback
        for folder_path in valid_folders:
            self.upload_queue.register_folder_for_scanning(folder_path, destination_id)
        
        # Auto-start session if not active
        if not self._is_active:
            self.start_upload_session()
        
        # Create and start batch scanner
        self.batch_scanner = BatchFolderScanner(self.upload_queue, self.drive_client)
        
        # Connect scanner signals
        self.batch_scanner.batch_started.connect(self._on_batch_started)
        self.batch_scanner.folder_scanning_started.connect(self._on_folder_scanning_started)
        self.batch_scanner.folder_scanning_completed.connect(self._on_folder_scanning_completed)
        self.batch_scanner.folder_scanning_error.connect(self._on_folder_scanning_error)
        self.batch_scanner.batch_completed.connect(self._on_batch_completed)
        
        # Start batch scanning
        self.batch_scanner.scan_folders(valid_folders, destination_id, is_shared_drive)
        
        return True
    
    def retry_failed_files(self) -> int:
        """
        Retry all failed files in the queue
        
        Returns:
            Number of files queued for retry
        """
        retry_count = self.upload_queue.retry_all_failed()
        
        if retry_count > 0:
            self.status_message.emit(f"🔄 {retry_count} fichier(s) en cours de retry")
            
            # Auto-start session if not active
            if not self._is_active:
                self.start_upload_session()
        else:
            self.status_message.emit("⚠️ Aucun fichier à réessayer")
        
        return retry_count
    
    def retry_file(self, file_unique_id: str) -> bool:
        """
        Retry a specific failed file
        
        Args:
            file_unique_id: Unique ID of file to retry
            
        Returns:
            True if file was queued for retry
        """
        success = self.upload_queue.retry_file(file_unique_id)
        
        if success:
            self.status_message.emit("🔄 Fichier en cours de retry")
            
            # Auto-start session if not active
            if not self._is_active:
                self.start_upload_session()
        
        return success
    
    def clear_completed_files(self):
        """Clear all completed/failed/skipped files from queue"""
        self.upload_queue.clear_completed()
        self.status_message.emit("🧹 Fichiers terminés supprimés")
    
    def get_queue_statistics(self) -> Dict[str, Any]:
        """Get current queue statistics"""
        stats = self.upload_queue.get_queue_statistics()
        
        # Add worker statistics if available
        if self.worker_manager:
            worker_stats = self.worker_manager.get_overall_statistics()
            stats.update({
                'workers': {
                    'total_workers': worker_stats['total_workers'],
                    'running_workers': worker_stats['running_workers'],
                    'total_active_files': worker_stats['total_active_files'],
                    'average_speed': worker_stats['average_speed']
                }
            })
        
        return stats
    
    def get_all_files(self) -> List[QueuedFile]:
        """Get all files in queue"""
        return self.upload_queue.get_all_files()
    
    def get_all_folders(self) -> List[FolderInfo]:
        """Get all folder information"""
        return self.upload_queue.get_all_folders()
    
    def get_files_by_status(self, status: FileStatus) -> List[QueuedFile]:
        """Get files with specific status"""
        return self.upload_queue.get_files_by_status(status)
    
    def is_active(self) -> bool:
        """Check if upload session is active"""
        return self._is_active
    
    def is_paused(self) -> bool:
        """Check if upload session is paused"""
        return self._is_paused
    
    # Signal handlers
    def _on_statistics_changed(self):
        """Handle queue statistics change"""
        pass  # Progress update timer will handle this
    
    def _on_file_added(self, unique_id: str):
        """Handle file added to queue"""
        pass
    
    def _on_file_updated(self, unique_id: str):
        """Handle file status updated"""
        pass
    
    def _on_folder_added(self, folder_path: str):
        """Handle folder added to queue"""
        pass
    
    def _on_folder_updated(self, folder_path: str):
        """Handle folder statistics updated"""
        pass
    
    def _on_workers_started(self):
        """Handle workers started"""
        self.status_message.emit(f"⚡ {self.num_workers} workers démarrés")
    
    def _on_workers_stopped(self):
        """Handle workers stopped"""
        self.status_message.emit("🛑 Workers arrêtés")
    
    def _on_all_workers_idle(self):
        """Handle all workers idle"""
        if self.upload_queue.get_pending_count() == 0:
            self.status_message.emit("🎉 Tous les uploads terminés")
    
    def _on_scanning_started(self, folder_path: str):
        """Handle folder scanning started"""
        folder_name = os.path.basename(folder_path)
        self.status_message.emit(f"🔍 Scan du dossier: {folder_name}")
        
        # Pre-register folder for immediate UI feedback if destination is available
        if hasattr(self, 'destination_id') and self.destination_id:
            self.upload_queue.register_folder_for_scanning(folder_path, self.destination_id)
    
    def _on_folder_created(self, local_path: str, folder_name: str, drive_folder_id: str):
        """Handle folder created on Drive"""
        self.status_message.emit(f"📁 Dossier créé: {folder_name}")
    
    def _on_files_added(self, folder_path: str, file_count: int):
        """Handle files added to queue"""
        if file_count > 0:
            self.status_message.emit(f"📄 {file_count} fichiers ajoutés à la file")
    
    def _on_scanning_completed(self, folder_path: str, total_files: int, main_folder_id: str):
        """Handle folder scanning completed"""
        folder_name = os.path.basename(folder_path)
        self.status_message.emit(f"✅ Scan terminé: {folder_name} ({total_files} fichiers)")
        
        # Mark folder scanning as completed
        self.upload_queue.mark_folder_scan_completed(folder_path)
        
        # Reorder queue to enable concurrent folder uploads
        self.upload_queue.auto_reorder_on_folder_complete(QueueOrdering.ROUND_ROBIN)
    
    def _on_scanning_error(self, folder_path: str, error_message: str):
        """Handle scanning error"""
        folder_name = os.path.basename(folder_path)
        self.error_occurred.emit(
            "Erreur de scan",
            f"Erreur lors du scan de {folder_name}: {error_message}"
        )
    
    def _on_batch_started(self, total_folders: int):
        """Handle batch scanning started"""
        self.status_message.emit(f"🔍 Scan de {total_folders} dossiers...")
    
    def _on_folder_scanning_started(self, folder_index: int, folder_path: str):
        """Handle individual folder in batch started"""
        folder_name = os.path.basename(folder_path)
        self.status_message.emit(f"🔍 Scan ({folder_index + 1}): {folder_name}")
    
    def _on_folder_scanning_completed(self, folder_index: int, folder_path: str, 
                                    files_added: int, main_folder_id: str):
        """Handle individual folder in batch completed"""
        folder_name = os.path.basename(folder_path)
        self.status_message.emit(f"✅ Scan ({folder_index + 1}) terminé: {folder_name} ({files_added} fichiers)")
        
        # Mark folder scanning as completed
        self.upload_queue.mark_folder_scan_completed(folder_path)
        
        # Reorder queue to enable concurrent folder uploads
        self.upload_queue.auto_reorder_on_folder_complete(QueueOrdering.ROUND_ROBIN)
    
    def _on_folder_scanning_error(self, folder_index: int, folder_path: str, error: str):
        """Handle individual folder in batch error"""
        folder_name = os.path.basename(folder_path)
        self.error_occurred.emit(
            "Erreur de scan",
            f"Erreur scan ({folder_index + 1}) {folder_name}: {error}"
        )
    
    def _on_batch_completed(self, total_folders: int, total_files_added: int):
        """Handle batch scanning completed"""
        self.status_message.emit(f"🎉 Scan de {total_folders} dossiers terminé ({total_files_added} fichiers)")
    
    def _emit_progress_update(self):
        """Emit progress update signal"""
        if self._is_active:
            stats = self.get_queue_statistics()
            self.upload_progress.emit(stats)

"""
Thread manager for coordinating and managing all thread operations
"""

from typing import Dict, List, Optional, Any
from PyQt5.QtCore import QObject, pyqtSignal, QTimer

from .base_thread import BaseOperationThread
from .file_operation_threads import FileUploadThread, FolderUploadThread, FileDownloadThread
from .file_load_threads import LocalFileLoadThread, DriveFileLoadThread
from models.transfer_models import TransferManager


class ThreadManager(QObject):
    """Centralized manager for all thread operations"""
    
    # Signals for thread events
    thread_started = pyqtSignal(str)  # thread_id
    thread_completed = pyqtSignal(str, str)  # thread_id, result
    thread_error = pyqtSignal(str, str)  # thread_id, error
    thread_progress = pyqtSignal(str, int)  # thread_id, progress
    
    def __init__(self, transfer_manager: Optional[TransferManager] = None):
        """
        Initialize thread manager
        
        Args:
            transfer_manager: Optional transfer manager for tracking transfers
        """
        super().__init__()
        self.transfer_manager = transfer_manager
        self.active_threads: Dict[str, BaseOperationThread] = {}
        self.thread_counter = 0
        
        # Setup cleanup timer
        self.cleanup_timer = QTimer()
        self.cleanup_timer.timeout.connect(self.cleanup_finished_threads)
        self.cleanup_timer.start(30000)  # Cleanup every 30 seconds
    
    def _generate_thread_id(self) -> str:
        """Generate unique thread ID"""
        self.thread_counter += 1
        return f"thread_{self.thread_counter}"
    
    def start_file_upload(self, drive_client, file_path: str, parent_id: str = 'root',
                         is_shared_drive: bool = False) -> str:
        """
        Start file upload operation
        
        Returns:
            Thread ID for tracking
        """
        thread_id = self._generate_thread_id()
        thread = FileUploadThread(
            drive_client, file_path, parent_id, is_shared_drive, self.transfer_manager
        )
        
        self._setup_thread_connections(thread, thread_id)
        self.active_threads[thread_id] = thread
        thread.start()
        
        self.thread_started.emit(thread_id)
        return thread_id
    
    def start_folder_upload(self, drive_client, folder_path: str, parent_id: str = 'root',
                           is_shared_drive: bool = False, max_workers: int = 3) -> str:
        """
        Start folder upload operation
        
        Returns:
            Thread ID for tracking
        """
        thread_id = self._generate_thread_id()
        thread = FolderUploadThread(
            drive_client, folder_path, parent_id, is_shared_drive, 
            self.transfer_manager, max_workers
        )
        
        self._setup_thread_connections(thread, thread_id)
        self.active_threads[thread_id] = thread
        thread.start()
        
        self.thread_started.emit(thread_id)
        return thread_id
    
    def start_file_download(self, drive_client, file_id: str, file_name: str,
                           local_dir: str, file_size: int = 0) -> str:
        """
        Start file download operation
        
        Returns:
            Thread ID for tracking
        """
        thread_id = self._generate_thread_id()
        thread = FileDownloadThread(
            drive_client, file_id, file_name, local_dir, file_size, self.transfer_manager
        )
        
        self._setup_thread_connections(thread, thread_id)
        self.active_threads[thread_id] = thread
        thread.start()
        
        self.thread_started.emit(thread_id)
        return thread_id
    
    def start_local_file_load(self, path: str) -> str:
        """
        Start local file loading operation
        
        Returns:
            Thread ID for tracking
        """
        thread_id = self._generate_thread_id()
        thread = LocalFileLoadThread(path)
        
        self._setup_thread_connections(thread, thread_id)
        self.active_threads[thread_id] = thread
        thread.start()
        
        self.thread_started.emit(thread_id)
        return thread_id
    
    def start_drive_file_load(self, drive_client, folder_id: str, path_history: List) -> str:
        """
        Start Google Drive file loading operation
        
        Returns:
            Thread ID for tracking
        """
        thread_id = self._generate_thread_id()
        thread = DriveFileLoadThread(drive_client, folder_id, path_history)
        
        self._setup_thread_connections(thread, thread_id)
        self.active_threads[thread_id] = thread
        thread.start()
        
        self.thread_started.emit(thread_id)
        return thread_id
    
    def cancel_thread(self, thread_id: str) -> bool:
        """
        Cancel a running thread
        
        Args:
            thread_id: ID of thread to cancel
            
        Returns:
            True if thread was cancelled, False if not found
        """
        if thread_id in self.active_threads:
            thread = self.active_threads[thread_id]
            thread.cancel()
            return True
        return False
    
    def pause_thread(self, thread_id: str) -> bool:
        """
        Pause a running thread
        
        Args:
            thread_id: ID of thread to pause
            
        Returns:
            True if thread was paused, False if not found
        """
        if thread_id in self.active_threads:
            thread = self.active_threads[thread_id]
            if hasattr(thread, 'pause'):
                thread.pause()
                return True
        return False
    
    def resume_thread(self, thread_id: str) -> bool:
        """
        Resume a paused thread
        
        Args:
            thread_id: ID of thread to resume
            
        Returns:
            True if thread was resumed, False if not found
        """
        if thread_id in self.active_threads:
            thread = self.active_threads[thread_id]
            if hasattr(thread, 'resume'):
                thread.resume()
                return True
        return False
    
    def get_thread_status(self, thread_id: str) -> Optional[Dict[str, Any]]:
        """
        Get status of a thread
        
        Args:
            thread_id: ID of thread
            
        Returns:
            Thread status information or None if not found
        """
        if thread_id in self.active_threads:
            thread = self.active_threads[thread_id]
            return {
                'id': thread_id,
                'running': thread.isRunning(),
                'cancelled': thread.is_operation_cancelled() if hasattr(thread, 'is_operation_cancelled') else False,
                'paused': thread.is_operation_paused() if hasattr(thread, 'is_operation_paused') else False
            }
        return None
    
    def get_active_threads(self) -> List[str]:
        """Get list of active thread IDs"""
        return [tid for tid, thread in self.active_threads.items() if thread.isRunning()]
    
    def cancel_all_threads(self) -> None:
        """Cancel all active threads"""
        for thread_id in list(self.active_threads.keys()):
            self.cancel_thread(thread_id)
    
    def cleanup_finished_threads(self) -> None:
        """Remove finished threads from active list"""
        finished_threads = []
        for thread_id, thread in self.active_threads.items():
            if not thread.isRunning():
                finished_threads.append(thread_id)
        
        for thread_id in finished_threads:
            del self.active_threads[thread_id]
    
    def _setup_thread_connections(self, thread: BaseOperationThread, thread_id: str) -> None:
        """Setup signal connections for a thread"""
        thread.completed_signal.connect(
            lambda result: self.thread_completed.emit(thread_id, result)
        )
        thread.error_signal.connect(
            lambda error: self.thread_error.emit(thread_id, error)
        )
        thread.progress_signal.connect(
            lambda progress: self.thread_progress.emit(thread_id, progress)
        )
        
        # Cleanup thread when finished
        thread.finished.connect(lambda: self._on_thread_finished(thread_id))
    
    def _on_thread_finished(self, thread_id: str) -> None:
        """Handle thread finishing"""
        # Thread will be cleaned up by the timer
        pass

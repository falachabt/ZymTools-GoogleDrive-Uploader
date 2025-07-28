"""
Unified Upload Queue System - New Architecture
Implements a single queue-based approach for all uploads
"""

import os
import queue
import threading
import random
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Set, Any
from dataclasses import dataclass, field
from PyQt5.QtCore import QObject, pyqtSignal, QTimer, QMutex, QMutexLocker


class FileStatus(Enum):
    """Status of files in upload queue"""
    PENDING = "⏳ En attente"
    IN_PROGRESS = "🔄 En cours"
    COMPLETED = "✅ Terminé"
    ERROR = "❌ Erreur"
    CANCELLED = "🚫 Annulé"
    SKIPPED = "⏭️ Ignoré (existe)"


class QueueOrdering(Enum):
    """Queue ordering strategies"""
    FIFO = "fifo"  # First In, First Out (default)
    RANDOM = "random"  # Random order
    SIZE_ASC = "size_asc"  # Small files first
    SIZE_DESC = "size_desc"  # Large files first  
    ALPHABETICAL = "alphabetical"  # Alphabetical by filename
    ROUND_ROBIN = "round_robin"  # Alternate between folders


@dataclass
class QueuedFile:
    """Represents a file in the upload queue"""
    
    # File information
    file_path: str
    file_name: str
    file_size: int
    
    # Folder/destination information
    source_folder: str  # Original folder this file came from
    relative_path: str  # Relative path within source folder
    destination_folder_id: str  # Google Drive folder ID where to upload
    
    # Upload state
    status: FileStatus = FileStatus.PENDING
    progress: int = 0
    speed: float = 0  # bytes/second
    bytes_transferred: int = 0
    
    # Timing information
    queued_time: datetime = field(default_factory=datetime.now)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    
    # Error handling
    error_message: str = ""
    retry_count: int = 0
    max_retries: int = 3
    
    # Upload result
    uploaded_file_id: str = ""
    worker_id: Optional[str] = None  # Which worker is processing this file
    
    def __post_init__(self):
        """Initialize computed fields"""
        if not self.file_name:
            self.file_name = os.path.basename(self.file_path)
        if self.file_size == 0 and os.path.exists(self.file_path):
            try:
                self.file_size = os.path.getsize(self.file_path)
            except:
                self.file_size = 0
    
    @property
    def unique_id(self) -> str:
        """Unique identifier for this file"""
        return f"{self.source_folder}::{self.relative_path}::{self.file_name}"
    
    @property
    def is_active(self) -> bool:
        """Returns True if file is currently being processed"""
        return self.status == FileStatus.IN_PROGRESS
    
    @property
    def is_completed(self) -> bool:
        """Returns True if file is done (success, error, cancelled, or skipped)"""
        return self.status in [FileStatus.COMPLETED, FileStatus.ERROR, 
                              FileStatus.CANCELLED, FileStatus.SKIPPED]
    
    @property
    def can_retry(self) -> bool:
        """Returns True if file can be retried"""
        return (self.status == FileStatus.ERROR and 
                self.retry_count < self.max_retries)
    
    def get_elapsed_time(self) -> float:
        """Returns elapsed time in seconds"""
        if not self.start_time:
            return 0.0
        end_time = self.end_time or datetime.now()
        return (end_time - self.start_time).total_seconds()
    
    def get_eta(self) -> Optional[float]:
        """Returns estimated time to completion in seconds"""
        if self.status != FileStatus.IN_PROGRESS or self.speed <= 0:
            return None
        
        remaining_bytes = self.file_size - self.bytes_transferred
        return remaining_bytes / self.speed
    
    def start_upload(self, worker_id: str):
        """Mark file as started by a worker"""
        self.status = FileStatus.IN_PROGRESS
        self.start_time = datetime.now()
        self.worker_id = worker_id
    
    def complete_upload(self, uploaded_file_id: str = ""):
        """Mark file as completed successfully"""
        self.status = FileStatus.COMPLETED
        self.end_time = datetime.now()
        self.progress = 100
        self.bytes_transferred = self.file_size
        self.uploaded_file_id = uploaded_file_id
        self.worker_id = None
    
    def fail_upload(self, error_message: str):
        """Mark file as failed"""
        self.status = FileStatus.ERROR
        self.end_time = datetime.now()
        self.error_message = error_message
        self.worker_id = None
    
    def skip_upload(self, reason: str = "File already exists"):
        """Mark file as skipped"""
        self.status = FileStatus.SKIPPED
        self.end_time = datetime.now()
        self.progress = 100
        self.error_message = reason
        self.worker_id = None
    
    def retry(self):
        """Prepare file for retry"""
        if self.can_retry:
            self.retry_count += 1
            self.status = FileStatus.PENDING
            self.progress = 0
            self.bytes_transferred = 0
            self.speed = 0
            self.start_time = None
            self.end_time = None
            self.worker_id = None
            # Keep error_message for reference


@dataclass 
class FolderInfo:
    """Information about a folder being uploaded"""
    
    folder_path: str  # Local folder path
    folder_name: str  # Display name
    destination_id: str  # Google Drive parent folder ID
    created_folder_id: str = ""  # ID of created folder on Drive
    
    # Statistics (computed from files in queue)
    total_files: int = 0
    completed_files: int = 0
    failed_files: int = 0
    skipped_files: int = 0
    in_progress_files: int = 0
    
    # Scanning state
    is_scanning: bool = False
    scan_completed: bool = False
    
    # Timing
    created_time: datetime = field(default_factory=datetime.now)
    
    @property
    def progress_percentage(self) -> int:
        """Calculate overall progress percentage"""
        if self.total_files == 0:
            return 0
        processed = self.completed_files + self.failed_files + self.skipped_files
        return int((processed / self.total_files) * 100)
    
    @property
    def is_completed(self) -> bool:
        """Returns True if all files are processed"""
        return (self.completed_files + self.failed_files + 
                self.skipped_files) >= self.total_files
    
    @property
    def has_errors(self) -> bool:
        """Returns True if any files failed"""
        return self.failed_files > 0
    
    @property 
    def status_text(self) -> str:
        """Get human-readable status for this folder"""
        if self.is_scanning:
            return "🔍 Scan en cours..."
        elif not self.scan_completed:
            return "⏳ En attente"
        elif self.is_completed:
            if self.has_errors:
                return "✅ Terminé (avec erreurs)"
            else:
                return "✅ Terminé"
        elif self.in_progress_files > 0:
            return "🔄 En cours"
        elif self.total_files > 0:
            return "⏳ En attente"
        else:
            return "📁 Vide"


class UploadQueue(QObject):
    """
    Unified upload queue that manages all files to be uploaded.
    This is the single source of truth for upload state.
    """
    
    # Signals for UI updates
    file_added = pyqtSignal(str)  # file unique_id
    file_updated = pyqtSignal(str)  # file unique_id  
    file_removed = pyqtSignal(str)  # file unique_id
    
    folder_added = pyqtSignal(str)  # folder_path
    folder_updated = pyqtSignal(str)  # folder_path
    
    queue_statistics_changed = pyqtSignal()  # Overall stats changed
    
    def __init__(self):
        super().__init__()
        
        # Core data structures
        self._files: Dict[str, QueuedFile] = {}  # unique_id -> QueuedFile
        self._folders: Dict[str, FolderInfo] = {}  # folder_path -> FolderInfo
        self._pending_queue = queue.Queue()  # Queue of unique_ids ready for processing
        
        # Thread safety
        self._lock = threading.RLock()
        
        # Statistics tracking
        self._total_size = 0
        self._transferred_size = 0
        
        # Update timer for aggregated statistics
        self._stats_timer = QTimer()
        self._stats_timer.timeout.connect(self._update_folder_statistics)
        self._stats_timer.start(1000)  # Update every second
    
    def add_file(self, queued_file: QueuedFile) -> bool:
        """
        Add a file to the upload queue
        
        Args:
            queued_file: File to add to queue
            
        Returns:
            True if added successfully, False if already exists
        """
        with self._lock:
            unique_id = queued_file.unique_id
            
            # Check if file already exists
            if unique_id in self._files:
                return False
            
            # Add to files dictionary
            self._files[unique_id] = queued_file
            
            # Add to pending queue for processing
            self._pending_queue.put(unique_id)
            
            # Update statistics
            self._total_size += queued_file.file_size
            
            # Update folder info if needed
            if queued_file.source_folder not in self._folders:
                folder_info = FolderInfo(
                    folder_path=queued_file.source_folder,
                    folder_name=os.path.basename(queued_file.source_folder),
                    destination_id=queued_file.destination_folder_id
                )
                self._folders[queued_file.source_folder] = folder_info
                self.folder_added.emit(queued_file.source_folder)
            
            # Emit signals
            self.file_added.emit(unique_id)
            self.queue_statistics_changed.emit()
            
            return True
    
    def add_files_batch(self, files: List[QueuedFile]) -> int:
        """
        Add multiple files efficiently
        
        Args:
            files: List of files to add
            
        Returns:
            Number of files actually added
        """
        added_count = 0
        with self._lock:
            for file in files:
                if self.add_file(file):
                    added_count += 1
        return added_count
    
    def register_folder_for_scanning(self, folder_path: str, destination_id: str) -> bool:
        """
        Pre-register a folder that will be scanned (for immediate UI feedback)
        
        Args:
            folder_path: Local folder path
            destination_id: Google Drive destination folder ID
            
        Returns:
            True if folder was registered (not already present)
        """
        with self._lock:
            if folder_path not in self._folders:
                folder_info = FolderInfo(
                    folder_path=folder_path,
                    folder_name=os.path.basename(folder_path),
                    destination_id=destination_id,
                    is_scanning=True,
                    scan_completed=False
                )
                self._folders[folder_path] = folder_info
                self.folder_added.emit(folder_path)
                self.queue_statistics_changed.emit()
                return True
            else:
                # Update existing folder to scanning status
                self._folders[folder_path].is_scanning = True
                self._folders[folder_path].scan_completed = False
                self.folder_updated.emit(folder_path)
                return False
    
    def mark_folder_scan_completed(self, folder_path: str) -> bool:
        """
        Mark a folder's scanning as completed
        
        Args:
            folder_path: Local folder path
            
        Returns:
            True if folder exists and was updated
        """
        with self._lock:
            if folder_path in self._folders:
                self._folders[folder_path].is_scanning = False
                self._folders[folder_path].scan_completed = True
                self.folder_updated.emit(folder_path)
                self.queue_statistics_changed.emit()
                return True
            return False
    
    def get_next_pending_file(self) -> Optional[QueuedFile]:
        """
        Get the next file ready for processing (thread-safe)
        
        Returns:
            Next file to process or None if queue is empty
        """
        try:
            # Get next file ID from queue (blocks if empty)
            unique_id = self._pending_queue.get_nowait()
            
            with self._lock:
                if unique_id in self._files:
                    file = self._files[unique_id]
                    # Double-check it's still pending
                    if file.status == FileStatus.PENDING:
                        return file
                    else:
                        # File status changed, try next
                        return self.get_next_pending_file()
                        
        except queue.Empty:
            return None
    
    def update_file_progress(self, unique_id: str, progress: int, 
                           bytes_transferred: int, speed: float):
        """Update file upload progress"""
        with self._lock:
            if unique_id in self._files:
                file = self._files[unique_id]
                file.progress = progress
                file.bytes_transferred = bytes_transferred
                file.speed = speed
                
                # Update folder statistics immediately for this file's folder if status changed
                if file.status == FileStatus.IN_PROGRESS:
                    self._update_single_folder_statistics(file.source_folder)
                
                self.file_updated.emit(unique_id)
    
    def complete_file(self, unique_id: str, uploaded_file_id: str = ""):
        """Mark file as completed successfully"""
        with self._lock:
            if unique_id in self._files:
                file = self._files[unique_id]
                file.complete_upload(uploaded_file_id)
                
                self._transferred_size += file.file_size
                
                # Update folder statistics immediately for this file's folder
                self._update_single_folder_statistics(file.source_folder)
                
                self.file_updated.emit(unique_id)
                self.queue_statistics_changed.emit()
    
    def fail_file(self, unique_id: str, error_message: str):
        """Mark file as failed"""
        with self._lock:
            if unique_id in self._files:
                file = self._files[unique_id]
                file.fail_upload(error_message)
                
                # Update folder statistics immediately for this file's folder
                self._update_single_folder_statistics(file.source_folder)
                
                self.file_updated.emit(unique_id)
                self.queue_statistics_changed.emit()
    
    def skip_file(self, unique_id: str, reason: str = "File already exists"):
        """Mark file as skipped"""
        with self._lock:
            if unique_id in self._files:
                file = self._files[unique_id]
                file.skip_upload(reason)
                
                # Count as transferred for progress calculation
                self._transferred_size += file.file_size
                
                # Update folder statistics immediately for this file's folder
                self._update_single_folder_statistics(file.source_folder)
                
                self.file_updated.emit(unique_id)
                self.queue_statistics_changed.emit()
    
    def retry_file(self, unique_id: str) -> bool:
        """
        Retry a failed file
        
        Args:
            unique_id: File to retry
            
        Returns:
            True if file was queued for retry
        """
        with self._lock:
            if unique_id in self._files:
                file = self._files[unique_id]
                if file.can_retry:
                    file.retry()
                    self._pending_queue.put(unique_id)
                    
                    self.file_updated.emit(unique_id)
                    return True
            return False
    
    def retry_all_failed(self) -> int:
        """
        Retry all failed files that can be retried
        
        Returns:
            Number of files queued for retry
        """
        retry_count = 0
        with self._lock:
            for unique_id, file in self._files.items():
                if file.can_retry:
                    file.retry()
                    self._pending_queue.put(unique_id)
                    retry_count += 1
                    self.file_updated.emit(unique_id)
        
        if retry_count > 0:
            self.queue_statistics_changed.emit()
        
        return retry_count
    
    def get_files_by_status(self, status: FileStatus) -> List[QueuedFile]:
        """Get all files with a specific status"""
        with self._lock:
            return [file for file in self._files.values() if file.status == status]
    
    def get_files_by_folder(self, folder_path: str) -> List[QueuedFile]:
        """Get all files from a specific source folder"""
        with self._lock:
            return [file for file in self._files.values() 
                   if file.source_folder == folder_path]
    
    def get_all_files(self) -> List[QueuedFile]:
        """Get all files in queue"""
        with self._lock:
            return list(self._files.values())
    
    def get_all_folders(self) -> List[FolderInfo]:
        """Get all folder information"""
        with self._lock:
            return list(self._folders.values())
    
    def get_folder_info(self, folder_path: str) -> Optional[FolderInfo]:
        """Get information about a specific folder"""
        with self._lock:
            return self._folders.get(folder_path)
    
    def get_queue_statistics(self) -> Dict[str, Any]:
        """Get overall queue statistics"""
        with self._lock:
            total_files = len(self._files)
            if total_files == 0:
                return {
                    'total_files': 0,
                    'pending': 0,
                    'in_progress': 0,
                    'completed': 0,
                    'failed': 0,
                    'skipped': 0,
                    'total_size': 0,
                    'transferred_size': 0,
                    'progress_percentage': 0,
                    'active_speed': 0
                }
            
            stats = {
                'pending': 0,
                'in_progress': 0,
                'completed': 0,
                'failed': 0,
                'skipped': 0,
                'active_speed': 0
            }
            
            for file in self._files.values():
                if file.status == FileStatus.PENDING:
                    stats['pending'] += 1
                elif file.status == FileStatus.IN_PROGRESS:
                    stats['in_progress'] += 1
                    stats['active_speed'] += file.speed
                elif file.status == FileStatus.COMPLETED:
                    stats['completed'] += 1
                elif file.status == FileStatus.ERROR:
                    stats['failed'] += 1
                elif file.status == FileStatus.SKIPPED:
                    stats['skipped'] += 1
            
            stats.update({
                'total_files': total_files,
                'total_size': self._total_size,
                'transferred_size': self._transferred_size,
                'progress_percentage': int((self._transferred_size / self._total_size) * 100) 
                                     if self._total_size > 0 else 0
            })
            
            return stats
    
    def _update_folder_statistics(self):
        """Update folder statistics based on their files"""
        with self._lock:
            for folder_path, folder_info in self._folders.items():
                # Get all files for this folder
                folder_files = self.get_files_by_folder(folder_path)
                
                # Calculate statistics
                folder_info.total_files = len(folder_files)
                folder_info.completed_files = sum(1 for f in folder_files 
                                                 if f.status == FileStatus.COMPLETED)
                folder_info.failed_files = sum(1 for f in folder_files 
                                             if f.status == FileStatus.ERROR)
                folder_info.skipped_files = sum(1 for f in folder_files 
                                              if f.status == FileStatus.SKIPPED)
                folder_info.in_progress_files = sum(1 for f in folder_files 
                                                   if f.status == FileStatus.IN_PROGRESS)
                
                # Emit update signal
                self.folder_updated.emit(folder_path)
    
    def _update_single_folder_statistics(self, folder_path: str):
        """Update statistics for a single folder immediately"""
        if folder_path in self._folders:
            folder_info = self._folders[folder_path]
            
            # Get all files for this folder
            folder_files = self.get_files_by_folder(folder_path)
            
            # Calculate statistics
            folder_info.total_files = len(folder_files)
            folder_info.completed_files = sum(1 for f in folder_files 
                                             if f.status == FileStatus.COMPLETED)
            folder_info.failed_files = sum(1 for f in folder_files 
                                         if f.status == FileStatus.ERROR)
            folder_info.skipped_files = sum(1 for f in folder_files 
                                          if f.status == FileStatus.SKIPPED)
            folder_info.in_progress_files = sum(1 for f in folder_files 
                                               if f.status == FileStatus.IN_PROGRESS)
            
            # Emit update signal immediately
            self.folder_updated.emit(folder_path)
    
    def clear_completed(self):
        """Remove all completed/failed/skipped files from queue"""
        with self._lock:
            to_remove = []
            for unique_id, file in self._files.items():
                if file.is_completed:
                    to_remove.append(unique_id)
            
            for unique_id in to_remove:
                del self._files[unique_id]
                self.file_removed.emit(unique_id)
            
            # Recalculate statistics
            self._total_size = sum(f.file_size for f in self._files.values())
            self._transferred_size = sum(f.bytes_transferred for f in self._files.values())
            
            self.queue_statistics_changed.emit()
    
    def is_empty(self) -> bool:
        """Check if queue is empty"""
        with self._lock:
            return len(self._files) == 0
    
    def has_pending_files(self) -> bool:
        """Check if there are files waiting to be processed"""
        return not self._pending_queue.empty()
    
    def get_pending_count(self) -> int:
        """Get number of pending files"""
        with self._lock:
            return sum(1 for f in self._files.values() if f.status == FileStatus.PENDING)
    
    def reorder_queue(self, ordering: QueueOrdering = QueueOrdering.RANDOM) -> int:
        """
        Reorder the pending files in the queue according to the specified strategy.
        This enables concurrent folder uploads by interleaving files from different folders.
        
        Args:
            ordering: The ordering strategy to apply
            
        Returns:
            Number of pending files that were reordered
        """
        with self._lock:
            # Get all pending files
            pending_files = [f for f in self._files.values() if f.status == FileStatus.PENDING]
            
            if len(pending_files) == 0:
                return 0
            
            # Clear current pending queue
            while not self._pending_queue.empty():
                try:
                    self._pending_queue.get_nowait()
                except queue.Empty:
                    break
            
            # Apply ordering strategy
            if ordering == QueueOrdering.RANDOM:
                random.shuffle(pending_files)
            elif ordering == QueueOrdering.SIZE_ASC:
                pending_files.sort(key=lambda f: f.file_size)
            elif ordering == QueueOrdering.SIZE_DESC:
                pending_files.sort(key=lambda f: f.file_size, reverse=True)
            elif ordering == QueueOrdering.ALPHABETICAL:
                pending_files.sort(key=lambda f: f.file_name.lower())
            elif ordering == QueueOrdering.ROUND_ROBIN:
                pending_files = self._round_robin_sort(pending_files)
            # FIFO is default - no reordering needed
            
            # Add reordered files back to queue
            for file in pending_files:
                self._pending_queue.put(file.unique_id)
            
            return len(pending_files)
    
    def _round_robin_sort(self, files: List[QueuedFile]) -> List[QueuedFile]:
        """
        Sort files using round-robin strategy to interleave files from different folders
        
        Args:
            files: List of files to sort
            
        Returns:
            List of files sorted in round-robin fashion by source folder
        """
        # Group files by source folder
        folder_groups = {}
        for file in files:
            folder = file.source_folder
            if folder not in folder_groups:
                folder_groups[folder] = []
            folder_groups[folder].append(file)
        
        # Round-robin through folders
        result = []
        folder_iterators = {folder: iter(files) for folder, files in folder_groups.items()}
        folders = list(folder_iterators.keys())
        
        while folder_iterators:
            for folder in folders[:]:  # Copy list to avoid modification during iteration
                try:
                    file = next(folder_iterators[folder])
                    result.append(file)
                except StopIteration:
                    # This folder is exhausted, remove it
                    del folder_iterators[folder]
                    folders.remove(folder)
        
        return result
    
    def auto_reorder_on_folder_complete(self, ordering: QueueOrdering = QueueOrdering.ROUND_ROBIN):
        """
        Automatically reorder queue when a new folder's files are added.
        This ensures concurrent folder uploads.
        
        Args:
            ordering: The ordering strategy to apply
        """
        pending_count = self.reorder_queue(ordering)
        if pending_count > 0:
            print(f"🔄 Queue reordered: {pending_count} pending files using {ordering.value} strategy")
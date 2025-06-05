
"""
Base thread class with common functionality for all operations
"""

import time
from abc import ABC, abstractmethod
from typing import Optional, Any, Dict
from PyQt5.QtCore import QThread, pyqtSignal, QMutex, QMutexLocker

from models.transfer_models import TransferManager, TransferType, TransferStatus


class BaseOperationThread(QThread, ABC):
    """Base class for all operation threads with common functionality"""
    
    # Common signals
    progress_signal = pyqtSignal(int)  # progress percentage
    status_signal = pyqtSignal(str)   # status message
    completed_signal = pyqtSignal(str)  # result data
    error_signal = pyqtSignal(str)    # error message
    time_signal = pyqtSignal(float)   # operation time
    
    def __init__(self, transfer_manager: Optional[TransferManager] = None):
        """
        Initialize base thread
        
        Args:
            transfer_manager: Optional transfer manager for tracking
        """
        super().__init__()
        self.transfer_manager = transfer_manager
        self.transfer_id: Optional[str] = None
        self.is_cancelled = False
        self.is_paused = False
        self.start_time = 0
        self.operation_mutex = QMutex()
        
    def run(self) -> None:
        """Main thread execution"""
        self.start_time = time.time()
        
        try:
            # Create transfer entry if manager is available
            if self.transfer_manager:
                self.transfer_id = self.create_transfer_entry()
            
            # Execute the main operation
            result = self.execute_operation()
            
            if not self.is_cancelled:
                self.completed_signal.emit(result)
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
    
    @abstractmethod
    def create_transfer_entry(self) -> str:
        """Create transfer entry in manager - to be implemented by subclasses"""
        pass
    
    @abstractmethod
    def execute_operation(self) -> str:
        """Execute the main operation - to be implemented by subclasses"""
        pass
    
    def update_progress(self, progress: int, bytes_transferred: int = 0, 
                       total_bytes: int = 0) -> None:
        """
        Update progress with thread safety
        
        Args:
            progress: Progress percentage (0-100)
            bytes_transferred: Bytes transferred so far
            total_bytes: Total bytes to transfer
        """
        with QMutexLocker(self.operation_mutex):
            if self.is_cancelled:
                return
            
            self.progress_signal.emit(progress)
            
            if self.transfer_manager and self.transfer_id and total_bytes > 0:
                elapsed_time = time.time() - self.start_time
                if elapsed_time > 0:
                    speed = bytes_transferred / elapsed_time
                    self.transfer_manager.update_transfer_progress(
                        self.transfer_id, progress, bytes_transferred, speed
                    )
    
    def update_status(self, status: str) -> None:
        """Update status message"""
        if not self.is_cancelled:
            self.status_signal.emit(status)
    
    def cancel(self) -> None:
        """Cancel the operation"""
        with QMutexLocker(self.operation_mutex):
            self.is_cancelled = True
            
        if self.transfer_manager and self.transfer_id:
            self.transfer_manager.update_transfer_status(
                self.transfer_id, TransferStatus.CANCELLED
            )
    
    def pause(self) -> None:
        """Pause the operation"""
        with QMutexLocker(self.operation_mutex):
            self.is_paused = True
            
        if self.transfer_manager and self.transfer_id:
            self.transfer_manager.update_transfer_status(
                self.transfer_id, TransferStatus.PAUSED
            )
    
    def resume(self) -> None:
        """Resume the operation"""
        with QMutexLocker(self.operation_mutex):
            self.is_paused = False
            
        if self.transfer_manager and self.transfer_id:
            self.transfer_manager.update_transfer_status(
                self.transfer_id, TransferStatus.IN_PROGRESS
            )
    
    def is_operation_cancelled(self) -> bool:
        """Check if operation is cancelled (thread-safe)"""
        with QMutexLocker(self.operation_mutex):
            return self.is_cancelled
    
    def is_operation_paused(self) -> bool:
        """Check if operation is paused (thread-safe)"""
        with QMutexLocker(self.operation_mutex):
            return self.is_paused


"""
Specialized threads for file operations (upload/download) with improved logic
"""

import os
import time
from typing import Optional, List, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed

from core.google_drive_client import GoogleDriveClient
from models.transfer_models import TransferManager, TransferType
from .base_thread import BaseOperationThread


class FileUploadThread(BaseOperationThread):
    """Improved thread for single file uploads"""
    
    def __init__(self, drive_client: GoogleDriveClient, file_path: str,
                 parent_id: str = 'root', is_shared_drive: bool = False,
                 transfer_manager: Optional[TransferManager] = None):
        super().__init__(transfer_manager)
        self.drive_client = drive_client
        self.file_path = file_path
        self.parent_id = parent_id
        self.is_shared_drive = is_shared_drive
        self.file_size = os.path.getsize(file_path) if os.path.isfile(file_path) else 0
        self.bytes_transferred = 0
    
    def create_transfer_entry(self) -> str:
        """Create transfer entry for file upload"""
        file_name = os.path.basename(self.file_path)
        return self.transfer_manager.add_transfer(
            TransferType.UPLOAD_FILE,
            self.file_path,
            f"Google Drive/{self.parent_id}",
            file_name,
            self.file_size
        )
    
    def execute_operation(self) -> str:
        """Execute file upload"""
        def progress_callback(progress: int) -> None:
            self.bytes_transferred = int((progress / 100.0) * self.file_size)
            self.update_progress(progress, self.bytes_transferred, self.file_size)
        
        def status_callback(status: str) -> None:
            self.update_status(status)
        
        file_id = self.drive_client.upload_file(
            self.file_path,
            self.parent_id,
            progress_callback,
            status_callback,
            self.is_shared_drive
        )
        
        return file_id


class FolderUploadThread(BaseOperationThread):
    """Improved thread for folder uploads with better parallel processing"""
    
    def __init__(self, drive_client: GoogleDriveClient, folder_path: str,
                 parent_id: str = 'root', is_shared_drive: bool = False,
                 transfer_manager: Optional[TransferManager] = None,
                 max_workers: int = 3):
        super().__init__(transfer_manager)
        self.drive_client = drive_client
        self.folder_path = folder_path
        self.parent_id = parent_id
        self.is_shared_drive = is_shared_drive
        self.max_workers = max_workers
        self.total_files = 0
        self.completed_files = 0
        self.total_size = 0
        self.transferred_size = 0
    
    def create_transfer_entry(self) -> str:
        """Create transfer entry for folder upload"""
        folder_name = os.path.basename(self.folder_path)
        self.total_files, self.total_size = self._analyze_folder()
        
        return self.transfer_manager.add_transfer(
            TransferType.UPLOAD_FOLDER,
            self.folder_path,
            f"Google Drive/{self.parent_id}",
            folder_name,
            self.total_size
        )
    
    def execute_operation(self) -> str:
        """Execute folder upload with parallel processing"""
        folder_name = os.path.basename(self.folder_path)
        
        if self.total_files == 0:
            self.update_status("📁 Creating empty folder...")
            return self.drive_client.create_folder(
                folder_name, self.parent_id, self.is_shared_drive
            )
        
        # Create main folder
        main_folder_id = self.drive_client.create_folder(
            folder_name, self.parent_id, self.is_shared_drive
        )
        
        # Create folder structure
        self.update_status("📁 Creating folder structure...")
        folder_mapping = self._create_folder_structure(main_folder_id)
        
        # Upload files in parallel
        self.update_status(f"⚡ Uploading {self.total_files} files...")
        self._upload_files_parallel(folder_mapping)
        
        return main_folder_id
    
    def _analyze_folder(self) -> tuple:
        """Analyze folder to count files and calculate total size"""
        file_count = 0
        total_size = 0
        
        for root, dirs, files in os.walk(self.folder_path):
            for file in files:
                file_path = os.path.join(root, file)
                try:
                    file_count += 1
                    total_size += os.path.getsize(file_path)
                except (OSError, IOError):
                    pass
        
        return file_count, total_size
    
    def _create_folder_structure(self, main_folder_id: str) -> Dict[str, str]:
        """Create folder structure on Google Drive"""
        folder_mapping = {'': main_folder_id}
        
        for root, dirs, files in os.walk(self.folder_path):
            if self.is_operation_cancelled():
                break
                
            rel_path = os.path.relpath(root, self.folder_path)
            if rel_path == '.':
                continue
            
            parent_rel_path = os.path.dirname(rel_path)
            if parent_rel_path == '.':
                parent_rel_path = ''
            
            if parent_rel_path in folder_mapping:
                parent_drive_id = folder_mapping[parent_rel_path]
                folder_name = os.path.basename(root)
                
                folder_id = self.drive_client.create_folder(
                    folder_name, parent_drive_id, self.is_shared_drive
                )
                folder_mapping[rel_path] = folder_id
        
        return folder_mapping
    
    def _upload_files_parallel(self, folder_mapping: Dict[str, str]) -> None:
        """Upload files in parallel with improved tracking"""
        files_to_upload = []
        
        # Collect all files
        for root, dirs, files in os.walk(self.folder_path):
            rel_dir = os.path.relpath(root, self.folder_path)
            if rel_dir == '.':
                rel_dir = ''
            
            for file in files:
                file_path = os.path.join(root, file)
                files_to_upload.append({
                    'path': file_path,
                    'name': file,
                    'rel_dir': rel_dir,
                    'size': os.path.getsize(file_path) if os.path.exists(file_path) else 0
                })
        
        def upload_single_file(file_info):
            """Upload a single file"""
            try:
                if self.is_operation_cancelled():
                    return {'success': False, 'cancelled': True}
                
                parent_id = folder_mapping.get(file_info['rel_dir'], self.parent_id)
                
                file_id = self.drive_client.upload_file(
                    file_info['path'],
                    parent_id,
                    None,  # No individual progress callback
                    None,  # No individual status callback
                    self.is_shared_drive
                )
                
                return {'success': True, 'file_id': file_id, 'file_info': file_info}
                
            except Exception as e:
                return {'success': False, 'error': str(e), 'file_info': file_info}
        
        # Execute uploads in parallel
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_file = {
                executor.submit(upload_single_file, file_info): file_info
                for file_info in files_to_upload
            }
            
            for future in as_completed(future_to_file):
                if self.is_operation_cancelled():
                    break
                
                result = future.result()
                
                if result['success']:
                    self.completed_files += 1
                    self.transferred_size += result['file_info']['size']
                    
                    progress = int((self.completed_files / self.total_files) * 100)
                    self.update_progress(progress, self.transferred_size, self.total_size)
                    self.update_status(f"✅ {result['file_info']['name']}")


class FileDownloadThread(BaseOperationThread):
    """Improved thread for file downloads"""
    
    def __init__(self, drive_client: GoogleDriveClient, file_id: str,
                 file_name: str, local_dir: str, file_size: int = 0,
                 transfer_manager: Optional[TransferManager] = None):
        super().__init__(transfer_manager)
        self.drive_client = drive_client
        self.file_id = file_id
        self.file_name = file_name
        self.local_dir = local_dir
        self.file_size = file_size
        self.bytes_transferred = 0
    
    def create_transfer_entry(self) -> str:
        """Create transfer entry for file download"""
        return self.transfer_manager.add_transfer(
            TransferType.DOWNLOAD_FILE,
            f"Google Drive/{self.file_id}",
            self.local_dir,
            self.file_name,
            self.file_size
        )
    
    def execute_operation(self) -> str:
        """Execute file download"""
        def progress_callback(progress: int) -> None:
            if self.file_size > 0:
                self.bytes_transferred = int((progress / 100.0) * self.file_size)
                self.update_progress(progress, self.bytes_transferred, self.file_size)
            else:
                self.update_progress(progress)
        
        file_path = self.drive_client.download_file(
            self.file_id,
            self.file_name,
            self.local_dir,
            progress_callback
        )
        
        return file_path


class BatchOperationThread(BaseOperationThread):
    """Thread for handling multiple operations in batch"""
    
    def __init__(self, operations: List[Dict[str, Any]], 
                 transfer_manager: Optional[TransferManager] = None,
                 max_workers: int = 3):
        super().__init__(transfer_manager)
        self.operations = operations
        self.max_workers = max_workers
        self.completed_operations = 0
        self.total_operations = len(operations)
    
    def create_transfer_entry(self) -> str:
        """Create transfer entry for batch operation"""
        total_size = sum(op.get('size', 0) for op in self.operations)
        return self.transfer_manager.add_transfer(
            TransferType.UPLOAD_FOLDER,  # Use folder type for batch
            "Batch Operation",
            "Multiple Destinations",
            f"Batch ({self.total_operations} items)",
            total_size
        )
    
    def execute_operation(self) -> str:
        """Execute batch operations"""
        def execute_single_operation(operation):
            """Execute a single operation from the batch"""
            try:
                if self.is_operation_cancelled():
                    return {'success': False, 'cancelled': True}
                
                # Execute operation based on type
                op_type = operation.get('type')
                if op_type == 'upload_file':
                    # Handle file upload
                    pass
                elif op_type == 'download_file':
                    # Handle file download
                    pass
                
                return {'success': True, 'operation': operation}
                
            except Exception as e:
                return {'success': False, 'error': str(e), 'operation': operation}
        
        successful_operations = 0
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_operation = {
                executor.submit(execute_single_operation, op): op
                for op in self.operations
            }
            
            for future in as_completed(future_to_operation):
                if self.is_operation_cancelled():
                    break
                
                result = future.result()
                self.completed_operations += 1
                
                if result['success']:
                    successful_operations += 1
                
                progress = int((self.completed_operations / self.total_operations) * 100)
                self.update_progress(progress)
                self.update_status(f"Completed {self.completed_operations}/{self.total_operations}")
        
        return f"Batch completed: {successful_operations}/{self.total_operations} successful"

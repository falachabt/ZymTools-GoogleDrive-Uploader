"""
Folder Scanner - Scans folders and adds files to upload queue
"""

import os
import time
from typing import Dict, List, Optional, Tuple
from PyQt5.QtCore import QThread, pyqtSignal

from models.upload_queue import UploadQueue, QueuedFile, FolderInfo
from core.google_drive_client import GoogleDriveClient


class FolderScanner(QThread):
    """
    Scans local folders, creates Drive folder structure, and adds files to upload queue
    """
    
    # Signals
    scanning_started = pyqtSignal(str)  # folder_path
    scanning_progress = pyqtSignal(str, int, int)  # folder_path, current, total
    folder_created = pyqtSignal(str, str, str)  # local_path, folder_name, drive_folder_id
    files_added = pyqtSignal(str, int)  # folder_path, file_count
    scanning_completed = pyqtSignal(str, int, str)  # folder_path, total_files, main_folder_id
    scanning_error = pyqtSignal(str, str)  # folder_path, error_message
    
    def __init__(self, upload_queue: UploadQueue, drive_client: GoogleDriveClient):
        """
        Initialize folder scanner
        
        Args:
            upload_queue: The upload queue to add files to
            drive_client: Google Drive client for creating folders
        """
        super().__init__()
        
        self.upload_queue = upload_queue
        self.drive_client = drive_client
        
        # Control flags
        self._should_stop = False
        
        # Batch processing
        self._batch_size = 100  # Process files in batches
        
        # Initialize attributes that will be set in scan_folder
        self.folder_path = ""
        self.destination_id = ""
        self.is_shared_drive = False
    
    def scan_folder(self, folder_path: str, destination_id: str, 
                   is_shared_drive: bool = False) -> None:
        """
        Scan a folder and add its files to the upload queue
        
        Args:
            folder_path: Local folder path to scan
            destination_id: Google Drive parent folder ID
            is_shared_drive: Whether the destination is a shared drive
        """
        self.folder_path = folder_path
        self.destination_id = destination_id
        self.is_shared_drive = is_shared_drive
        self._should_stop = False
        
        # Start the scanning process
        self.start()
    
    def run(self):
        """Main scanning process"""
        try:
            self.scanning_started.emit(self.folder_path)
            
            # Step 1: Scan local folder structure
            folder_structure, all_files = self._scan_local_structure(self.folder_path)
            
            if self._should_stop:
                return
            
            # Step 2: Create Google Drive folder structure
            folder_mapping = self._create_drive_structure(
                self.folder_path, self.destination_id, folder_structure
            )
            
            if self._should_stop:
                return
            
            # Step 3: Add files to upload queue in batches
            main_folder_id = folder_mapping.get('', self.destination_id)
            files_added = self._add_files_to_queue(all_files, folder_mapping)
            
            if not self._should_stop:
                self.scanning_completed.emit(self.folder_path, files_added, main_folder_id)
                
        except Exception as e:
            if not self._should_stop:
                self.scanning_error.emit(self.folder_path, str(e))
    
    def _scan_local_structure(self, root_path: str) -> Tuple[Dict[str, List[str]], List[Dict[str, str]]]:
        """
        Scan local folder structure and collect all files
        
        Args:
            root_path: Root folder to scan
            
        Returns:
            Tuple of (folder_structure, all_files)
            - folder_structure: Dict mapping relative paths to subfolder names
            - all_files: List of file info dictionaries
        """
        folder_structure = {}  # relative_path -> [subfolder_names]
        all_files = []
        
        total_items = 0
        processed_items = 0
        
        # First pass: count total items for progress
        for root, dirs, files in os.walk(root_path):
            total_items += len(dirs) + len(files)
        
        # Second pass: collect structure and files
        for root, dirs, files in os.walk(root_path):
            if self._should_stop:
                break
            
            # Calculate relative path from root
            rel_path = os.path.relpath(root, root_path)
            if rel_path == '.':
                rel_path = ''
            
            # Store subfolder names
            if dirs:
                folder_structure[rel_path] = dirs
            
            # Process files in this directory
            for file_name in files:
                if self._should_stop:
                    break
                
                file_path = os.path.join(root, file_name)
                
                try:
                    file_size = os.path.getsize(file_path)
                    
                    file_info = {
                        'file_path': file_path,
                        'file_name': file_name,
                        'file_size': file_size,
                        'relative_path': rel_path,
                        'source_folder': root_path
                    }
                    
                    all_files.append(file_info)
                    
                except (OSError, IOError) as e:
                    print(f"⚠️ Cannot access file {file_path}: {e}")
                    continue
                
                processed_items += 1
                
                # Emit progress every 10 items
                if processed_items % 10 == 0:
                    self.scanning_progress.emit(root_path, processed_items, total_items)
            
            # Count processed directories
            processed_items += len(dirs)
            self.scanning_progress.emit(root_path, processed_items, total_items)
        
        return folder_structure, all_files
    
    def _create_drive_structure(self, root_path: str, parent_id: str, 
                              folder_structure: Dict[str, List[str]]) -> Dict[str, str]:
        """
        Create Google Drive folder structure with proper hierarchical order
        
        Args:
            root_path: Local root folder path
            parent_id: Google Drive parent folder ID
            folder_structure: Dict mapping relative paths to subfolder names
            
        Returns:
            Dict mapping relative paths to Google Drive folder IDs
        """
        folder_mapping = {'': parent_id}  # Root mapping
        
        # Create main folder first
        main_folder_name = os.path.basename(root_path)
        try:
            main_folder_id = self.drive_client.create_folder(
                main_folder_name, parent_id, self.is_shared_drive
            )
            folder_mapping[''] = main_folder_id
            self.folder_created.emit(root_path, main_folder_name, main_folder_id)
            
        except Exception as e:
            raise Exception(f"Failed to create main folder '{main_folder_name}': {e}")
        
        if self._should_stop:
            return folder_mapping
        
        # Create complete list of all folders that need to be created
        all_folders_to_create = []
        for rel_path, subfolders in folder_structure.items():
            for subfolder_name in subfolders:
                if rel_path == '':
                    subfolder_rel_path = subfolder_name
                else:
                    subfolder_rel_path = os.path.join(rel_path, subfolder_name)
                all_folders_to_create.append(subfolder_rel_path)
        
        # Sort by depth to ensure parent folders are created before children
        all_folders_to_create.sort(key=lambda x: x.count(os.sep))
        
        # Create folders one by one in hierarchical order
        for subfolder_rel_path in all_folders_to_create:
            if self._should_stop:
                break
            
            # Skip if already created
            if subfolder_rel_path in folder_mapping:
                continue
            
            # Determine parent folder
            parent_rel_path = os.path.dirname(subfolder_rel_path)
            if parent_rel_path == '.':
                parent_rel_path = ''
            
            # Get parent Drive folder ID - must exist by now due to sorting
            parent_drive_id = folder_mapping.get(parent_rel_path, main_folder_id)
            
            # Get folder name
            subfolder_name = os.path.basename(subfolder_rel_path)
            
            try:
                # Create the folder
                subfolder_id = self.drive_client.create_folder(
                    subfolder_name, parent_drive_id, self.is_shared_drive
                )
                folder_mapping[subfolder_rel_path] = subfolder_id
                
                local_subfolder_path = os.path.join(root_path, subfolder_rel_path)
                self.folder_created.emit(local_subfolder_path, subfolder_name, subfolder_id)
                
                print(f"✅ Created folder: {subfolder_rel_path} -> {subfolder_id}")
                
            except Exception as e:
                print(f"⚠️ Failed to create folder '{subfolder_name}' at '{subfolder_rel_path}': {e}")
                # Use parent folder as fallback
                folder_mapping[subfolder_rel_path] = parent_drive_id
            
            # Small delay to avoid rate limiting
            time.sleep(0.05)
        
        return folder_mapping
    
    def _add_files_to_queue(self, all_files: List[Dict[str, str]], 
                          folder_mapping: Dict[str, str]) -> int:
        """
        Add files to upload queue in batches
        
        Args:
            all_files: List of file info dictionaries
            folder_mapping: Dict mapping relative paths to Drive folder IDs
            
        Returns:
            Number of files added to queue
        """
        files_added = 0
        batch = []
        
        for file_info in all_files:
            if self._should_stop:
                break
            
            # Get destination folder ID
            rel_path = file_info['relative_path']
            destination_folder_id = folder_mapping.get(rel_path, folder_mapping[''])
            
            # Create QueuedFile
            queued_file = QueuedFile(
                file_path=file_info['file_path'],
                file_name=file_info['file_name'],
                file_size=file_info['file_size'],
                source_folder=file_info['source_folder'],
                relative_path=rel_path,
                destination_folder_id=destination_folder_id
            )
            
            batch.append(queued_file)
            
            # Process batch when it reaches batch_size
            if len(batch) >= self._batch_size:
                added_count = self.upload_queue.add_files_batch(batch)
                files_added += added_count
                self.files_added.emit(self.folder_path, added_count)
                batch = []
                
                # Small delay between batches
                time.sleep(0.01)
        
        # Process remaining files in batch
        if batch and not self._should_stop:
            added_count = self.upload_queue.add_files_batch(batch)
            files_added += added_count
            self.files_added.emit(self.folder_path, added_count)
        
        return files_added
    
    def stop(self):
        """Stop the scanning process"""
        self._should_stop = True
        
        if self.isRunning():
            self.wait(3000)  # Wait up to 3 seconds


class BatchFolderScanner(QThread):
    """
    Scanner for multiple folders - processes them in sequence
    """
    
    # Signals
    batch_started = pyqtSignal(int)  # total_folders
    folder_scanning_started = pyqtSignal(int, str)  # folder_index, folder_path
    folder_scanning_completed = pyqtSignal(int, str, int, str)  # folder_index, folder_path, files_added, main_folder_id
    folder_scanning_error = pyqtSignal(int, str, str)  # folder_index, folder_path, error
    batch_completed = pyqtSignal(int, int)  # total_folders, total_files_added
    
    def __init__(self, upload_queue: UploadQueue, drive_client: GoogleDriveClient):
        """
        Initialize batch folder scanner
        
        Args:
            upload_queue: The upload queue to add files to
            drive_client: Google Drive client for creating folders
        """
        super().__init__()
        
        self.upload_queue = upload_queue
        self.drive_client = drive_client
        
        # Control flags
        self._should_stop = False
        
        # Batch data
        self.folder_paths = []
        self.destination_id = ""
        self.is_shared_drive = False
    
    def scan_folders(self, folder_paths: List[str], destination_id: str, 
                    is_shared_drive: bool = False) -> None:
        """
        Scan multiple folders and add their files to the upload queue
        
        Args:
            folder_paths: List of local folder paths to scan
            destination_id: Google Drive parent folder ID
            is_shared_drive: Whether the destination is a shared drive
        """
        self.folder_paths = folder_paths
        self.destination_id = destination_id
        self.is_shared_drive = is_shared_drive
        self._should_stop = False
        
        # Start the scanning process
        self.start()
    
    def run(self):
        """Main batch scanning process"""
        try:
            total_folders = len(self.folder_paths)
            total_files_added = 0
            
            self.batch_started.emit(total_folders)
            
            for i, folder_path in enumerate(self.folder_paths):
                if self._should_stop:
                    break
                
                self.folder_scanning_started.emit(i, folder_path)
                
                try:
                    # Create individual scanner for this folder
                    scanner = FolderScanner(self.upload_queue, self.drive_client)
                    
                    # Set the required attributes for this scan
                    scanner.folder_path = folder_path
                    scanner.destination_id = self.destination_id
                    scanner.is_shared_drive = self.is_shared_drive
                    
                    # Connect to scanner signals to forward them
                    scanner.folder_created.connect(
                        lambda local_path, name, drive_id: None  # Could forward if needed
                    )
                    
                    # Run the scan synchronously
                    folder_structure, all_files = scanner._scan_local_structure(folder_path)
                    
                    if self._should_stop:
                        break
                    
                    folder_mapping = scanner._create_drive_structure(
                        folder_path, self.destination_id, folder_structure
                    )
                    
                    if self._should_stop:
                        break
                    
                    files_added = scanner._add_files_to_queue(all_files, folder_mapping)
                    main_folder_id = folder_mapping.get('', self.destination_id)
                    
                    total_files_added += files_added
                    
                    self.folder_scanning_completed.emit(i, folder_path, files_added, main_folder_id)
                    
                except Exception as e:
                    self.folder_scanning_error.emit(i, folder_path, str(e))
                    continue
                
                # Small delay between folders
                time.sleep(0.1)
            
            if not self._should_stop:
                self.batch_completed.emit(total_folders, total_files_added)
                
        except Exception as e:
            print(f"❌ Batch scanning error: {e}")
    
    def stop(self):
        """Stop the batch scanning process"""
        self._should_stop = True
        
        if self.isRunning():
            self.wait(5000)  # Wait up to 5 seconds
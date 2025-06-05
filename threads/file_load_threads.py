
"""
Improved threads for loading files with better performance and error handling
"""

import os
import time
from typing import List, Dict, Any, Tuple, Optional
from PyQt5.QtCore import QThread, pyqtSignal, QMutex, QMutexLocker

from core.google_drive_client import GoogleDriveClient
from .base_thread import BaseOperationThread


class LocalFileLoadThread(BaseOperationThread):
    """Improved thread for loading local files with caching and better performance"""
    
    files_loaded = pyqtSignal(str, list)  # path, file_list
    
    def __init__(self, path: str, use_cache: bool = True):
        super().__init__()
        self.path = path
        self.use_cache = use_cache
        self._cache = {}
        self._cache_mutex = QMutex()
    
    def create_transfer_entry(self) -> str:
        """Not needed for file loading operations"""
        return ""
    
    def execute_operation(self) -> str:
        """Load local files with improved performance"""
        # Check cache first
        if self.use_cache:
            with QMutexLocker(self._cache_mutex):
                if self.path in self._cache:
                    cache_entry = self._cache[self.path]
                    # Check if cache is still valid (less than 30 seconds old)
                    if time.time() - cache_entry['timestamp'] < 30:
                        self.files_loaded.emit(self.path, cache_entry['data'])
                        return "Loaded from cache"
        
        try:
            file_list = []
            
            # Add parent directory entry
            if self.path != os.path.dirname(self.path):
                file_list.append({
                    'name': '..',
                    'type': 'parent',
                    'size': '',
                    'modified': '',
                    'is_dir': True
                })
            
            # Get directory entries
            items = []
            try:
                entries = os.listdir(self.path)
                total_entries = len(entries)
                
                for i, item in enumerate(entries):
                    if self.is_operation_cancelled():
                        break
                    
                    item_path = os.path.join(self.path, item)
                    
                    try:
                        stats = os.stat(item_path)
                        is_dir = os.path.isdir(item_path)
                        
                        file_info = {
                            'name': item,
                            'type': 'folder' if is_dir else 'file',
                            'size': '' if is_dir else stats.st_size,
                            'modified': stats.st_mtime,
                            'is_dir': is_dir,
                            'path': item_path
                        }
                        items.append(file_info)
                        
                        # Update progress
                        progress = int((i + 1) / total_entries * 100)
                        self.update_progress(progress)
                        
                    except (OSError, IOError) as e:
                        # Log inaccessible files but continue
                        self.update_status(f"⚠️ Cannot access: {item}")
                        continue
                
            except PermissionError:
                self.error_signal.emit(f"Permission denied accessing: {self.path}")
                return "Permission denied"
            
            # Sort items: directories first, then by name
            items.sort(key=lambda x: (not x['is_dir'], x['name'].lower()))
            file_list.extend(items)
            
            # Cache the results
            if self.use_cache:
                with QMutexLocker(self._cache_mutex):
                    self._cache[self.path] = {
                        'data': file_list,
                        'timestamp': time.time()
                    }
            
            self.files_loaded.emit(self.path, file_list)
            return f"Loaded {len(items)} items"
            
        except Exception as e:
            self.error_signal.emit(f"Error loading directory: {str(e)}")
            return "Error occurred"


class DriveFileLoadThread(BaseOperationThread):
    """Improved thread for loading Google Drive files with better caching"""
    
    files_loaded = pyqtSignal(str, list)  # folder_id, file_list
    
    def __init__(self, drive_client: GoogleDriveClient, folder_id: str,
                 current_path_history: List[Tuple[str, str]], use_cache: bool = True):
        super().__init__()
        self.drive_client = drive_client
        self.folder_id = folder_id
        self.current_path_history = current_path_history
        self.use_cache = use_cache
        self._cache = {}
        self._cache_mutex = QMutex()
    
    def create_transfer_entry(self) -> str:
        """Not needed for file loading operations"""
        return ""
    
    def execute_operation(self) -> str:
        """Load Google Drive files with improved caching and error handling"""
        # Check cache first
        if self.use_cache:
            with QMutexLocker(self._cache_mutex):
                if self.folder_id in self._cache:
                    cache_entry = self._cache[self.folder_id]
                    # Check if cache is still valid (less than 60 seconds old)
                    if time.time() - cache_entry['timestamp'] < 60:
                        self.files_loaded.emit(self.folder_id, cache_entry['data'])
                        return "Loaded from cache"
        
        try:
            file_list = []
            
            # Add parent directory entry
            if len(self.current_path_history) > 1:
                parent_id = self.current_path_history[-2][1]
                file_list.append({
                    'name': '..',
                    'type': 'parent',
                    'size': '',
                    'modified': '',
                    'mimeType': 'application/vnd.google-apps.folder',
                    'id': parent_id,
                    'is_dir': True
                })
            
            self.update_status("🔍 Loading Google Drive files...")
            
            # Get files from Google Drive
            files = self.drive_client.list_files(self.folder_id)
            
            # Process files
            folders = []
            other_files = []
            total_files = len(files)
            
            for i, file in enumerate(files):
                if self.is_operation_cancelled():
                    break
                
                file_info = {
                    'name': file.get('name', ''),
                    'type': 'folder' if file.get('mimeType') == 'application/vnd.google-apps.folder' else 'file',
                    'size': int(file.get('size', 0)) if 'size' in file else 0,
                    'modified': file.get('modifiedTime', ''),
                    'mimeType': file.get('mimeType', ''),
                    'id': file.get('id', ''),
                    'is_dir': file.get('mimeType') == 'application/vnd.google-apps.folder'
                }
                
                if file_info['is_dir']:
                    folders.append(file_info)
                else:
                    other_files.append(file_info)
                
                # Update progress
                progress = int((i + 1) / total_files * 100)
                self.update_progress(progress)
            
            # Sort and combine
            folders.sort(key=lambda x: x['name'].lower())
            other_files.sort(key=lambda x: x['name'].lower())
            file_list.extend(folders + other_files)
            
            # Cache the results
            if self.use_cache:
                with QMutexLocker(self._cache_mutex):
                    self._cache[self.folder_id] = {
                        'data': file_list,
                        'timestamp': time.time()
                    }
            
            self.files_loaded.emit(self.folder_id, file_list)
            return f"Loaded {len(files)} items"
            
        except Exception as e:
            self.error_signal.emit(f"Error loading Google Drive folder: {str(e)}")
            return "Error occurred"
    
    def clear_cache(self) -> None:
        """Clear the cache"""
        with QMutexLocker(self._cache_mutex):
            self._cache.clear()
    
    def clear_cache_entry(self, folder_id: str) -> None:
        """Clear a specific cache entry"""
        with QMutexLocker(self._cache_mutex):
            if folder_id in self._cache:
                del self._cache[folder_id]


class BackgroundFileIndexThread(BaseOperationThread):
    """Background thread for indexing files for search functionality"""
    
    index_updated = pyqtSignal(dict)  # indexed data
    
    def __init__(self, drive_client: GoogleDriveClient, folder_id: str = 'root'):
        super().__init__()
        self.drive_client = drive_client
        self.folder_id = folder_id
        self.indexed_files = {}
    
    def create_transfer_entry(self) -> str:
        """Not needed for indexing operations"""
        return ""
    
    def execute_operation(self) -> str:
        """Build search index of all files"""
        try:
            self.update_status("🔍 Building file index...")
            
            def index_folder_recursive(folder_id: str, path: str = "") -> None:
                """Recursively index a folder"""
                if self.is_operation_cancelled():
                    return
                
                try:
                    files = self.drive_client.list_files(folder_id)
                    
                    for file in files:
                        if self.is_operation_cancelled():
                            break
                        
                        file_id = file.get('id', '')
                        file_name = file.get('name', '')
                        is_folder = file.get('mimeType') == 'application/vnd.google-apps.folder'
                        
                        # Add to index
                        full_path = f"{path}/{file_name}" if path else file_name
                        self.indexed_files[file_id] = {
                            'name': file_name,
                            'path': full_path,
                            'is_folder': is_folder,
                            'parent_id': folder_id,
                            'size': file.get('size', 0),
                            'modified': file.get('modifiedTime', ''),
                            'mimeType': file.get('mimeType', '')
                        }
                        
                        # Recursively index subfolders
                        if is_folder:
                            index_folder_recursive(file_id, full_path)
                        
                        self.update_status(f"Indexed: {full_path}")
                
                except Exception as e:
                    self.update_status(f"Error indexing folder {folder_id}: {str(e)}")
            
            # Start indexing from root
            index_folder_recursive(self.folder_id)
            
            if not self.is_operation_cancelled():
                self.index_updated.emit(self.indexed_files)
                return f"Indexed {len(self.indexed_files)} items"
            
            return "Indexing cancelled"
            
        except Exception as e:
            self.error_signal.emit(f"Error building index: {str(e)}")
            return "Error occurred"

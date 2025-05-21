import os
import sys
import io
import pickle
import time
import threading
import queue
from datetime import datetime
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
from PyQt5.QtWidgets import (QApplication, QMainWindow, QTreeView, QWidget,
                             QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
                             QFileDialog, QMessageBox, QMenu, QAction, QHeaderView,
                             QSplitter, QToolBar, QStatusBar, QProgressBar, QLineEdit,
                             QListView, QTabWidget, QComboBox, QDialog, QDialogButtonBox,
                             QFormLayout, QInputDialog, QShortcut, QFrame, QGridLayout,
                             QListWidget, QTableWidget, QTableWidgetItem, QGroupBox, QRadioButton,
                             QCheckBox, QSpinBox, QTextEdit, QScrollArea, QSizePolicy)
from PyQt5.QtCore import Qt, QSize, QMimeData, QUrl, pyqtSignal, QThread, QModelIndex, QDir, QTimer
from PyQt5.QtGui import QStandardItemModel, QStandardItem, QIcon, QKeySequence, QFont, QColor, QPalette, QPixmap
import random  # For demo purposes

# Google Drive API scopes
SCOPES = ['https://www.googleapis.com/auth/drive']


class PerformanceMetrics:
    """Tracks performance metrics for operations"""

    def __init__(self):
        self.start_time = 0
        self.end_time = 0
        self.total_bytes = 0
        self.processed_bytes = 0
        self.metrics_history = {
            'upload_speeds': [],
            'download_speeds': [],
            'operation_times': []
        }

    def start_operation(self, total_bytes=0):
        """Start timing an operation"""
        self.start_time = time.time()
        self.total_bytes = total_bytes
        self.processed_bytes = 0

    def update_progress(self, processed_bytes):
        """Update progress of current operation"""
        self.processed_bytes = processed_bytes

    def end_operation(self, operation_type):
        """End timing an operation and record metrics"""
        self.end_time = time.time()
        duration = self.end_time - self.start_time

        if duration > 0 and self.total_bytes > 0:
            speed = self.total_bytes / duration / 1024 / 1024  # MB/s

            if operation_type == 'upload':
                self.metrics_history['upload_speeds'].append(speed)
            elif operation_type == 'download':
                self.metrics_history['download_speeds'].append(speed)

        self.metrics_history['operation_times'].append(duration)

        return {
            'duration': duration,
            'speed': speed if duration > 0 and self.total_bytes > 0 else 0,
            'total_bytes': self.total_bytes
        }

    def get_average_metrics(self):
        """Get average metrics"""
        upload_avg = sum(self.metrics_history['upload_speeds']) / max(len(self.metrics_history['upload_speeds']), 1)
        download_avg = sum(self.metrics_history['download_speeds']) / max(len(self.metrics_history['download_speeds']),
                                                                          1)
        time_avg = sum(self.metrics_history['operation_times']) / max(len(self.metrics_history['operation_times']), 1)

        return {
            'avg_upload_speed': upload_avg,
            'avg_download_speed': download_avg,
            'avg_operation_time': time_avg
        }


class OperationThread(QThread):
    """Base thread class for Drive operations"""
    progress_signal = pyqtSignal(int)
    status_signal = pyqtSignal(str)
    completed_signal = pyqtSignal(str, dict)  # Result, metrics
    error_signal = pyqtSignal(str)

    def __init__(self, drive_client):
        super().__init__()
        self.drive_client = drive_client
        self.metrics = PerformanceMetrics()


class UploadThread(OperationThread):
    """Thread for uploading files to Google Drive"""

    def __init__(self, drive_client, file_path, parent_id='root'):
        super().__init__(drive_client)
        self.file_path = file_path
        self.parent_id = parent_id
        self.file_size = os.path.getsize(file_path)

    def run(self):
        """Execute the upload operation"""
        try:
            # Start timing and set total bytes
            self.metrics.start_operation(self.file_size)

            # Upload the file and track progress
            file_id = self.drive_client.upload_file(
                self.file_path,
                self.parent_id,
                self.progress_signal,
                self.metrics
            )

            # End timing
            metrics_result = self.metrics.end_operation('upload')

            self.completed_signal.emit(file_id, metrics_result)
        except Exception as e:
            self.error_signal.emit(str(e))


class FolderUploadThread(OperationThread):
    """Thread for uploading folders to Google Drive"""

    def __init__(self, drive_client, folder_path, parent_id='root'):
        super().__init__(drive_client)
        self.folder_path = folder_path
        self.parent_id = parent_id
        self.folder_name = os.path.basename(folder_path)

        # Calculate total size and file count
        self.total_size = 0
        self.file_count = 0
        self.calculate_folder_stats(folder_path)

        # Initialize processed bytes and file count
        self.processed_bytes = 0
        self.processed_files = 0

    def calculate_folder_stats(self, folder_path):
        """Calculate total size and file count of a folder"""
        for root, dirs, files in os.walk(folder_path):
            for file in files:
                file_path = os.path.join(root, file)
                try:
                    self.total_size += os.path.getsize(file_path)
                    self.file_count += 1
                except Exception:
                    pass

    def run(self):
        """Execute the folder upload operation"""
        try:
            # Start timing and set total bytes
            self.metrics.start_operation(self.total_size)

            # Create parent folder on Drive
            self.status_signal.emit(f"Creating folder: {self.folder_name}")
            folder_id = self.drive_client.create_folder(self.folder_name, self.parent_id)

            # Upload folder contents recursively
            self.upload_folder_contents(self.folder_path, folder_id)

            # End timing
            metrics_result = self.metrics.end_operation('upload')

            self.completed_signal.emit(folder_id, metrics_result)
        except Exception as e:
            self.error_signal.emit(str(e))

    def upload_folder_contents(self, folder_path, parent_id):
        """Recursively upload folder contents"""
        # List all items in the folder
        for item in os.listdir(folder_path):
            item_path = os.path.join(folder_path, item)

            if os.path.isfile(item_path):
                # Upload file
                self.status_signal.emit(f"Uploading file: {item}")
                try:
                    file_size = os.path.getsize(item_path)

                    # Create a progress tracker for this file
                    def file_progress_callback(progress):
                        # Calculate how much of the total has been processed
                        file_progress = progress / 100  # Convert percentage to fraction
                        file_bytes_processed = file_size * file_progress

                        # Update total progress
                        self.processed_bytes += file_bytes_processed
                        total_progress = int((self.processed_bytes / self.total_size) * 100)
                        self.progress_signal.emit(total_progress)

                        # Update metrics
                        self.metrics.update_progress(self.processed_bytes)

                    # Upload the file
                    self.drive_client.upload_file(
                        item_path,
                        parent_id,
                        file_progress_callback
                    )

                    # Update processed files count
                    self.processed_files += 1
                    self.status_signal.emit(f"Uploaded {self.processed_files} of {self.file_count} files")

                except Exception as e:
                    self.status_signal.emit(f"Error uploading {item}: {str(e)}")

            elif os.path.isdir(item_path):
                # Create subfolder
                self.status_signal.emit(f"Creating subfolder: {item}")
                try:
                    subfolder_id = self.drive_client.create_folder(item, parent_id)

                    # Upload subfolder contents recursively
                    self.upload_folder_contents(item_path, subfolder_id)
                except Exception as e:
                    self.status_signal.emit(f"Error creating subfolder {item}: {str(e)}")


class DownloadThread(OperationThread):
    """Thread for downloading files from Google Drive"""

    def __init__(self, drive_client, file_id, file_name, local_dir, file_size=0):
        super().__init__(drive_client)
        self.file_id = file_id
        self.file_name = file_name
        self.local_dir = local_dir
        self.file_size = file_size

    def run(self):
        """Execute the download operation"""
        try:
            # Start timing and set total bytes
            self.metrics.start_operation(self.file_size)

            # Download the file and track progress
            file_path = self.drive_client.download_file(
                self.file_id,
                self.file_name,
                self.local_dir,
                self.progress_signal,
                self.metrics
            )

            # End timing
            metrics_result = self.metrics.end_operation('download')

            self.completed_signal.emit(file_path, metrics_result)
        except Exception as e:
            self.error_signal.emit(str(e))


class FolderDownloadThread(OperationThread):
    """Thread for downloading folders from Google Drive"""

    def __init__(self, drive_client, folder_id, folder_name, local_dir):
        super().__init__(drive_client)
        self.folder_id = folder_id
        self.folder_name = folder_name
        self.local_dir = local_dir

        # Calculate total size and file count
        self.total_size = 0
        self.file_count = 0

        # Store file info for all files in the folder (recursive)
        self.files_to_download = []

        # Initialize processed bytes and file count
        self.processed_bytes = 0
        self.processed_files = 0

    def run(self):
        """Execute the folder download operation"""
        try:
            # Create local folder
            local_folder_path = os.path.join(self.local_dir, self.folder_name)
            os.makedirs(local_folder_path, exist_ok=True)

            # First, scan the Drive folder to get all files and total size
            self.status_signal.emit(f"Scanning folder: {self.folder_name}")
            self.scan_drive_folder(self.folder_id, local_folder_path, '')

            # Start timing and set total bytes
            self.metrics.start_operation(self.total_size)

            # Now download all files
            self.status_signal.emit(f"Downloading {self.file_count} files")
            self.download_files()

            # End timing
            metrics_result = self.metrics.end_operation('download')

            self.completed_signal.emit(local_folder_path, metrics_result)
        except Exception as e:
            self.error_signal.emit(str(e))

    def scan_drive_folder(self, folder_id, local_folder_path, relative_path):
        """Recursively scan a Drive folder and prepare download info"""
        files = self.drive_client.list_files(folder_id)

        for file in files:
            file_name = file.get('name', '')
            file_id = file.get('id', '')
            mime_type = file.get('mimeType', '')

            # Calculate the local path for this file/folder
            if relative_path:
                file_relative_path = os.path.join(relative_path, file_name)
            else:
                file_relative_path = file_name

            file_local_path = os.path.join(local_folder_path, file_name)

            if mime_type == 'application/vnd.google-apps.folder':
                # Create the local subfolder
                os.makedirs(file_local_path, exist_ok=True)

                # Recursively scan the subfolder
                self.scan_drive_folder(file_id, local_folder_path, file_relative_path)
            else:
                # Add file to download list
                file_size = int(file.get('size', 0))
                self.total_size += file_size
                self.file_count += 1

                self.files_to_download.append({
                    'id': file_id,
                    'name': file_name,
                    'size': file_size,
                    'local_path': os.path.dirname(file_local_path),
                    'relative_path': file_relative_path
                })

    def download_files(self):
        """Download all files in the download list"""
        for i, file_info in enumerate(self.files_to_download):
            file_id = file_info['id']
            file_name = file_info['name']
            file_size = file_info['size']
            local_path = file_info['local_path']
            relative_path = file_info['relative_path']

            self.status_signal.emit(f"Downloading {i + 1} of {self.file_count}: {relative_path}")

            try:
                # Create a progress tracker for this file
                def file_progress_callback(progress):
                    # Calculate how much of the total has been processed
                    file_progress = progress / 100  # Convert percentage to fraction
                    file_bytes_processed = file_size * file_progress

                    # Update total progress
                    current_progress = int(((self.processed_bytes + file_bytes_processed) / self.total_size) * 100)
                    self.progress_signal.emit(current_progress)

                    # Update metrics
                    self.metrics.update_progress(self.processed_bytes + file_bytes_processed)

                # Download the file
                self.drive_client.download_file(
                    file_id,
                    file_name,
                    local_path,
                    file_progress_callback
                )

                # Update processed bytes and files
                self.processed_bytes += file_size
                self.processed_files += 1

            except Exception as e:
                self.status_signal.emit(f"Error downloading {relative_path}: {str(e)}")


class GoogleDriveClient:
    """Client for Google Drive API interactions"""

    def __init__(self):
        """Initialize the Google Drive connection"""
        self.service = self._get_drive_service()

    def _get_drive_service(self):
        """Authenticate and create the Google Drive service"""
        creds = None

        # Check for existing token
        if os.path.exists('token.pickle'):
            with open('token.pickle', 'rb') as token:
                creds = pickle.load(token)

        # If no valid credentials, prompt user to log in
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    'credentials.json', SCOPES)
                creds = flow.run_local_server(port=0)

            # Save token for next time
            with open('token.pickle', 'wb') as token:
                pickle.dump(creds, token)

        # Return Google Drive service
        return build('drive', 'v3', credentials=creds)

    def list_files(self, parent_id='root'):
        """List files in Google Drive folder"""
        query = f"'{parent_id}' in parents and trashed=false"
        results = self.service.files().list(
            q=query,
            pageSize=100,
            fields="nextPageToken, files(id, name, mimeType, size, modifiedTime)"
        ).execute()

        return results.get('files', [])

    def list_shared_drives(self):
        """List available Shared Drives"""
        try:
            results = self.service.drives().list(
                pageSize=50
            ).execute()
            return results.get('drives', [])
        except Exception as e:
            print(f"Error listing Shared Drives: {str(e)}")
            return []

    def search_files(self, query_string):
        """Search for files by name"""
        query = f"name contains '{query_string}' and trashed=false"
        results = self.service.files().list(
            q=query,
            pageSize=100,
            fields="nextPageToken, files(id, name, mimeType, size, modifiedTime, parents)"
        ).execute()

        return results.get('files', [])

    def get_file_metadata(self, file_id):
        """Get file metadata"""
        return self.service.files().get(
            fileId=file_id,
            fields="id, name, mimeType, size, modifiedTime, parents, description"
        ).execute()

    def download_file(self, file_id, file_name, local_dir, progress_callback=None, metrics=None):
        """Download a file from Google Drive with progress tracking"""
        request = self.service.files().get_media(fileId=file_id)
        file_path = os.path.join(local_dir, file_name)

        with open(file_path, 'wb') as f:
            downloader = MediaIoBaseDownload(f, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()
                if progress_callback:
                    progress = int(status.progress() * 100)
                    progress_callback(progress)

                    # Update metrics if provided
                    if metrics and hasattr(status, 'total_size'):
                        metrics.update_progress(status.progress() * status.total_size)

        return file_path

    def upload_file(self, file_path, parent_id='root', progress_callback=None, metrics=None):
        """Upload a file to Google Drive with progress tracking"""
        file_name = os.path.basename(file_path)
        file_metadata = {
            'name': file_name,
            'parents': [parent_id]
        }

        # Use appropriate chunksize for progress updates
        chunksize = 1024 * 1024  # 1MB

        media = MediaFileUpload(
            file_path,
            resumable=True,
            chunksize=chunksize
        )

        # Create request but don't execute immediately
        request = self.service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id'
        )

        # Execute request with progress updates
        response = None
        file_size = os.path.getsize(file_path)
        uploaded = 0

        while response is None:
            status, response = request.next_chunk()
            if status:
                uploaded += chunksize
                progress = min(int((uploaded / file_size) * 100), 100)
                if progress_callback:
                    progress_callback(progress)

                    # Update metrics if provided
                    if metrics:
                        metrics.update_progress(uploaded)

        return response.get('id')

    def create_folder(self, folder_name, parent_id='root'):
        """Create a new folder in Google Drive"""
        file_metadata = {
            'name': folder_name,
            'mimeType': 'application/vnd.google-apps.folder',
            'parents': [parent_id]
        }

        folder = self.service.files().create(
            body=file_metadata,
            fields='id'
        ).execute()

        return folder.get('id')

    def rename_item(self, file_id, new_name):
        """Rename a file or folder"""
        file_metadata = {'name': new_name}

        updated_file = self.service.files().update(
            fileId=file_id,
            body=file_metadata,
            fields='id, name'
        ).execute()

        return updated_file

    def delete_item(self, file_id):
        """Delete a file or folder (move to trash)"""
        self.service.files().update(
            fileId=file_id,
            body={'trashed': True}
        ).execute()

    def move_item(self, file_id, destination_folder_id):
        """Move a file to another folder"""
        # Get current parents
        file = self.service.files().get(
            fileId=file_id,
            fields='parents'
        ).execute()

        # Remove current parents and add new parent
        previous_parents = ",".join(file.get('parents', []))

        # Update the file with the new parent
        file = self.service.files().update(
            fileId=file_id,
            addParents=destination_folder_id,
            removeParents=previous_parents,
            fields='id, parents'
        ).execute()

        return file

    def permanently_delete_item(self, file_id):
        """Permanently delete a file or folder"""
        self.service.files().delete(fileId=file_id).execute()


class FileListWidget(QTableWidget):
    """Custom widget for displaying file lists with sorting and filtering"""

    def __init__(self, headers, parent=None):
        super().__init__(parent)
        self.setColumnCount(len(headers))
        self.setHorizontalHeaderLabels(headers)
        self.setSelectionBehavior(QTableWidget.SelectRows)
        self.setSelectionMode(QTableWidget.ExtendedSelection)
        self.setSortingEnabled(True)
        self.setAlternatingRowColors(True)
        self.verticalHeader().setVisible(False)
        self.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)

        # Style the table
        self.setStyleSheet("""
            QTableWidget {
                border: 1px solid #dcdcdc;
                border-radius: 5px;
                background-color: #ffffff;
                selection-background-color: #e0f0ff;
            }
            QHeaderView::section {
                background-color: #f0f0f0;
                padding: 5px;
                border: 1px solid #dcdcdc;
                font-weight: bold;
            }
        """)


class MetricsPanel(QWidget):
    """Widget to display performance metrics"""

    def __init__(self, parent=None):
        super().__init__(parent)

        # Setup layout
        self.layout = QVBoxLayout(self)

        # Title
        title = QLabel("Performance Metrics")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 16px; font-weight: bold; margin-bottom: 10px;")
        self.layout.addWidget(title)

        # Metrics grid
        metrics_grid = QGridLayout()

        # Create labels for metrics
        self.upload_speed_label = QLabel("0 MB/s")
        self.download_speed_label = QLabel("0 MB/s")
        self.last_operation_time_label = QLabel("0 sec")
        self.avg_upload_speed_label = QLabel("0 MB/s")
        self.avg_download_speed_label = QLabel("0 MB/s")
        self.total_operations_label = QLabel("0")

        # Style metric values
        for label in [self.upload_speed_label, self.download_speed_label,
                      self.last_operation_time_label, self.avg_upload_speed_label,
                      self.avg_download_speed_label, self.total_operations_label]:
            label.setStyleSheet("font-size: 14px; font-weight: bold; color: #2980b9;")
            label.setAlignment(Qt.AlignRight)

        # Add metrics to grid
        metrics_grid.addWidget(QLabel("Last Upload Speed:"), 0, 0)
        metrics_grid.addWidget(self.upload_speed_label, 0, 1)

        metrics_grid.addWidget(QLabel("Last Download Speed:"), 1, 0)
        metrics_grid.addWidget(self.download_speed_label, 1, 1)

        metrics_grid.addWidget(QLabel("Last Operation Time:"), 2, 0)
        metrics_grid.addWidget(self.last_operation_time_label, 2, 1)

        metrics_grid.addWidget(QLabel("Avg Upload Speed:"), 3, 0)
        metrics_grid.addWidget(self.avg_upload_speed_label, 3, 1)

        metrics_grid.addWidget(QLabel("Avg Download Speed:"), 4, 0)
        metrics_grid.addWidget(self.avg_download_speed_label, 4, 1)

        metrics_grid.addWidget(QLabel("Total Operations:"), 5, 0)
        metrics_grid.addWidget(self.total_operations_label, 5, 1)

        self.layout.addLayout(metrics_grid)

        # Create speed history tables
        self.create_speed_history_tables()

        # Style the panel
        self.setStyleSheet("""
            QLabel {
                font-size: 12px;
            }
            QWidget {
                background-color: #f9f9f9;
                border-radius: 8px;
            }
        """)

        # Initial data
        self.upload_speeds = []
        self.download_speeds = []
        self.operation_times = []

    def create_speed_history_tables(self):
        """Create tables to visualize upload/download speeds"""
        history_group = QGroupBox("Speed History")
        history_layout = QVBoxLayout(history_group)

        # Upload speeds table
        upload_label = QLabel("Upload Speeds (MB/s)")
        upload_label.setStyleSheet("font-weight: bold;")
        history_layout.addWidget(upload_label)

        self.upload_table = QTableWidget(0, 2)
        self.upload_table.setHorizontalHeaderLabels(["Operation #", "Speed (MB/s)"])
        self.upload_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.upload_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.upload_table.setMaximumHeight(100)
        history_layout.addWidget(self.upload_table)

        # Download speeds table
        download_label = QLabel("Download Speeds (MB/s)")
        download_label.setStyleSheet("font-weight: bold;")
        history_layout.addWidget(download_label)

        self.download_table = QTableWidget(0, 2)
        self.download_table.setHorizontalHeaderLabels(["Operation #", "Speed (MB/s)"])
        self.download_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.download_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.download_table.setMaximumHeight(100)
        history_layout.addWidget(self.download_table)

        self.layout.addWidget(history_group)

    def update_metrics(self, operation_type, metrics):
        """Update displayed metrics"""
        duration = metrics.get('duration', 0)
        speed = metrics.get('speed', 0)

        # Update last operation time
        self.last_operation_time_label.setText(f"{duration:.2f} sec")

        # Update speed based on operation type
        if operation_type == 'upload':
            self.upload_speed_label.setText(f"{speed:.2f} MB/s")
            self.upload_speeds.append(speed)

            # Update upload table
            self.update_speed_table(self.upload_table, self.upload_speeds)

        elif operation_type == 'download':
            self.download_speed_label.setText(f"{speed:.2f} MB/s")
            self.download_speeds.append(speed)

            # Update download table
            self.update_speed_table(self.download_table, self.download_speeds)

        # Update all operation times
        self.operation_times.append(duration)

        # Calculate and update averages
        if self.upload_speeds:
            avg_upload = sum(self.upload_speeds) / len(self.upload_speeds)
            self.avg_upload_speed_label.setText(f"{avg_upload:.2f} MB/s")

        if self.download_speeds:
            avg_download = sum(self.download_speeds) / len(self.download_speeds)
            self.avg_download_speed_label.setText(f"{avg_download:.2f} MB/s")

        # Update total operations
        total = len(self.upload_speeds) + len(self.download_speeds)
        self.total_operations_label.setText(str(total))

    def update_speed_table(self, table, speeds):
        """Update a speed history table"""
        # Clear table
        table.setRowCount(0)

        # Add last 5 speeds (most recent first)
        for i, speed in enumerate(speeds[-5:]):
            row = table.rowCount()
            table.insertRow(row)

            # Operation number
            op_num = len(speeds) - i
            table.setItem(row, 0, QTableWidgetItem(str(op_num)))

            # Speed
            speed_item = QTableWidgetItem(f"{speed:.2f}")
            table.setItem(row, 1, speed_item)


class TestPanel(QWidget):
    """Panel for testing Drive operations"""
    operation_started = pyqtSignal(str)
    operation_completed = pyqtSignal(str, str, dict)
    operation_error = pyqtSignal(str)

    def __init__(self, drive_client, parent=None):
        super().__init__(parent)
        self.drive_client = drive_client

        # Setup layout
        self.layout = QVBoxLayout(self)

        # Create title
        title = QLabel("Operation Testing")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 16px; font-weight: bold; margin-bottom: 10px;")
        self.layout.addWidget(title)

        # Create operation buttons
        self.create_operation_buttons()

        # Create test options
        self.create_test_options()

        # Create progress section
        self.create_progress_section()

        # Apply styles
        self.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                border-radius: 5px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
            QPushButton:disabled {
                background-color: #bdc3c7;
            }
            QGroupBox {
                font-weight: bold;
                border: 1px solid #dcdcdc;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 15px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top center;
                padding: 0 5px;
            }
        """)

    def create_operation_buttons(self):
        """Create buttons for different operations"""
        button_layout = QGridLayout()

        # Upload button
        self.upload_btn = QPushButton("Upload File")
        self.upload_btn.clicked.connect(self.start_upload_test)
        button_layout.addWidget(self.upload_btn, 0, 0)

        # Download button
        self.download_btn = QPushButton("Download File")
        self.download_btn.clicked.connect(self.start_download_test)
        button_layout.addWidget(self.download_btn, 0, 1)

        # Move button
        self.move_btn = QPushButton("Move File")
        self.move_btn.clicked.connect(self.start_move_test)
        button_layout.addWidget(self.move_btn, 1, 0)

        # Delete button
        self.delete_btn = QPushButton("Delete File")
        self.delete_btn.clicked.connect(self.start_delete_test)
        button_layout.addWidget(self.delete_btn, 1, 1)

        # Add buttons to layout
        self.layout.addLayout(button_layout)

    def create_test_options(self):
        """Create options for configuring tests"""
        options_group = QGroupBox("Test Options")
        options_layout = QVBoxLayout(options_group)

        # File size selection
        size_layout = QHBoxLayout()
        size_layout.addWidget(QLabel("Test File Size:"))

        self.file_size_combo = QComboBox()
        self.file_size_combo.addItem("Small (1MB)", 1)
        self.file_size_combo.addItem("Medium (10MB)", 10)
        self.file_size_combo.addItem("Large (100MB)", 100)
        size_layout.addWidget(self.file_size_combo)

        options_layout.addLayout(size_layout)

        # Number of operations
        count_layout = QHBoxLayout()
        count_layout.addWidget(QLabel("Number of Operations:"))

        self.operation_count = QSpinBox()
        self.operation_count.setRange(1, 100)
        self.operation_count.setValue(1)
        count_layout.addWidget(self.operation_count)

        options_layout.addLayout(count_layout)

        # Batch or Sequential
        method_layout = QHBoxLayout()
        method_layout.addWidget(QLabel("Execution Method:"))

        self.execution_combo = QComboBox()
        self.execution_combo.addItem("Sequential", "sequential")
        self.execution_combo.addItem("Parallel", "parallel")
        method_layout.addWidget(self.execution_combo)

        options_layout.addLayout(method_layout)

        # Add options to main layout
        self.layout.addWidget(options_group)

    def create_progress_section(self):
        """Create progress bar and status section"""
        progress_group = QGroupBox("Operation Progress")
        progress_layout = QVBoxLayout(progress_group)

        # Status label
        self.status_label = QLabel("Ready")
        self.status_label.setAlignment(Qt.AlignCenter)
        progress_layout.addWidget(self.status_label)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        progress_layout.addWidget(self.progress_bar)

        # Add to main layout
        self.layout.addWidget(progress_group)

    def start_upload_test(self):
        """Start an upload test"""
        # Get test file size
        file_size_mb = self.file_size_combo.currentData()

        # Create temporary test file
        temp_dir = os.path.join(os.path.expanduser("~"), "temp_drive_test")
        os.makedirs(temp_dir, exist_ok=True)

        test_file_path = os.path.join(temp_dir, f"test_upload_{file_size_mb}MB.dat")

        # Check if file already exists
        if not os.path.exists(test_file_path):
            self.status_label.setText(f"Creating {file_size_mb}MB test file...")

            # Create file with random data
            with open(test_file_path, 'wb') as f:
                f.write(os.urandom(file_size_mb * 1024 * 1024))

        # Start upload
        self.status_label.setText(f"Uploading {file_size_mb}MB file...")
        self.progress_bar.setValue(0)

        # Create and start upload thread
        self.upload_thread = UploadThread(
            self.drive_client,
            test_file_path,
            'root'
        )

        # Connect signals
        self.upload_thread.progress_signal.connect(self.progress_bar.setValue)
        self.upload_thread.completed_signal.connect(
            lambda file_id, metrics: self.operation_completed.emit('upload', file_id, metrics)
        )
        self.upload_thread.error_signal.connect(self.operation_error.emit)

        # Emit operation started signal
        self.operation_started.emit('upload')

        # Start thread
        self.upload_thread.start()

    def start_download_test(self):
        """Start a download test"""
        # Get list of files
        files = self.drive_client.list_files()

        # Filter for test files
        test_files = [f for f in files if 'test_upload_' in f.get('name', '')]

        if not test_files:
            self.status_label.setText("No test files found. Upload a file first.")
            return

        # Sort by size (largest first)
        test_files.sort(key=lambda f: int(f.get('size', '0')), reverse=True)

        # Get file to download
        file_to_download = test_files[0]
        file_id = file_to_download.get('id')
        file_name = file_to_download.get('name')
        file_size = int(file_to_download.get('size', 0))

        # Create temp download directory
        temp_dir = os.path.join(os.path.expanduser("~"), "temp_drive_test", "downloads")
        os.makedirs(temp_dir, exist_ok=True)

        # Start download
        self.status_label.setText(f"Downloading {file_name}...")
        self.progress_bar.setValue(0)

        # Create and start download thread
        self.download_thread = DownloadThread(
            self.drive_client,
            file_id,
            file_name,
            temp_dir,
            file_size
        )

        # Connect signals
        self.download_thread.progress_signal.connect(self.progress_bar.setValue)
        self.download_thread.completed_signal.connect(
            lambda file_path, metrics: self.operation_completed.emit('download', file_path, metrics)
        )
        self.download_thread.error_signal.connect(self.operation_error.emit)

        # Emit operation started signal
        self.operation_started.emit('download')

        # Start thread
        self.download_thread.start()

    def start_move_test(self):
        """Test moving a file"""
        # Get list of files
        files = self.drive_client.list_files()

        # Filter for test files
        test_files = [f for f in files if 'test_upload_' in f.get('name', '')]

        if not test_files:
            self.status_label.setText("No test files found. Upload a file first.")
            return

        # Create a test folder if it doesn't exist
        self.status_label.setText("Creating test folder...")

        # First check if test folder already exists
        test_folders = [f for f in files if f.get('name') == 'Test_Move_Folder' and
                        f.get('mimeType') == 'application/vnd.google-apps.folder']

        if test_folders:
            folder_id = test_folders[0]['id']
        else:
            folder_id = self.drive_client.create_folder('Test_Move_Folder')

        # Get file to move
        file_to_move = test_files[0]
        file_id = file_to_move.get('id')
        file_name = file_to_move.get('name')

        # Move the file
        self.status_label.setText(f"Moving {file_name} to Test_Move_Folder...")

        try:
            self.drive_client.move_item(file_id, folder_id)

            # Create mock metrics for consistency
            metrics = {
                'duration': 0.5,
                'speed': 0,
                'total_bytes': 0
            }

            self.operation_completed.emit('move', f"Moved {file_name} to Test_Move_Folder", metrics)
        except Exception as e:
            self.operation_error.emit(str(e))

    def start_delete_test(self):
        """Test deleting a file"""
        # Get list of files
        files = self.drive_client.list_files()

        # Filter for test files
        test_files = [f for f in files if 'test_upload_' in f.get('name', '')]

        # Also check in the test folder
        test_folders = [f for f in files if f.get('name') == 'Test_Move_Folder' and
                        f.get('mimeType') == 'application/vnd.google-apps.folder']

        if test_folders:
            folder_files = self.drive_client.list_files(test_folders[0]['id'])
            test_files.extend(folder_files)

        if not test_files:
            self.status_label.setText("No test files found. Upload a file first.")
            return

        # Get file to delete
        file_to_delete = test_files[0]
        file_id = file_to_delete.get('id')
        file_name = file_to_delete.get('name')

        # Delete the file (move to trash)
        self.status_label.setText(f"Deleting {file_name}...")

        try:
            self.drive_client.delete_item(file_id)

            # Create mock metrics for consistency
            metrics = {
                'duration': 0.3,
                'speed': 0,
                'total_bytes': 0
            }

            self.operation_completed.emit('delete', f"Deleted {file_name}", metrics)
        except Exception as e:
            self.operation_error.emit(str(e))


class ModernDriveExplorer(QMainWindow):
    """Main application window"""

    def __init__(self):
        super().__init__()

        # Initialize the Google Drive client
        try:
            self.drive_client = GoogleDriveClient()
            self.connected = True

            # Load Shared Drives
            self.shared_drives = self.drive_client.list_shared_drives()
        except Exception as e:
            self.connected = False
            QMessageBox.critical(self, "Connection Error",
                                 f"Could not connect to Google Drive: {str(e)}")
            self.shared_drives = []

        # Window configuration
        self.setWindowTitle("Modern Google Drive Explorer")
        self.resize(1200, 800)

        # Create central widget
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)

        # Create main layout
        main_layout = QHBoxLayout(self.central_widget)

        # Create splitter for resizable sections
        self.splitter = QSplitter(Qt.Horizontal)

        # Create left panel (file explorer)
        self.create_file_explorer_panel()

        # Create right panel (testing & metrics)
        self.create_right_panel()

        # Add panels to splitter
        self.splitter.addWidget(self.file_explorer_panel)
        self.splitter.addWidget(self.right_panel)

        # Set initial sizes (60% file explorer, 40% right panel)
        self.splitter.setSizes([int(self.width() * 0.6), int(self.width() * 0.4)])

        # Add splitter to main layout
        main_layout.addWidget(self.splitter)

        # Create toolbar and status bar
        self.create_toolbar()

        # Status bar with permanent progress bar
        self.status_bar = QStatusBar()
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedWidth(150)
        self.progress_bar.setVisible(False)
        self.status_bar.addPermanentWidget(self.progress_bar)
        self.setStatusBar(self.status_bar)

        # Keyboard shortcuts
        QShortcut(QKeySequence("F5"), self, self.refresh_all)
        QShortcut(QKeySequence("Ctrl+F"), self, self.show_search_dialog)

        # Connect test panel signals
        self.test_panel.operation_started.connect(self.on_operation_started)
        self.test_panel.operation_completed.connect(self.on_operation_completed)
        self.test_panel.operation_error.connect(self.on_operation_error)

        # Initial refresh
        if self.connected:
            self.refresh_all()

    def create_file_explorer_panel(self):
        """Create the file explorer panel with tabs for local and Drive"""
        self.file_explorer_panel = QWidget()
        layout = QVBoxLayout(self.file_explorer_panel)

        # Create tab widget
        self.explorer_tabs = QTabWidget()

        # Create local files tab
        self.local_tab = QWidget()
        local_layout = QVBoxLayout(self.local_tab)

        # Local path navigation
        local_path_layout = QHBoxLayout()
        local_path_layout.addWidget(QLabel("Local Path:"))

        self.local_path_edit = QLineEdit(os.path.expanduser("~"))
        self.local_path_edit.returnPressed.connect(self.change_local_path)
        local_path_layout.addWidget(self.local_path_edit)

        local_browse_btn = QPushButton("Browse")
        local_browse_btn.clicked.connect(self.browse_local_folder)
        local_path_layout.addWidget(local_browse_btn)

        local_layout.addLayout(local_path_layout)

        # Local files list
        self.local_files = FileListWidget(["Name", "Size", "Modified", "Type"])
        self.local_files.setContextMenuPolicy(Qt.CustomContextMenu)
        self.local_files.customContextMenuRequested.connect(self.show_local_context_menu)
        self.local_files.doubleClicked.connect(self.local_item_double_clicked)
        local_layout.addWidget(self.local_files)

        # Add local tab to tabs
        self.explorer_tabs.addTab(self.local_tab, "Local Files")

        # Create Google Drive tab
        self.drive_tab = QWidget()
        drive_layout = QVBoxLayout(self.drive_tab)

        # Drive selection and navigation
        drive_header_layout = QHBoxLayout()

        drive_header_layout.addWidget(QLabel("Drive:"))
        self.drive_selector = QComboBox()
        self.drive_selector.addItem("My Drive", "root")

        # Add Shared Drives
        for drive in self.shared_drives:
            self.drive_selector.addItem(drive['name'], drive['id'])

        self.drive_selector.currentIndexChanged.connect(self.change_drive)
        drive_header_layout.addWidget(self.drive_selector)

        # Refresh button
        refresh_btn = QPushButton("⟳")
        refresh_btn.setFixedWidth(30)
        refresh_btn.clicked.connect(self.refresh_drive_files)
        drive_header_layout.addWidget(refresh_btn)

        drive_layout.addLayout(drive_header_layout)

        # Drive path breadcrumb
        path_layout = QHBoxLayout()
        self.drive_back_btn = QPushButton("←")
        self.drive_back_btn.setFixedWidth(30)
        self.drive_back_btn.clicked.connect(self.drive_go_back)
        path_layout.addWidget(self.drive_back_btn)

        self.drive_path_label = QLabel("Root")
        path_layout.addWidget(self.drive_path_label, 1)

        drive_layout.addLayout(path_layout)

        # Drive files list
        self.drive_files = FileListWidget(["Name", "Size", "Modified", "Type", "ID"])
        self.drive_files.setColumnHidden(4, True)  # Hide ID column
        self.drive_files.setContextMenuPolicy(Qt.CustomContextMenu)
        self.drive_files.customContextMenuRequested.connect(self.show_drive_context_menu)
        self.drive_files.doubleClicked.connect(self.drive_item_double_clicked)
        drive_layout.addWidget(self.drive_files)

        # Add drive tab to tabs
        self.explorer_tabs.addTab(self.drive_tab, "Google Drive")

        # Add tabs to layout
        layout.addWidget(self.explorer_tabs)

        # Initialize path history for Drive navigation
        self.drive_path_history = [('Root', 'root')]
        self.current_drive_id = 'root'

    def create_right_panel(self):
        """Create the right panel with testing tools and metrics"""
        self.right_panel = QWidget()
        layout = QVBoxLayout(self.right_panel)

        # Create tab widget for right panel
        self.right_tabs = QTabWidget()

        # Create metrics panel
        self.metrics_panel = MetricsPanel()
        self.right_tabs.addTab(self.metrics_panel, "Performance Metrics")

        # Create test panel
        self.test_panel = TestPanel(self.drive_client)
        self.right_tabs.addTab(self.test_panel, "Test Operations")

        # Create log panel
        self.log_widget = QTextEdit()
        self.log_widget.setReadOnly(True)
        self.log_widget.setLineWrapMode(QTextEdit.NoWrap)
        self.log_widget.setStyleSheet("""
            QTextEdit {
                font-family: monospace;
                background-color: #f8f8f8;
                border: 1px solid #dcdcdc;
            }
        """)
        self.right_tabs.addTab(self.log_widget, "Operation Log")

        # Add tabs to layout
        layout.addWidget(self.right_tabs)

    def create_toolbar(self):
        """Create the application toolbar"""
        self.toolbar = QToolBar("Main Toolbar")
        self.toolbar.setIconSize(QSize(24, 24))
        self.toolbar.setMovable(False)

        # Refresh action
        refresh_action = QAction("Refresh", self)
        refresh_action.triggered.connect(self.refresh_all)
        self.toolbar.addAction(refresh_action)

        self.toolbar.addSeparator()

        # New folder action
        new_folder_action = QAction("New Folder", self)
        new_folder_action.triggered.connect(self.create_new_folder)
        self.toolbar.addAction(new_folder_action)

        # Search action
        search_action = QAction("Search", self)
        search_action.triggered.connect(self.show_search_dialog)
        self.toolbar.addAction(search_action)

        self.addToolBar(self.toolbar)

    def log_message(self, message, error=False):
        """Add a message to the log with timestamp"""
        timestamp = datetime.now().strftime("%H:%M:%S")

        if error:
            self.log_widget.append(f"<span style='color:red'>[ {timestamp} ] ERROR: {message}</span>")
        else:
            self.log_widget.append(f"[ {timestamp} ] {message}")

        # Scroll to bottom
        cursor = self.log_widget.textCursor()
        cursor.movePosition(cursor.End)
        self.log_widget.setTextCursor(cursor)

    def refresh_all(self):
        """Refresh all file views"""
        self.refresh_local_files()
        self.refresh_drive_files()

    def refresh_local_files(self):
        """Refresh the local files list"""
        self.local_files.setRowCount(0)

        # Get current path
        current_path = self.local_path_edit.text()
        if not os.path.isdir(current_path):
            current_path = os.path.expanduser("~")
            self.local_path_edit.setText(current_path)

        # Add parent directory entry
        if current_path != os.path.dirname(current_path):
            row = self.local_files.rowCount()
            self.local_files.insertRow(row)

            name_item = QTableWidgetItem("..")
            name_item.setData(Qt.UserRole, "parent")
            self.local_files.setItem(row, 0, name_item)

            # Empty cells for other columns
            for col in range(1, self.local_files.columnCount()):
                self.local_files.setItem(row, col, QTableWidgetItem(""))

        # List files and directories
        try:
            items = []
            for item in os.listdir(current_path):
                item_path = os.path.join(current_path, item)

                try:
                    stats = os.stat(item_path)
                    is_dir = os.path.isdir(item_path)

                    # Store item info
                    items.append((item, stats, is_dir))
                except Exception:
                    pass

            # Sort: directories first, then by name
            items.sort(key=lambda x: (not x[2], x[0].lower()))

            # Add to table
            for item, stats, is_dir in items:
                row = self.local_files.rowCount()
                self.local_files.insertRow(row)

                # Name column
                name_item = QTableWidgetItem(item)
                name_item.setData(Qt.UserRole, "dir" if is_dir else "file")
                self.local_files.setItem(row, 0, name_item)

                # Size column
                if is_dir:
                    size_text = ""
                else:
                    size_text = self.format_size(stats.st_size)
                self.local_files.setItem(row, 1, QTableWidgetItem(size_text))

                # Date column
                date_modified = datetime.fromtimestamp(stats.st_mtime).strftime("%Y-%m-%d %H:%M")
                self.local_files.setItem(row, 2, QTableWidgetItem(date_modified))

                # Type column
                type_text = "Folder" if is_dir else os.path.splitext(item)[1].upper()[1:] or "File"
                self.local_files.setItem(row, 3, QTableWidgetItem(type_text))

        except Exception as e:
            self.log_message(f"Error listing local files: {str(e)}", True)
            QMessageBox.warning(self, "Error", f"Could not list files: {str(e)}")

    def refresh_drive_files(self, folder_id=None):
        """Refresh the Google Drive files list"""
        if not self.connected:
            return

        self.drive_files.setRowCount(0)

        # Use provided folder ID or current folder
        current_folder_id = folder_id if folder_id is not None else self.current_drive_id
        self.current_drive_id = current_folder_id

        # Update path label
        if current_folder_id == 'root':
            self.drive_path_label.setText("Root")
        else:
            path_text = " / ".join([name for name, _ in self.drive_path_history])
            self.drive_path_label.setText(path_text)

        # Add parent directory if not at root
        if len(self.drive_path_history) > 1:
            row = self.drive_files.rowCount()
            self.drive_files.insertRow(row)

            # Name column
            name_item = QTableWidgetItem("..")
            name_item.setData(Qt.UserRole, self.drive_path_history[-2][1])  # Parent ID
            self.drive_files.setItem(row, 0, name_item)

            # Empty cells for other columns
            for col in range(1, self.drive_files.columnCount()):
                self.drive_files.setItem(row, col, QTableWidgetItem(""))

        # Get files from the current folder
        try:
            files = self.drive_client.list_files(current_folder_id)

            # Separate folders and files
            folders = []
            other_files = []

            for file in files:
                if file.get('mimeType') == 'application/vnd.google-apps.folder':
                    folders.append(file)
                else:
                    other_files.append(file)

            # Sort by name
            folders.sort(key=lambda x: x['name'].lower())
            other_files.sort(key=lambda x: x['name'].lower())

            # Add folders first, then files
            for file in folders + other_files:
                row = self.drive_files.rowCount()
                self.drive_files.insertRow(row)

                # Name column
                name_item = QTableWidgetItem(file.get('name', ''))
                self.drive_files.setItem(row, 0, name_item)

                # Size column
                is_folder = file.get('mimeType') == 'application/vnd.google-apps.folder'
                size_text = "" if is_folder else self.format_size(int(file.get('size', 0)))
                self.drive_files.setItem(row, 1, QTableWidgetItem(size_text))

                # Date column
                date_str = ""
                if 'modifiedTime' in file:
                    try:
                        date_obj = datetime.strptime(file['modifiedTime'], "%Y-%m-%dT%H:%M:%S.%fZ")
                        date_str = date_obj.strftime("%Y-%m-%d %H:%M")
                    except:
                        date_str = file['modifiedTime']
                self.drive_files.setItem(row, 2, QTableWidgetItem(date_str))

                # Type column
                type_text = "Folder" if is_folder else self.get_file_type(file.get('mimeType', ''))
                self.drive_files.setItem(row, 3, QTableWidgetItem(type_text))

                # ID column
                self.drive_files.setItem(row, 4, QTableWidgetItem(file.get('id', '')))

        except Exception as e:
            self.log_message(f"Error listing Drive files: {str(e)}", True)
            QMessageBox.warning(self, "Error", f"Could not list Drive files: {str(e)}")

    def get_file_type(self, mime_type):
        """Get the file type from MIME type"""
        mime_map = {
            'application/vnd.google-apps.document': 'Google Doc',
            'application/vnd.google-apps.spreadsheet': 'Google Sheet',
            'application/vnd.google-apps.presentation': 'Google Slides',
            'application/vnd.google-apps.form': 'Google Form',
            'application/vnd.google-apps.drawing': 'Google Drawing',
            'application/pdf': 'PDF',
            'image/jpeg': 'JPEG',
            'image/png': 'PNG',
            'text/plain': 'Text',
            'text/html': 'HTML',
            'application/zip': 'ZIP',
            'video/mp4': 'MP4',
            'audio/mpeg': 'MP3'
        }

        return mime_map.get(mime_type, mime_type.split('/')[-1].upper())

    def format_size(self, size_bytes):
        """Format file size in a human-readable way"""
        if size_bytes == 0:
            return "0 B"

        size_names = ("B", "KB", "MB", "GB", "TB")
        i = 0
        while size_bytes >= 1024 and i < len(size_names) - 1:
            size_bytes /= 1024
            i += 1

        return f"{size_bytes:.2f} {size_names[i]}"

    def change_local_path(self):
        """Change the current local path"""
        new_path = self.local_path_edit.text()
        if os.path.isdir(new_path):
            self.refresh_local_files()
        else:
            QMessageBox.warning(self, "Invalid Path", "The specified path is not a valid directory.")
            self.local_path_edit.setText(os.path.expanduser("~"))
            self.refresh_local_files()

    def browse_local_folder(self):
        """Open a folder browser dialog"""
        folder = QFileDialog.getExistingDirectory(self, "Select Folder", self.local_path_edit.text())
        if folder:
            self.local_path_edit.setText(folder)
            self.refresh_local_files()

    def local_item_double_clicked(self, index):
        """Handle double-click on a local file/folder"""
        if not index.isValid():
            return

        row = index.row()
        name = self.local_files.item(row, 0).text()
        item_type = self.local_files.item(row, 0).data(Qt.UserRole)

        # If parent directory
        if name == ".." and item_type == "parent":
            parent_dir = os.path.dirname(self.local_path_edit.text())
            self.local_path_edit.setText(parent_dir)
            self.refresh_local_files()
            return

        # If directory, navigate into it
        if item_type == "dir":
            new_path = os.path.join(self.local_path_edit.text(), name)
            self.local_path_edit.setText(new_path)
            self.refresh_local_files()

    def drive_item_double_clicked(self, index):
        """Handle double-click on a Drive file/folder"""
        if not index.isValid():
            return

        row = index.row()
        name = self.drive_files.item(row, 0).text()

        # Check if it's the parent directory entry
        if name == "..":
            if len(self.drive_path_history) > 1:
                self.drive_path_history.pop()  # Remove current folder
                parent_name, parent_id = self.drive_path_history[-1]
                self.refresh_drive_files(parent_id)
            return

        # Get type and ID
        type_str = self.drive_files.item(row, 3).text()
        file_id = self.drive_files.item(row, 4).text()

        # If it's a folder, navigate into it
        if type_str == "Folder":
            # Add to navigation history
            self.drive_path_history.append((name, file_id))
            self.refresh_drive_files(file_id)

    def drive_go_back(self):
        """Go up one level in Drive navigation"""
        if len(self.drive_path_history) > 1:
            self.drive_path_history.pop()  # Remove current folder
            parent_name, parent_id = self.drive_path_history[-1]
            self.refresh_drive_files(parent_id)

    def change_drive(self, index):
        """Switch between My Drive and Shared Drives"""
        drive_id = self.drive_selector.currentData()

        # Reset navigation history
        self.drive_path_history = [(self.drive_selector.currentText(), drive_id)]
        self.current_drive_id = drive_id

        self.refresh_drive_files(drive_id)

    def show_local_context_menu(self, position):
        """Show context menu for local files"""
        # Get selected items
        indexes = self.local_files.selectedIndexes()
        if not indexes:
            return

        # Get unique rows
        rows = set(index.row() for index in indexes)
        if not rows:
            return

        menu = QMenu(self)

        # For multiple files
        if rows:
            upload_action = QAction("Upload to Google Drive", self)
            upload_action.triggered.connect(self.upload_selected_files)
            menu.addAction(upload_action)

            # Add 'Upload Folder' option if a folder is selected
            for row in rows:
                item_type = self.local_files.item(row, 0).data(Qt.UserRole)
                if item_type == "dir":
                    upload_folder_action = QAction("Upload Folder to Google Drive", self)
                    upload_folder_action.triggered.connect(self.upload_selected_folders)
                    menu.addAction(upload_folder_action)
                    break

            menu.addSeparator()

        # For a single file
        if len(rows) == 1:
            row = list(rows)[0]
            name = self.local_files.item(row, 0).text()

            # If not parent directory
            if name != "..":
                rename_action = QAction("Rename", self)
                rename_action.triggered.connect(self.rename_selected)
                menu.addAction(rename_action)

                delete_action = QAction("Delete", self)
                delete_action.triggered.connect(self.delete_selected)
                menu.addAction(delete_action)

        menu.exec_(self.local_files.viewport().mapToGlobal(position))

    def show_drive_context_menu(self, position):
        """Show context menu for Drive files"""
        # Get selected items
        indexes = self.drive_files.selectedIndexes()
        if not indexes:
            return

        # Get unique rows
        rows = set(index.row() for index in indexes)
        if not rows:
            return

        menu = QMenu(self)

        # For multiple files
        if rows:
            download_action = QAction("Download", self)
            download_action.triggered.connect(self.download_selected_files)
            menu.addAction(download_action)

            # Add 'Download Folder' option if a folder is selected
            for row in rows:
                type_str = self.drive_files.item(row, 3).text()
                if type_str == "Folder":
                    download_folder_action = QAction("Download Folder", self)
                    download_folder_action.triggered.connect(self.download_selected_folders)
                    menu.addAction(download_folder_action)
                    break

            menu.addSeparator()

        # For a single file
        if len(rows) == 1:
            row = list(rows)[0]
            name = self.drive_files.item(row, 0).text()

            # If not parent directory
            if name != "..":
                file_type = self.drive_files.item(row, 3).text()

                rename_action = QAction("Rename", self)
                rename_action.triggered.connect(self.rename_selected)
                menu.addAction(rename_action)

                # For folders - create subfolder option
                if file_type == "Folder":
                    create_subfolder_action = QAction("Create Subfolder", self)
                    create_subfolder_action.triggered.connect(self.create_subfolder_selected)
                    menu.addAction(create_subfolder_action)

                delete_action = QAction("Move to Trash", self)
                delete_action.triggered.connect(self.delete_selected)
                menu.addAction(delete_action)

                perm_delete_action = QAction("Delete Permanently", self)
                perm_delete_action.triggered.connect(self.permanently_delete_selected)
                menu.addAction(perm_delete_action)

        menu.exec_(self.drive_files.viewport().mapToGlobal(position))

    def upload_selected_files(self):
        """Upload selected local files to Drive"""
        # Get selected files
        rows = []
        for index in self.local_files.selectedIndexes():
            rows.append(index.row())

        # Get unique rows
        rows = list(set(rows))
        if not rows:
            return

        # Get files to upload
        files_to_upload = []
        for row in rows:
            name = self.local_files.item(row, 0).text()
            item_type = self.local_files.item(row, 0).data(Qt.UserRole)

            # Skip parent directory and folders
            if name == ".." or item_type == "dir":
                continue

            # Add file path
            file_path = os.path.join(self.local_path_edit.text(), name)
            files_to_upload.append((name, file_path))

        if not files_to_upload:
            return

        # Destination folder
        destination_id = self.current_drive_id

        # Upload each file
        for name, file_path in files_to_upload:
            # Create upload thread
            self.upload_thread = UploadThread(
                self.drive_client,
                file_path,
                destination_id
            )

            # Connect signals
            self.upload_thread.progress_signal.connect(self.progress_bar.setValue)
            self.upload_thread.completed_signal.connect(
                lambda file_id, metrics: self.on_upload_completed(file_id, metrics)
            )
            self.upload_thread.error_signal.connect(
                lambda error: self.on_upload_error(error)
            )

            # Start thread
            self.upload_thread.start()

            # Show progress bar and status
            self.progress_bar.setValue(0)
            self.progress_bar.setVisible(True)
            self.status_bar.showMessage(f"Uploading {name}...")

            # Log the operation
            self.log_message(f"Started uploading {name} to Drive")

    def upload_selected_folders(self):
        """Upload selected local folders to Drive"""
        # Get selected folders
        rows = []
        for index in self.local_files.selectedIndexes():
            rows.append(index.row())

        # Get unique rows
        rows = list(set(rows))
        if not rows:
            return

        # Get folders to upload
        folders_to_upload = []
        for row in rows:
            name = self.local_files.item(row, 0).text()
            item_type = self.local_files.item(row, 0).data(Qt.UserRole)

            # Skip parent directory and non-folders
            if name == ".." or item_type != "dir":
                continue

            # Add folder path
            folder_path = os.path.join(self.local_path_edit.text(), name)
            folders_to_upload.append((name, folder_path))

        if not folders_to_upload:
            return

        # Destination folder
        destination_id = self.current_drive_id

        # Upload each folder
        for name, folder_path in folders_to_upload:
            # Create folder upload thread
            self.folder_upload_thread = FolderUploadThread(
                self.drive_client,
                folder_path,
                destination_id
            )

            # Connect signals
            self.folder_upload_thread.progress_signal.connect(self.progress_bar.setValue)
            self.folder_upload_thread.status_signal.connect(
                lambda msg: self.status_bar.showMessage(msg)
            )
            self.folder_upload_thread.completed_signal.connect(
                lambda folder_id, metrics: self.on_folder_upload_completed(folder_id, metrics, name)
            )
            self.folder_upload_thread.error_signal.connect(
                lambda error: self.on_upload_error(error)
            )

            # Start thread
            self.folder_upload_thread.start()

            # Show progress bar and status
            self.progress_bar.setValue(0)
            self.progress_bar.setVisible(True)
            self.status_bar.showMessage(f"Preparing to upload folder: {name}...")

            # Log the operation
            self.log_message(f"Started uploading folder {name} to Drive")

    def download_selected_files(self):
        """Download selected Drive files"""
        # Get selected files
        rows = []
        for index in self.drive_files.selectedIndexes():
            rows.append(index.row())

        # Get unique rows
        rows = list(set(rows))
        if not rows:
            return

        # Get files to download
        files_to_download = []
        for row in rows:
            name = self.drive_files.item(row, 0).text()
            file_type = self.drive_files.item(row, 3).text()
            file_id = self.drive_files.item(row, 4).text()

            # Skip parent directory and folders
            if name == ".." or file_type == "Folder":
                continue

            # Add file info
            files_to_download.append((name, file_id))

        if not files_to_download:
            return

        # Ask for destination directory
        destination_dir = QFileDialog.getExistingDirectory(
            self, "Choose Destination Directory", self.local_path_edit.text())

        if not destination_dir:
            return

        # Download each file
        for name, file_id in files_to_download:
            # Create download thread
            self.download_thread = DownloadThread(
                self.drive_client,
                file_id,
                name,
                destination_dir
            )

            # Connect signals
            self.download_thread.progress_signal.connect(self.progress_bar.setValue)
            self.download_thread.completed_signal.connect(
                lambda file_path, metrics: self.on_download_completed(file_path, metrics)
            )
            self.download_thread.error_signal.connect(
                lambda error: self.on_download_error(error)
            )

            # Start thread
            self.download_thread.start()

            # Show progress bar and status
            self.progress_bar.setValue(0)
            self.progress_bar.setVisible(True)
            self.status_bar.showMessage(f"Downloading {name}...")

            # Log the operation
            self.log_message(f"Started downloading {name} from Drive")

    def download_selected_folders(self):
        """Download selected Drive folders"""
        # Get selected folders
        rows = []
        for index in self.drive_files.selectedIndexes():
            rows.append(index.row())

        # Get unique rows
        rows = list(set(rows))
        if not rows:
            return

        # Get folders to download
        folders_to_download = []
        for row in rows:
            name = self.drive_files.item(row, 0).text()
            file_type = self.drive_files.item(row, 3).text()
            file_id = self.drive_files.item(row, 4).text()

            # Skip parent directory and non-folders
            if name == ".." or file_type != "Folder":
                continue

            # Add folder info
            folders_to_download.append((name, file_id))

        if not folders_to_download:
            return

        # Ask for destination directory
        destination_dir = QFileDialog.getExistingDirectory(
            self, "Choose Destination Directory", self.local_path_edit.text())

        if not destination_dir:
            return

        # Download each folder
        for name, folder_id in folders_to_download:
            # Create folder download thread
            self.folder_download_thread = FolderDownloadThread(
                self.drive_client,
                folder_id,
                name,
                destination_dir
            )

            # Connect signals
            self.folder_download_thread.progress_signal.connect(self.progress_bar.setValue)
            self.folder_download_thread.status_signal.connect(
                lambda msg: self.status_bar.showMessage(msg)
            )
            self.folder_download_thread.completed_signal.connect(
                lambda folder_path, metrics: self.on_folder_download_completed(folder_path, metrics, name)
            )
            self.folder_download_thread.error_signal.connect(
                lambda error: self.on_download_error(error)
            )

            # Start thread
            self.folder_download_thread.start()

            # Show progress bar and status
            self.progress_bar.setValue(0)
            self.progress_bar.setVisible(True)
            self.status_bar.showMessage(f"Preparing to download folder: {name}...")

            # Log the operation
            self.log_message(f"Started downloading folder {name} from Drive")

    def on_upload_completed(self, file_id, metrics):
        """Handle upload completion"""
        self.progress_bar.setVisible(False)
        self.status_bar.showMessage("Upload complete", 3000)
        self.refresh_drive_files()

        # Update metrics
        self.metrics_panel.update_metrics('upload', metrics)

        # Log completion
        duration = metrics.get('duration', 0)
        speed = metrics.get('speed', 0)
        self.log_message(f"Upload completed in {duration:.2f} seconds ({speed:.2f} MB/s)")

    def on_folder_upload_completed(self, folder_id, metrics, folder_name):
        """Handle folder upload completion"""
        self.progress_bar.setVisible(False)
        self.status_bar.showMessage(f"Folder upload complete: {folder_name}", 3000)
        self.refresh_drive_files()

        # Update metrics
        self.metrics_panel.update_metrics('upload', metrics)

        # Log completion
        duration = metrics.get('duration', 0)
        speed = metrics.get('speed', 0)
        total_bytes = metrics.get('total_bytes', 0)
        self.log_message(
            f"Folder '{folder_name}' upload completed in {duration:.2f} seconds, {speed:.2f} MB/s, {self.format_size(total_bytes)}")

    def on_upload_error(self, error_msg):
        """Handle upload error"""
        self.progress_bar.setVisible(False)
        self.status_bar.showMessage(f"Upload error: {error_msg}", 5000)

        # Log error
        self.log_message(f"Upload error: {error_msg}", True)

    def on_download_completed(self, file_path, metrics):
        """Handle download completion"""
        self.progress_bar.setVisible(False)
        self.status_bar.showMessage(f"Download complete: {file_path}", 3000)

        # Update metrics
        self.metrics_panel.update_metrics('download', metrics)

        # If destination is current local folder, refresh
        if os.path.dirname(file_path) == self.local_path_edit.text():
            self.refresh_local_files()

        # Log completion
        duration = metrics.get('duration', 0)
        speed = metrics.get('speed', 0)
        self.log_message(f"Download completed in {duration:.2f} seconds ({speed:.2f} MB/s)")

    def on_folder_download_completed(self, folder_path, metrics, folder_name):
        """Handle folder download completion"""
        self.progress_bar.setVisible(False)
        self.status_bar.showMessage(f"Folder download complete: {folder_path}", 3000)

        # Update metrics
        self.metrics_panel.update_metrics('download', metrics)

        # If destination is current local folder, refresh
        if os.path.dirname(folder_path) == self.local_path_edit.text():
            self.refresh_local_files()

        # Log completion
        duration = metrics.get('duration', 0)
        speed = metrics.get('speed', 0)
        total_bytes = metrics.get('total_bytes', 0)
        self.log_message(
            f"Folder '{folder_name}' download completed in {duration:.2f} seconds, {speed:.2f} MB/s, {self.format_size(total_bytes)}")

    def on_download_error(self, error_msg):
        """Handle download error"""
        self.progress_bar.setVisible(False)
        self.status_bar.showMessage(f"Download error: {error_msg}", 5000)

        # Log error
        self.log_message(f"Download error: {error_msg}", True)

    def create_new_folder(self):
        """Create a new folder in the active panel"""
        active_tab = self.explorer_tabs.currentWidget()

        if active_tab == self.local_tab:
            # Create local folder
            folder_name, ok = QInputDialog.getText(self, "New Folder",
                                                   "Folder name:")

            if ok and folder_name:
                try:
                    new_path = os.path.join(self.local_path_edit.text(), folder_name)
                    os.makedirs(new_path, exist_ok=True)
                    self.refresh_local_files()
                    self.status_bar.showMessage(f"Folder '{folder_name}' created", 3000)
                    self.log_message(f"Created local folder: {folder_name}")
                except Exception as e:
                    error_msg = f"Could not create folder: {str(e)}"
                    QMessageBox.warning(self, "Error", error_msg)
                    self.log_message(error_msg, True)

        elif active_tab == self.drive_tab:
            # Create Drive folder
            folder_name, ok = QInputDialog.getText(self, "New Drive Folder",
                                                   "Folder name:")

            if ok and folder_name:
                try:
                    parent_id = self.current_drive_id
                    folder_id = self.drive_client.create_folder(folder_name, parent_id)
                    self.refresh_drive_files()
                    self.status_bar.showMessage(f"Drive folder '{folder_name}' created", 3000)
                    self.log_message(f"Created Drive folder: {folder_name}")
                except Exception as e:
                    error_msg = f"Could not create folder: {str(e)}"
                    QMessageBox.warning(self, "Error", error_msg)
                    self.log_message(error_msg, True)

    def create_subfolder_selected(self):
        """Create a subfolder in the selected Drive folder"""
        # Get selected folder
        indexes = self.drive_files.selectedIndexes()
        if not indexes:
            return

        row = indexes[0].row()
        folder_name = self.drive_files.item(row, 0).text()
        folder_id = self.drive_files.item(row, 4).text()
        folder_type = self.drive_files.item(row, 3).text()

        if folder_name == ".." or folder_type != "Folder":
            return

        # Ask for subfolder name
        subfolder_name, ok = QInputDialog.getText(self, f"New subfolder in '{folder_name}'",
                                                  "Subfolder name:")

        if ok and subfolder_name:
            try:
                subfolder_id = self.drive_client.create_folder(subfolder_name, folder_id)
                self.refresh_drive_files()
                self.status_bar.showMessage(f"Subfolder '{subfolder_name}' created", 3000)
                self.log_message(f"Created subfolder '{subfolder_name}' in '{folder_name}'")
            except Exception as e:
                error_msg = f"Could not create subfolder: {str(e)}"
                QMessageBox.warning(self, "Error", error_msg)
                self.log_message(error_msg, True)

    def rename_selected(self):
        """Rename the selected item (local or Drive)"""
        active_tab = self.explorer_tabs.currentWidget()

        if active_tab == self.local_tab:
            # Rename local file/folder
            indexes = self.local_files.selectedIndexes()
            if not indexes:
                return

            row = indexes[0].row()
            old_name = self.local_files.item(row, 0).text()

            if old_name == "..":
                return

            new_name, ok = QInputDialog.getText(self, "Rename",
                                                "New name:", text=old_name)

            if ok and new_name and new_name != old_name:
                old_path = os.path.join(self.local_path_edit.text(), old_name)
                new_path = os.path.join(self.local_path_edit.text(), new_name)

                try:
                    os.rename(old_path, new_path)
                    self.refresh_local_files()
                    self.status_bar.showMessage(f"'{old_name}' renamed to '{new_name}'", 3000)
                    self.log_message(f"Renamed local item '{old_name}' to '{new_name}'")
                except Exception as e:
                    error_msg = f"Could not rename: {str(e)}"
                    QMessageBox.warning(self, "Error", error_msg)
                    self.log_message(error_msg, True)

        elif active_tab == self.drive_tab:
            # Rename Drive file/folder
            indexes = self.drive_files.selectedIndexes()
            if not indexes:
                return

            row = indexes[0].row()
            old_name = self.drive_files.item(row, 0).text()
            file_id = self.drive_files.item(row, 4).text()

            if old_name == "..":
                return

            new_name, ok = QInputDialog.getText(self, "Rename",
                                                "New name:", text=old_name)

            if ok and new_name and new_name != old_name:
                try:
                    self.drive_client.rename_item(file_id, new_name)
                    self.refresh_drive_files()
                    self.status_bar.showMessage(f"'{old_name}' renamed to '{new_name}'", 3000)
                    self.log_message(f"Renamed Drive item '{old_name}' to '{new_name}'")
                except Exception as e:
                    error_msg = f"Could not rename: {str(e)}"
                    QMessageBox.warning(self, "Error", error_msg)
                    self.log_message(error_msg, True)

    def delete_selected(self):
        """Delete the selected item(s)"""
        active_tab = self.explorer_tabs.currentWidget()

        if active_tab == self.local_tab:
            # Delete local file/folder
            rows = []
            for index in self.local_files.selectedIndexes():
                rows.append(index.row())

            # Get unique rows
            rows = list(set(rows))
            if not rows:
                return

            # Get items to delete
            items_to_delete = []
            for row in rows:
                name = self.local_files.item(row, 0).text()
                if name != "..":
                    items_to_delete.append(name)

            if not items_to_delete:
                return

            # Confirmation
            if len(items_to_delete) == 1:
                message = f"Are you sure you want to delete '{items_to_delete[0]}'?"
            else:
                message = f"Are you sure you want to delete these {len(items_to_delete)} items?"

            confirm = QMessageBox.question(self, "Confirm Delete", message,
                                           QMessageBox.Yes | QMessageBox.No)

            if confirm == QMessageBox.Yes:
                errors = []
                for name in items_to_delete:
                    path = os.path.join(self.local_path_edit.text(), name)
                    try:
                        if os.path.isdir(path):
                            import shutil
                            shutil.rmtree(path)
                        else:
                            os.remove(path)
                        self.log_message(f"Deleted local item: {name}")
                    except Exception as e:
                        errors.append(f"Could not delete '{name}': {str(e)}")
                        self.log_message(f"Error deleting local item '{name}': {str(e)}", True)

                self.refresh_local_files()

                if errors:
                    QMessageBox.warning(self, "Delete Errors", "\n".join(errors))
                else:
                    self.status_bar.showMessage(f"Deleted {len(items_to_delete)} item(s)", 3000)

        elif active_tab == self.drive_tab:
            # Delete Drive file/folder
            rows = []
            for index in self.drive_files.selectedIndexes():
                rows.append(index.row())

            # Get unique rows
            rows = list(set(rows))
            if not rows:
                return

            # Get items to delete
            items_to_delete = []
            for row in rows:
                name = self.drive_files.item(row, 0).text()
                file_id = self.drive_files.item(row, 4).text()
                if name != "..":
                    items_to_delete.append((name, file_id))

            if not items_to_delete:
                return

            # Confirmation
            if len(items_to_delete) == 1:
                message = f"Are you sure you want to move '{items_to_delete[0][0]}' to trash?"
            else:
                message = f"Are you sure you want to move these {len(items_to_delete)} items to trash?"

            confirm = QMessageBox.question(self, "Confirm Delete", message,
                                           QMessageBox.Yes | QMessageBox.No)

            if confirm == QMessageBox.Yes:
                errors = []
                for name, file_id in items_to_delete:
                    try:
                        self.drive_client.delete_item(file_id)
                        self.log_message(f"Moved to trash: {name}")
                    except Exception as e:
                        errors.append(f"Could not delete '{name}': {str(e)}")
                        self.log_message(f"Error moving '{name}' to trash: {str(e)}", True)

                self.refresh_drive_files()

                if errors:
                    QMessageBox.warning(self, "Delete Errors", "\n".join(errors))
                else:
                    self.status_bar.showMessage(f"Moved {len(items_to_delete)} item(s) to trash", 3000)
"""
Queue Workers - Process files from the unified upload queue
Version améliorée avec détection de doublons robuste
"""

import time
import threading
from typing import Optional, List
from PyQt5.QtCore import QThread, pyqtSignal, QMutex, QMutexLocker

from models.upload_queue import UploadQueue, QueuedFile, FileStatus
from core.google_drive_client import GoogleDriveClient
from utils.google_drive_utils import already_exists_in_folder, get_duplicate_tracker


class QueueWorker(QThread):
    """
    Worker thread that processes files from the upload queue.
    Multiple workers can run simultaneously with controlled parallelism.
    Version améliorée avec détection de doublons robuste.
    """

    # Signals
    worker_started = pyqtSignal(str)  # worker_id
    worker_stopped = pyqtSignal(str)  # worker_id
    file_started = pyqtSignal(str, str)  # worker_id, file_unique_id
    file_progress = pyqtSignal(str, str, int, int, float)  # worker_id, file_unique_id, progress, bytes_transferred, speed
    file_completed = pyqtSignal(str, str, str)  # worker_id, file_unique_id, uploaded_file_id
    file_failed = pyqtSignal(str, str, str)  # worker_id, file_unique_id, error_message
    file_skipped = pyqtSignal(str, str, str)  # worker_id, file_unique_id, reason

    def __init__(self, worker_id: str, upload_queue: UploadQueue,
                 max_parallel_files: int = 10):
        """
        Initialize queue worker

        Args:
            worker_id: Unique identifier for this worker
            upload_queue: The upload queue to process
            max_parallel_files: Maximum files to process simultaneously
        """
        super().__init__()

        self.worker_id = worker_id
        self.upload_queue = upload_queue
        self.max_parallel_files = max_parallel_files

        # Control flags
        self._should_stop = False
        self._is_paused = False
        self._stop_mutex = QMutex()

        # Active file tracking
        self._active_files = set()  # Set of unique_ids being processed
        self._active_files_lock = threading.RLock()

        # Google Drive clients pool (one per parallel upload)
        self._drive_clients = []
        self._client_lock = threading.RLock()

        # Performance tracking
        self._files_processed = 0
        self._total_bytes_transferred = 0
        self._start_time = None

        # Duplicate tracker
        self._duplicate_tracker = get_duplicate_tracker()

    def run(self):
        """Main worker loop"""
        self._should_stop = False
        self._start_time = time.time()

        print(f"🚀 Worker {self.worker_id} started (max {self.max_parallel_files} parallel files)")
        self.worker_started.emit(self.worker_id)

        try:
            # Initialize drive clients pool
            self._initialize_drive_clients()

            # Main processing loop
            while not self._should_stop:
                if self._is_paused:
                    time.sleep(0.5)
                    continue

                # Check if we can process more files
                with self._active_files_lock:
                    active_count = len(self._active_files)

                if active_count >= self.max_parallel_files:
                    # At capacity, wait a bit
                    time.sleep(0.1)
                    continue

                # Get next file from queue
                next_file = self.upload_queue.get_next_pending_file()
                if next_file is None:
                    # No pending files, wait a bit
                    time.sleep(0.5)
                    continue

                # Process the file in a separate thread
                threading.Thread(
                    target=self._process_file,
                    args=(next_file,),
                    daemon=True
                ).start()

                # Small delay to prevent tight loop
                time.sleep(0.01)

        except Exception as e:
            print(f"❌ Worker {self.worker_id} error: {e}")
        finally:
            self._cleanup_drive_clients()
            print(f"🛑 Worker {self.worker_id} stopped. Processed {self._files_processed} files")
            self.worker_stopped.emit(self.worker_id)

    def _initialize_drive_clients(self):
        """Initialize pool of Google Drive clients"""
        with self._client_lock:
            self._drive_clients = []
            for i in range(self.max_parallel_files):
                try:
                    client = GoogleDriveClient()
                    self._drive_clients.append(client)
                except Exception as e:
                    print(f"⚠️ Failed to create drive client {i}: {e}")

    def _cleanup_drive_clients(self):
        """Clean up Google Drive clients"""
        with self._client_lock:
            for client in self._drive_clients:
                try:
                    if hasattr(client, 'close'):
                        client.close()
                except:
                    pass
            self._drive_clients = []

    def _get_available_drive_client(self) -> Optional[GoogleDriveClient]:
        """Get an available drive client from the pool"""
        with self._client_lock:
            if self._drive_clients:
                return self._drive_clients.pop()
            else:
                # Create new client if pool is empty
                try:
                    return GoogleDriveClient()
                except Exception as e:
                    print(f"⚠️ Failed to create new drive client: {e}")
                    return None

    def _return_drive_client(self, client: GoogleDriveClient):
        """Return a drive client to the pool"""
        with self._client_lock:
            if len(self._drive_clients) < self.max_parallel_files:
                self._drive_clients.append(client)
            else:
                # Pool is full, close this client
                try:
                    if hasattr(client, 'close'):
                        client.close()
                except:
                    pass

    def _process_file(self, file: QueuedFile):
        """
        Process a single file upload with improved duplicate detection

        Args:
            file: File to upload
        """
        unique_id = file.unique_id

        # Add to active files
        with self._active_files_lock:
            if unique_id in self._active_files:
                # Already being processed
                return
            self._active_files.add(unique_id)

        try:
            # Get drive client
            drive_client = self._get_available_drive_client()
            if drive_client is None:
                self._fail_file(file, "No Google Drive client available")
                return

            # ÉTAPE 1: Vérifier d'abord si le fichier existe sur Google Drive
            print(f"🔍 {self.worker_id}: Checking if {file.file_name} already exists on Drive...")
            if already_exists_in_folder(drive_client, file.destination_folder_id, file.file_name):
                self.upload_queue.skip_file(unique_id, "File already exists on Drive")
                self.file_skipped.emit(self.worker_id, unique_id, "File already exists on Drive")
                self._return_drive_client(drive_client)
                print(f"⏭️ {self.worker_id}: Skipped {file.file_name} - exists on Drive")
                return

            # ÉTAPE 2: Claim du fichier dans le tracker global (pour éviter la concurrence)
            if not self._duplicate_tracker.claim_file(
                file.destination_folder_id,
                file.file_name,
                self.worker_id
            ):
                # Fichier déjà en cours d'upload ou uploadé dans cette session
                reason = "File already being uploaded or uploaded by another worker in this session"
                self.upload_queue.skip_file(unique_id, reason)
                self.file_skipped.emit(self.worker_id, unique_id, reason)
                self._return_drive_client(drive_client)
                print(f"⏭️ {self.worker_id}: Skipped {file.file_name} - already claimed")
                return

            # ÉTAPE 3: Mark file as started
            file.start_upload(self.worker_id)
            self.upload_queue.update_file_progress(unique_id, 0, 0, 0)
            self.file_started.emit(self.worker_id, unique_id)
            print(f"🔄 {self.worker_id}: Processing {file.file_name}")

            # ÉTAPE 4: Perform the upload
            start_time = time.time()
            last_progress_time = start_time

            def progress_callback(bytes_transferred: int, total_bytes: int):
                """Handle upload progress"""
                if self._should_stop:
                    return False  # Cancel upload

                current_time = time.time()

                # Calculate progress
                progress = int((bytes_transferred / total_bytes) * 100) if total_bytes > 0 else 0

                # Calculate speed (update every 0.5 seconds)
                speed = 0
                if current_time - last_progress_time >= 0.5:
                    time_diff = current_time - start_time
                    if time_diff > 0:
                        speed = bytes_transferred / time_diff

                    # Update file and emit signal
                    self.upload_queue.update_file_progress(unique_id, progress, bytes_transferred, speed)
                    self.file_progress.emit(self.worker_id, unique_id, progress, bytes_transferred, speed)

                return True  # Continue upload

            # Upload the file avec retry logic
            max_retries = 3
            retry_count = 0
            upload_successful = False

            while retry_count <= max_retries and not upload_successful:
                try:
                    uploaded_file_id = drive_client.upload_file_with_progress(
                        file.file_path,
                        file.destination_folder_id,
                        progress_callback=progress_callback,
                        is_shared_drive=False  # TODO: Get from settings
                    )

                    # Upload successful
                    self._duplicate_tracker.mark_uploaded(
                        file.destination_folder_id,
                        file.file_name,
                        uploaded_file_id,
                        self.worker_id
                    )

                    self.upload_queue.complete_file(unique_id, uploaded_file_id)
                    self.file_completed.emit(self.worker_id, unique_id, uploaded_file_id)
                    self._files_processed += 1
                    self._total_bytes_transferred += file.file_size
                    upload_successful = True
                    print(f"✅ {self.worker_id}: Completed {file.file_name}")

                except Exception as upload_error:
                    error_str = str(upload_error).lower()

                    # Check if it's a rate limit error
                    if ("403" in error_str and ("rate" in error_str or "limit" in error_str or "quota" in error_str)) or \
                       ("userratelimitexceeded" in error_str):

                        retry_count += 1
                        if retry_count <= max_retries:
                            # Exponential backoff: 2^retry_count seconds
                            backoff_time = 2 ** retry_count
                            print(f"⏳ Rate limit hit for {file.file_name}, retrying in {backoff_time}s (attempt {retry_count}/{max_retries})")
                            time.sleep(backoff_time)
                            continue

                    # Either not a rate limit error, or max retries exceeded
                    error_msg = str(upload_error)
                    if retry_count > 0:
                        error_msg = f"Upload error after {retry_count} retries: {error_msg}"

                    # Libérer le claim en cas d'échec
                    self._duplicate_tracker.release_file(
                        file.destination_folder_id,
                        file.file_name,
                        self.worker_id
                    )

                    self.upload_queue.fail_file(unique_id, error_msg)
                    self.file_failed.emit(self.worker_id, unique_id, error_msg)
                    print(f"❌ {self.worker_id}: Failed {file.file_name} - {error_msg}")
                    break  # Exit retry loop

            # Return client to pool
            self._return_drive_client(drive_client)

        except Exception as e:
            # General processing error - libérer le claim
            self._duplicate_tracker.release_file(
                file.destination_folder_id,
                file.file_name,
                self.worker_id
            )
            self._fail_file(file, f"Processing error: {str(e)}")

        finally:
            # Remove from active files
            with self._active_files_lock:
                self._active_files.discard(unique_id)

    def _fail_file(self, file: QueuedFile, error_message: str):
        """Helper to mark file as failed"""
        unique_id = file.unique_id
        self.upload_queue.fail_file(unique_id, error_message)
        self.file_failed.emit(self.worker_id, unique_id, error_message)

    def stop(self):
        """Stop the worker thread"""
        with QMutexLocker(self._stop_mutex):
            self._should_stop = True

        # Wait for completion
        if self.isRunning():
            self.wait(5000)  # Wait up to 5 seconds

    def pause(self):
        """Pause the worker"""
        self._is_paused = True

    def resume(self):
        """Resume the worker"""
        self._is_paused = False

    def is_active(self) -> bool:
        """Check if worker is actively processing files"""
        with self._active_files_lock:
            return len(self._active_files) > 0

    def get_active_files_count(self) -> int:
        """Get number of files currently being processed"""
        with self._active_files_lock:
            return len(self._active_files)

    def get_statistics(self) -> dict:
        """Get worker statistics"""
        elapsed_time = time.time() - self._start_time if self._start_time else 0

        return {
            'worker_id': self.worker_id,
            'files_processed': self._files_processed,
            'bytes_transferred': self._total_bytes_transferred,
            'elapsed_time': elapsed_time,
            'active_files': self.get_active_files_count(),
            'is_running': self.isRunning(),
            'is_paused': self._is_paused
        }


class WorkerManager(QThread):
    """
    Manages multiple queue workers and provides unified control
    """

    # Signals
    worker_manager_started = pyqtSignal()
    worker_manager_stopped = pyqtSignal()
    all_workers_idle = pyqtSignal()  # When all workers have no active files

    def __init__(self, upload_queue: UploadQueue, num_workers: int = 3,
                 files_per_worker: int = 10):
        """
        Initialize worker manager

        Args:
            upload_queue: The upload queue to process
            num_workers: Number of worker threads to create
            files_per_worker: Maximum files per worker
        """
        super().__init__()

        self.upload_queue = upload_queue
        self.num_workers = num_workers
        self.files_per_worker = files_per_worker

        # Workers
        self.workers: List[QueueWorker] = []
        self._should_stop = False

        # Statistics
        self._start_time = None

    def start_workers(self):
        """Start all worker threads"""
        if self.workers:
            self.stop_workers()  # Stop existing workers first

        # Clear duplicate tracking at the start of a new session
        from utils.google_drive_utils import clear_duplicate_tracking
        clear_duplicate_tracking()

        self._should_stop = False
        self._start_time = time.time()

        print(f"🚀 Starting {self.num_workers} workers with {self.files_per_worker} files each")

        # Create and start workers
        for i in range(self.num_workers):
            worker_id = f"worker_{i+1}"
            worker = QueueWorker(
                worker_id=worker_id,
                upload_queue=self.upload_queue,
                max_parallel_files=self.files_per_worker
            )

            # Connect worker signals
            worker.worker_started.connect(self._on_worker_started)
            worker.worker_stopped.connect(self._on_worker_stopped)
            worker.file_started.connect(self._on_file_started)
            worker.file_progress.connect(self._on_file_progress)
            worker.file_completed.connect(self._on_file_completed)
            worker.file_failed.connect(self._on_file_failed)
            worker.file_skipped.connect(self._on_file_skipped)

            self.workers.append(worker)
            worker.start()

        self.worker_manager_started.emit()

        # Start monitoring thread
        self.start()

    def stop_workers(self):
        """Stop all worker threads"""
        self._should_stop = True

        print(f"🛑 Stopping {len(self.workers)} workers...")

        # Stop all workers
        for worker in self.workers:
            worker.stop()

        # Clear workers list
        self.workers = []

        # Print duplicate tracking stats
        from utils.google_drive_utils import get_duplicate_stats
        stats = get_duplicate_stats()
        print(f"📊 Duplicate tracking stats: {stats['uploaded_files']} uploaded, {stats['uploading_files']} in progress")

        self.worker_manager_stopped.emit()

    def pause_workers(self):
        """Pause all workers"""
        for worker in self.workers:
            worker.pause()

    def resume_workers(self):
        """Resume all workers"""
        for worker in self.workers:
            worker.resume()

    def run(self):
        """Monitor workers and emit idle signal"""
        while not self._should_stop:
            time.sleep(2)  # Check every 2 seconds

            # Check if all workers are idle
            all_idle = True
            for worker in self.workers:
                if worker.is_active():
                    all_idle = False
                    break

            if all_idle and not self.upload_queue.has_pending_files():
                self.all_workers_idle.emit()

            # If no more files to process, we can stop
            if (all_idle and not self.upload_queue.has_pending_files() and
                self.upload_queue.get_pending_count() == 0):
                print("🎉 All uploads completed - workers going idle")
                time.sleep(5)  # Wait a bit more before stopping

    def get_overall_statistics(self) -> dict:
        """Get combined statistics from all workers"""
        total_files = 0
        total_bytes = 0
        total_active = 0
        running_workers = 0

        for worker in self.workers:
            stats = worker.get_statistics()
            total_files += stats['files_processed']
            total_bytes += stats['bytes_transferred']
            total_active += stats['active_files']
            if stats['is_running']:
                running_workers += 1

        elapsed_time = time.time() - self._start_time if self._start_time else 0

        return {
            'total_workers': len(self.workers),
            'running_workers': running_workers,
            'total_files_processed': total_files,
            'total_bytes_transferred': total_bytes,
            'total_active_files': total_active,
            'elapsed_time': elapsed_time,
            'average_speed': total_bytes / elapsed_time if elapsed_time > 0 else 0
        }

    # Signal handlers for logging/debugging
    def _on_worker_started(self, worker_id: str):
        print(f"✅ Worker {worker_id} started")

    def _on_worker_stopped(self, worker_id: str):
        print(f"🛑 Worker {worker_id} stopped")

    def _on_file_started(self, worker_id: str, file_unique_id: str):
        # Moins verbose pour éviter le spam
        pass
    
    def _on_file_progress(self, worker_id: str, file_unique_id: str, 
                         progress: int, bytes_transferred: int, speed: float):
        # Too verbose for normal logging
        pass
    
    def _on_file_completed(self, worker_id: str, file_unique_id: str, uploaded_file_id: str):
        print(f"✅ {worker_id}: Completed {file_unique_id}")
    
    def _on_file_failed(self, worker_id: str, file_unique_id: str, error_message: str):
        print(f"❌ {worker_id}: Failed {file_unique_id} - {error_message}")
    
    def _on_file_skipped(self, worker_id: str, file_unique_id: str, reason: str):
        print(f"⏭️ {worker_id}: Skipped {file_unique_id} - {reason}")
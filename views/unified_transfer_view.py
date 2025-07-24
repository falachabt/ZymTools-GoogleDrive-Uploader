"""
New Transfer View for Unified Upload System
Displays queue status, files, and folder statistics
"""

import os
from typing import Dict, List, Optional
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTreeView, QPushButton, QLabel,
    QProgressBar, QSplitter, QGroupBox, QTabWidget, QTableWidget, 
    QTableWidgetItem, QHeaderView, QAbstractItemView, QMenu, QAction
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QModelIndex
from PyQt5.QtGui import QStandardItemModel, QStandardItem, QFont

from models.upload_queue import UploadQueue, QueuedFile, FileStatus, FolderInfo
from models.unified_upload_manager import UnifiedUploadManager
from utils.helpers import format_file_size


class UnifiedTransferView(QWidget):
    """
    Transfer view for the new unified upload system.
    Shows queue status, folder progress, and individual files.
    """
    
    # Signals
    retry_file_requested = pyqtSignal(str)  # file_unique_id
    retry_all_requested = pyqtSignal()
    clear_completed_requested = pyqtSignal()
    pause_requested = pyqtSignal()
    resume_requested = pyqtSignal()
    
    def __init__(self, upload_manager: UnifiedUploadManager):
        """
        Initialize transfer view
        
        Args:
            upload_manager: The unified upload manager (can be None if connection failed)
        """
        super().__init__()
        
        # Handle case where upload_manager is None
        self.upload_manager = upload_manager
        self.upload_queue = None
        
        if upload_manager and hasattr(upload_manager, 'upload_queue'):
            self.upload_queue = upload_manager.upload_queue
        
        # Update timers with safety checks
        self._update_timer = QTimer()
        self._update_timer.timeout.connect(self._safe_update_displays)
        self._update_timer.start(1000)  # Update every second
        
        # Data tracking
        self._last_file_count = 0
        self._last_stats = {}
        
        try:
            self._setup_ui()
            self._connect_signals()
            self._safe_update_displays()
        except Exception as e:
            print(f"❌ Error initializing UnifiedTransferView: {e}")
            import traceback
            traceback.print_exc()
    
    def set_upload_manager(self, upload_manager: UnifiedUploadManager):
        """
        Set or update the upload manager for this view
        
        Args:
            upload_manager: The unified upload manager to use
        """
        try:
            # Disconnect old signals if any
            if self.upload_manager:
                try:
                    self.upload_manager.upload_progress.disconnect()
                    self.upload_manager.status_message.disconnect()
                except:
                    pass  # Ignore disconnection errors
            
            # Set new upload manager
            self.upload_manager = upload_manager
            self.upload_queue = None
            
            if upload_manager and hasattr(upload_manager, 'upload_queue'):
                self.upload_queue = upload_manager.upload_queue
                
            # Reconnect signals
            self._connect_signals()
            
            # Update display immediately
            self._safe_update_displays()
            
            print("✅ Upload manager updated in transfer view")
            
        except Exception as e:
            print(f"❌ Error setting upload manager: {e}")
            import traceback
            traceback.print_exc()
    
    def _safe_update_displays(self):
        """Safely update displays with error handling"""
        try:
            self._update_displays()
        except Exception as e:
            print(f"❌ Error updating transfer displays: {e}")
            # Don't crash, just log the error
    
    def _setup_ui(self):
        """Set up the user interface"""
        layout = QVBoxLayout(self)
        
        # Control panel
        self._create_control_panel(layout)
        
        # Statistics panel
        self._create_statistics_panel(layout)
        
        # Main content - tabbed view
        self._create_main_content(layout)
        
        # Error files panel at bottom
        self._create_error_panel(layout)
    
    def _create_control_panel(self, parent_layout):
        """Create control buttons panel"""
        control_group = QGroupBox("Contrôles d'Upload")
        control_layout = QHBoxLayout(control_group)
        
        # Pause/Resume button
        self.pause_resume_btn = QPushButton("⏸️ Pause")
        self.pause_resume_btn.clicked.connect(self._on_pause_resume_clicked)
        control_layout.addWidget(self.pause_resume_btn)
        
        # Retry all button
        self.retry_all_btn = QPushButton("🔄 Réessayer tout")
        self.retry_all_btn.clicked.connect(self.retry_all_requested.emit)
        control_layout.addWidget(self.retry_all_btn)
        
        # Clear completed button
        self.clear_btn = QPushButton("🧹 Vider terminés")
        self.clear_btn.clicked.connect(self.clear_completed_requested.emit)
        control_layout.addWidget(self.clear_btn)
        
        control_layout.addStretch()
        
        parent_layout.addWidget(control_group)
    
    def _create_statistics_panel(self, parent_layout):
        """Create overall statistics panel"""
        stats_group = QGroupBox("Statistiques Globales")
        stats_layout = QHBoxLayout(stats_group)
        
        # Progress bar
        self.overall_progress = QProgressBar()
        self.overall_progress.setTextVisible(True)
        stats_layout.addWidget(QLabel("Progrès:"))
        stats_layout.addWidget(self.overall_progress)
        
        # Statistics labels
        self.stats_label = QLabel("0 fichiers | 0 B")
        self.stats_label.setMinimumWidth(200)
        stats_layout.addWidget(self.stats_label)
        
        self.speed_label = QLabel("0 B/s")
        self.speed_label.setMinimumWidth(100)
        stats_layout.addWidget(self.speed_label)
        
        self.workers_label = QLabel("0/0 workers")
        self.workers_label.setMinimumWidth(100)
        stats_layout.addWidget(self.workers_label)
        
        parent_layout.addWidget(stats_group)
    
    def _create_main_content(self, parent_layout):
        """Create main tabbed content area"""
        self.tab_widget = QTabWidget()
        
        # Tab 1: Folder view
        self._create_folder_view_tab()
        
        # Tab 2: All files view  
        self._create_files_view_tab()
        
        parent_layout.addWidget(self.tab_widget)
    
    def _create_folder_view_tab(self):
        """Create folder view tab"""
        folder_widget = QWidget()
        layout = QVBoxLayout(folder_widget)
        
        # Tree view for folders
        self.folder_tree = QTreeView()
        self.folder_tree.setAlternatingRowColors(True)
        self.folder_tree.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.folder_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.folder_tree.customContextMenuRequested.connect(self._on_folder_context_menu)
        
        # Model for folder tree
        self.folder_model = QStandardItemModel()
        self.folder_model.setHorizontalHeaderLabels([
            "Dossier", "Statut", "Progrès", "Fichiers", "Vitesse", "ETA", "Taille"
        ])
        self.folder_tree.setModel(self.folder_model)
        
        layout.addWidget(self.folder_tree)
        
        self.tab_widget.addTab(folder_widget, "📁 Vue Dossiers")
    
    def _create_files_view_tab(self):
        """Create all files view tab"""
        files_widget = QWidget()
        layout = QVBoxLayout(files_widget)
        
        # Filter buttons
        filter_layout = QHBoxLayout()
        
        self.filter_all_btn = QPushButton("📋 Tous")
        self.filter_pending_btn = QPushButton("⏳ En attente")
        self.filter_progress_btn = QPushButton("🔄 En cours")
        self.filter_completed_btn = QPushButton("✅ Terminés")
        self.filter_failed_btn = QPushButton("❌ Erreurs")
        
        filter_layout.addWidget(self.filter_all_btn)
        filter_layout.addWidget(self.filter_pending_btn)
        filter_layout.addWidget(self.filter_progress_btn)
        filter_layout.addWidget(self.filter_completed_btn)
        filter_layout.addWidget(self.filter_failed_btn)
        filter_layout.addStretch()
        
        # Connect filter buttons
        self.filter_all_btn.clicked.connect(lambda: self._filter_files(None))
        self.filter_pending_btn.clicked.connect(lambda: self._filter_files(FileStatus.PENDING))
        self.filter_progress_btn.clicked.connect(lambda: self._filter_files(FileStatus.IN_PROGRESS))
        self.filter_completed_btn.clicked.connect(lambda: self._filter_files(FileStatus.COMPLETED))
        self.filter_failed_btn.clicked.connect(lambda: self._filter_files(FileStatus.ERROR))
        
        layout.addLayout(filter_layout)
        
        # Files table
        self.files_table = QTableWidget()
        self.files_table.setColumnCount(6)
        self.files_table.setHorizontalHeaderLabels([
            "Statut", "Nom", "Dossier", "Taille", "ETA", "Retry"
        ])
        
        # Table properties
        self.files_table.setAlternatingRowColors(True)
        self.files_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.files_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.files_table.customContextMenuRequested.connect(self._on_file_context_menu)
        
        # Adjust column widths
        header = self.files_table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(1, QHeaderView.Stretch)  # File name
        
        layout.addWidget(self.files_table)
        
        self.tab_widget.addTab(files_widget, "📄 Tous les Fichiers")
    
    def _create_error_panel(self, parent_layout):
        """Create error files panel at bottom"""
        self.error_group = QGroupBox("❌ Fichiers en Erreur")
        error_layout = QVBoxLayout(self.error_group)
        
        # Error files table
        self.error_table = QTableWidget()
        self.error_table.setColumnCount(4)
        self.error_table.setHorizontalHeaderLabels([
            "Fichier", "Dossier", "Erreur", "Retry"
        ])
        self.error_table.setMaximumHeight(150)
        self.error_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.error_table.customContextMenuRequested.connect(self._on_error_context_menu)
        
        error_layout.addWidget(self.error_table)
        
        # Initially hidden
        self.error_group.setVisible(False)
        
        parent_layout.addWidget(self.error_group)
    
    def _connect_signals(self):
        """Connect upload manager signals"""
        if not self.upload_queue:
            print("⚠️ No upload queue available - signals not connected")
            return
        
        try:
            # Connect queue signals
            self.upload_queue.file_added.connect(self._on_file_added)
            self.upload_queue.file_updated.connect(self._on_file_updated)
            self.upload_queue.folder_added.connect(self._on_folder_added)
            self.upload_queue.folder_updated.connect(self._on_folder_updated)
            self.upload_queue.queue_statistics_changed.connect(self._on_statistics_changed)
            print("✅ Upload queue signals connected successfully")
        except Exception as e:
            print(f"❌ Error connecting signals: {e}")
    
    def _update_displays(self):
        """Update all display elements"""
        if not self.upload_queue:
            return
        
        self._update_statistics()
        self._update_folder_view()
        self._update_files_view()
        self._update_error_view()
    
    def _update_statistics(self):
        """Update overall statistics display"""
        if not self.upload_manager:
            # Set default values if no upload manager
            self.overall_progress.setValue(0)
            self.overall_progress.setFormat("0%")
            self.stats_label.setText("Aucun gestionnaire d'upload")
            self.speed_label.setText("0 B/s")
            self.workers_label.setText("0/0 workers (0 actifs)")
            self.pause_resume_btn.setText("🚀 Démarrer")
            return
        
        try:
            stats = self.upload_manager.get_queue_statistics()
            
            # Progress bar
            progress = stats.get('progress_percentage', 0)
            self.overall_progress.setValue(progress)
            self.overall_progress.setFormat(f"{progress}%")
            
            # Statistics label
            total_files = stats.get('total_files', 0)
            total_size = stats.get('total_size', 0)
            completed = stats.get('completed', 0)
            failed = stats.get('failed', 0)
            
            stats_text = f"{total_files} fichiers | {format_file_size(total_size)}"
            if completed > 0 or failed > 0:
                stats_text += f" | ✅{completed} ❌{failed}"
            
            self.stats_label.setText(stats_text)
            
            # Speed label
            speed = stats.get('active_speed', 0)
            self.speed_label.setText(f"{format_file_size(int(speed))}/s")
            
            # Workers label
            workers_info = stats.get('workers', {})
            total_workers = workers_info.get('total_workers', 0)
            running_workers = workers_info.get('running_workers', 0)
            active_files = workers_info.get('total_active_files', 0)
            
            self.workers_label.setText(f"{running_workers}/{total_workers} workers ({active_files} actifs)")
            
            # Update pause/resume button
            if hasattr(self.upload_manager, 'is_paused') and self.upload_manager.is_paused():
                self.pause_resume_btn.setText("▶️ Reprendre")
            elif hasattr(self.upload_manager, 'is_active') and self.upload_manager.is_active():
                self.pause_resume_btn.setText("⏸️ Pause")
            else:
                self.pause_resume_btn.setText("🚀 Démarrer")
                
        except Exception as e:
            print(f"❌ Error updating statistics: {e}")
            # Set safe defaults
            self.overall_progress.setValue(0)
            self.stats_label.setText("Erreur de mise à jour")
            self.speed_label.setText("0 B/s")
    
    def _update_folder_view(self):
        """Update folder tree view"""
        if not self.upload_queue or not self.upload_manager:
            return
        
        try:
            # Clear existing items
            self.folder_model.clear()
            self.folder_model.setHorizontalHeaderLabels([
                "Dossier", "Statut", "Progrès", "Fichiers", "Vitesse", "ETA", "Taille"
            ])
            
            # Get all folders
            if hasattr(self.upload_manager, 'get_all_folders'):
                folders = self.upload_manager.get_all_folders()
                
                for folder in folders:
                    self._add_folder_to_tree(folder)
        except Exception as e:
            print(f"❌ Error updating folder view: {e}")
    
    def _add_folder_to_tree(self, folder_info: FolderInfo):
        """Add a folder to the tree view"""
        # Folder name
        name_item = QStandardItem(f"📁 {folder_info.folder_name}")
        name_item.setData(folder_info.folder_path, Qt.UserRole)
        
        # Status
        if folder_info.is_completed:
            if folder_info.has_errors:
                status = "✅ Terminé (avec erreurs)"
            else:
                status = "✅ Terminé"
        elif folder_info.in_progress_files > 0:
            status = "🔄 En cours"
        elif folder_info.total_files > 0:
            status = "⏳ En attente"
        else:
            status = "📁 Vide"
        
        status_item = QStandardItem(status)
        
        # Progress
        progress_text = f"{folder_info.progress_percentage}%"
        if folder_info.total_files > 0:
            processed = folder_info.completed_files + folder_info.failed_files + folder_info.skipped_files
            progress_text += f" ({processed}/{folder_info.total_files})"
        
        progress_item = QStandardItem(progress_text)
        
        # Files count detail
        files_text = f"{folder_info.total_files}"
        if folder_info.failed_files > 0:
            files_text += f" (❌{folder_info.failed_files})"
        
        files_item = QStandardItem(files_text)
        
        # Speed (aggregate from files in this folder)
        folder_files = self.upload_queue.get_files_by_folder(folder_info.folder_path)
        total_speed = sum(f.speed for f in folder_files if f.status == FileStatus.IN_PROGRESS)
        speed_item = QStandardItem(f"{format_file_size(int(total_speed))}/s" if total_speed > 0 else "")
        
        # ETA (estimate based on remaining files and current speed)
        remaining_files = sum(1 for f in folder_files if f.status in [FileStatus.PENDING, FileStatus.IN_PROGRESS])
        if remaining_files > 0 and total_speed > 0:
            # Rough estimate: assume average file size
            avg_size = sum(f.file_size for f in folder_files) / len(folder_files) if folder_files else 0
            remaining_bytes = remaining_files * avg_size
            eta_seconds = remaining_bytes / total_speed
            if eta_seconds < 60:
                eta_text = f"{int(eta_seconds)}s"
            elif eta_seconds < 3600:
                eta_text = f"{int(eta_seconds // 60)}m"
            else:
                eta_text = f"{int(eta_seconds // 3600)}h"
        else:
            eta_text = ""
        
        eta_item = QStandardItem(eta_text)
        
        # Total size
        total_size = sum(f.file_size for f in folder_files)
        size_item = QStandardItem(format_file_size(total_size))
        
        # Add row to model
        self.folder_model.appendRow([
            name_item, status_item, progress_item, files_item, 
            speed_item, eta_item, size_item
        ])
    
    def _update_files_view(self):
        """Update all files view"""
        if not self.upload_queue or not self.upload_manager:
            return
        
        try:
            # Get current filter
            current_filter = getattr(self, '_current_filter', None)
            
            # Get files based on filter
            if current_filter is None and hasattr(self.upload_manager, 'get_all_files'):
                files = self.upload_manager.get_all_files()
            elif hasattr(self.upload_manager, 'get_files_by_status'):
                files = self.upload_manager.get_files_by_status(current_filter)
            else:
                files = []
            
            # Limit display to prevent UI lag
            max_display = 1000
            if len(files) > max_display:
                files = files[:max_display]
            
            # Update table
            self.files_table.setRowCount(len(files))
            
            for row, file in enumerate(files):
                self._update_file_row(row, file)
        except Exception as e:
            print(f"❌ Error updating files view: {e}")
    
    def _update_file_row(self, row: int, file: QueuedFile):
        """Update a single file row in the table"""
        # Status
        status_text = file.status.value
        if file.retry_count > 0:
            status_text += f" (Retry {file.retry_count})"
        
        status_item = QTableWidgetItem(status_text)
        status_item.setData(Qt.UserRole, file.unique_id)
        self.files_table.setItem(row, 0, status_item)
        
        # File name
        name_item = QTableWidgetItem(file.file_name)
        self.files_table.setItem(row, 1, name_item)
        
        # Folder
        folder_name = os.path.basename(file.source_folder)
        if file.relative_path:
            folder_name += f"/{file.relative_path}"
        
        folder_item = QTableWidgetItem(folder_name)
        self.files_table.setItem(row, 2, folder_item)
        
        # Size
        size_item = QTableWidgetItem(format_file_size(file.file_size))
        self.files_table.setItem(row, 3, size_item)
        
        # ETA
        eta = file.get_eta()
        if eta and file.status == FileStatus.IN_PROGRESS:
            if eta < 60:
                eta_text = f"{int(eta)}s"
            elif eta < 3600:
                eta_text = f"{int(eta // 60)}m"
            else:
                eta_text = f"{int(eta // 3600)}h"
        else:
            eta_text = ""
        
        eta_item = QTableWidgetItem(eta_text)
        self.files_table.setItem(row, 4, eta_item)
        
        # Retry count
        retry_item = QTableWidgetItem(str(file.retry_count) if file.retry_count > 0 else "")
        self.files_table.setItem(row, 5, retry_item)
    
    def _update_error_view(self):
        """Update error files view"""
        if not self.upload_queue or not self.upload_manager:
            return
        
        try:
            # Get failed files
            if hasattr(self.upload_manager, 'get_files_by_status'):
                failed_files = self.upload_manager.get_files_by_status(FileStatus.ERROR)
            else:
                failed_files = []
            
            # Show/hide error panel
            self.error_group.setVisible(len(failed_files) > 0)
            
            if not failed_files:
                return
            
            # Update error table
            self.error_table.setRowCount(len(failed_files))
            
            for row, file in enumerate(failed_files):
                # File name
                name_item = QTableWidgetItem(file.file_name)
                name_item.setData(Qt.UserRole, file.unique_id)
                self.error_table.setItem(row, 0, name_item)
            
                # Folder
                folder_name = os.path.basename(file.source_folder)
                if file.relative_path:
                    folder_name += f"/{file.relative_path}"
                
                folder_item = QTableWidgetItem(folder_name)
                self.error_table.setItem(row, 1, folder_item)
                
                # Error message
                error_item = QTableWidgetItem(file.error_message[:100] + "..." if len(file.error_message) > 100 else file.error_message)
                error_item.setToolTip(file.error_message)  # Full error on hover
                self.error_table.setItem(row, 2, error_item)
                
                # Retry count
                retry_item = QTableWidgetItem(str(file.retry_count))
                self.error_table.setItem(row, 3, retry_item)
        except Exception as e:
            print(f"❌ Error updating error view: {e}")
    
    def _filter_files(self, status: Optional[FileStatus]):
        """Filter files by status"""
        self._current_filter = status
        self._update_files_view()
        
        # Update button styles
        buttons = [self.filter_all_btn, self.filter_pending_btn, self.filter_progress_btn, 
                  self.filter_completed_btn, self.filter_failed_btn]
        
        for btn in buttons:
            btn.setStyleSheet("")  # Reset style
        
        # Highlight active filter
        if status is None:
            self.filter_all_btn.setStyleSheet("font-weight: bold;")
        elif status == FileStatus.PENDING:
            self.filter_pending_btn.setStyleSheet("font-weight: bold;")
        elif status == FileStatus.IN_PROGRESS:
            self.filter_progress_btn.setStyleSheet("font-weight: bold;")
        elif status == FileStatus.COMPLETED:
            self.filter_completed_btn.setStyleSheet("font-weight: bold;")
        elif status == FileStatus.ERROR:
            self.filter_failed_btn.setStyleSheet("font-weight: bold;")
    
    # Event handlers
    def _on_pause_resume_clicked(self):
        """Handle pause/resume button clicked"""
        if not self.upload_manager:
            return
        
        if self.upload_manager.is_paused():
            self.resume_requested.emit()
        elif self.upload_manager.is_active():
            self.pause_requested.emit()
        else:
            # Start new session
            self.upload_manager.start_upload_session()
    
    def _on_folder_context_menu(self, position):
        """Handle folder tree context menu"""
        index = self.folder_tree.indexAt(position)
        if not index.isValid():
            return
        
        # Get folder path from the item
        item = self.folder_model.itemFromIndex(index)
        if not item:
            return
        
        folder_path = item.data(Qt.UserRole)
        if not folder_path:
            return
        
        menu = QMenu(self)
        
        # Retry failed files in this folder
        retry_action = QAction("🔄 Réessayer fichiers échoués", self)
        retry_action.triggered.connect(lambda: self._retry_folder_files(folder_path))
        menu.addAction(retry_action)
        
        menu.exec_(self.folder_tree.mapToGlobal(position))
    
    def _on_file_context_menu(self, position):
        """Handle files table context menu"""
        row = self.files_table.rowAt(position.y())
        if row < 0:
            return
        
        # Get file unique ID
        status_item = self.files_table.item(row, 0)
        if not status_item:
            return
        
        file_unique_id = status_item.data(Qt.UserRole)
        if not file_unique_id:
            return
        
        menu = QMenu(self)
        
        # Retry this file
        retry_action = QAction("🔄 Réessayer ce fichier", self)
        retry_action.triggered.connect(lambda: self.retry_file_requested.emit(file_unique_id))
        menu.addAction(retry_action)
        
        menu.exec_(self.files_table.mapToGlobal(position))
    
    def _on_error_context_menu(self, position):
        """Handle error table context menu"""
        row = self.error_table.rowAt(position.y())
        if row < 0:
            return
        
        # Get file unique ID
        name_item = self.error_table.item(row, 0)
        if not name_item:
            return
        
        file_unique_id = name_item.data(Qt.UserRole)
        if not file_unique_id:
            return
        
        menu = QMenu(self)
        
        # Retry this file
        retry_action = QAction("🔄 Réessayer ce fichier", self)
        retry_action.triggered.connect(lambda: self.retry_file_requested.emit(file_unique_id))
        menu.addAction(retry_action)
        
        menu.exec_(self.error_table.mapToGlobal(position))
    
    def _retry_folder_files(self, folder_path: str):
        """Retry all failed files in a specific folder"""
        if not self.upload_queue:
            return
        
        # Get failed files in this folder
        folder_files = self.upload_queue.get_files_by_folder(folder_path)
        failed_files = [f for f in folder_files if f.status == FileStatus.ERROR and f.can_retry]
        
        # Retry each failed file
        retry_count = 0
        for file in failed_files:
            if self.upload_queue.retry_file(file.unique_id):
                retry_count += 1
        
        if retry_count > 0:
            print(f"🔄 {retry_count} fichier(s) du dossier en cours de retry")
    
    # Signal handlers for upload queue events
    def _on_file_added(self, unique_id: str):
        """Handle file added to queue"""
        pass  # Will be updated by timer
    
    def _on_file_updated(self, unique_id: str):
        """Handle file status updated"""
        pass  # Will be updated by timer
    
    def _on_folder_added(self, folder_path: str):
        """Handle folder added to queue"""
        pass  # Will be updated by timer
    
    def _on_folder_updated(self, folder_path: str):
        """Handle folder statistics updated"""
        pass  # Will be updated by timer
    
    def _on_statistics_changed(self):
        """Handle queue statistics changed"""
        pass  # Will be updated by timer


# Legacy adapter for existing TransferPanel usage
class TransferPanel(UnifiedTransferView):
    """
    Legacy adapter to maintain compatibility with existing code
    """
    
    def __init__(self, transfer_manager=None):
        """
        Initialize with legacy interface
        
        Args:
            transfer_manager: Legacy transfer manager (ignored)
        """
        # Get upload manager from main window if available
        upload_manager = None
        try:
            from PyQt5.QtWidgets import QApplication
            app = QApplication.instance()
            if app and hasattr(app, 'activeWindow'):
                main_window = app.activeWindow()
                if hasattr(main_window, 'upload_manager'):
                    upload_manager = main_window.upload_manager
        except:
            pass
        
        super().__init__(upload_manager)
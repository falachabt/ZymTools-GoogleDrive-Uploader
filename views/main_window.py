"""
Fenêtre principale de l'application Google Drive Explorer avec interface à onglets
"""

import os
import shutil
import subprocess
import sys
from typing import List, Dict, Any, Optional
from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QPushButton, QLabel, QFileDialog, QMessageBox,
                             QMenu, QAction, QSplitter, QToolBar, QStatusBar,
                             QProgressBar, QLineEdit, QComboBox, QApplication,
                             QTabWidget)
from PyQt5.QtCore import Qt, QSize, QTimer, pyqtSignal
from PyQt5.QtGui import QKeySequence

from config.settings import (WINDOW_TITLE, WINDOW_WIDTH, WINDOW_HEIGHT,
                             TOOLBAR_ICON_SIZE, CACHE_CLEANUP_INTERVAL_MS)
from core.cache_manager import CacheManager
from core.google_drive_client import GoogleDriveClient
from threads.file_load_threads import LocalFileLoadThread, DriveFileLoadThread
from threads.transfer_threads import UploadThread, FolderUploadThread, DownloadThread, SafeFolderUploadThread
from models.file_models import FileListModel, LocalFileModel
from models.transfer_models import  TransferManager
from views.tree_views import LocalTreeView, DriveTreeView
from views.dialogs import (SearchDialog, FileDetailsDialog, RenameDialog,
                           CreateFolderDialog, ConfirmationDialog, ErrorDialog)
from views.transfer_view import  TransferPanel
from utils.helpers import (format_file_size, get_file_emoji, get_file_type_description,
                           format_date, sanitize_filename)


def ensure_imports():
    """S'assurer que les imports nécessaires sont présents"""
    # Cette fonction doit être appelée au début du fichier main_window.py
    # pour s'assurer que SafeFolderUploadThread est importé

    # Ajouter cet import en haut du fichier main_window.py :
    # from threads.transfer_threads import UploadThread, FolderUploadThread, DownloadThread, SafeFolderUploadThread
    pass



class DriveExplorerMainWindow(QMainWindow):
    """Fenêtre principale de l'application avec interface à onglets"""

    def __init__(self):
        """Initialise la fenêtre principale"""
        super().__init__()

        # Paramètres de sécurité
        self.MAX_PARALLEL_UPLOADS = 1
        self.SAFE_MODE = True

        self.transfer_manager = TransferManager()



        # Initialiser les composants principaux
        self.setup_core_components()

        # Configuration de la fenêtre
        self.setWindowTitle(WINDOW_TITLE)
        self.resize(WINDOW_WIDTH, WINDOW_HEIGHT)

        # Créer l'interface utilisateur
        self.setup_ui()

        # Connecter les signaux
        self.connect_signals()

        # Connecter les signaux du panneau de transferts
        self.connect_transfer_signals()

        # Charger les fichiers au démarrage
        self.refresh_local_files()
        if self.connected:
            self.refresh_drive_files()

    def setup_core_components(self) -> None:
        """Initialise les composants principaux"""
        # Gestionnaire de cache
        self.cache_manager = CacheManager(max_age_minutes=10)

        # Timer pour nettoyer le cache périodiquement
        self.cache_cleanup_timer = QTimer()
        self.cache_cleanup_timer.timeout.connect(self.cache_manager.clear_old_cache)
        self.cache_cleanup_timer.start(CACHE_CLEANUP_INTERVAL_MS)

        # Client Google Drive
        self.drive_client = None
        self.connected = False
        self.connect_to_drive()

        # Threads de chargement et transfert
        self.local_load_thread = None
        self.drive_load_thread = None
        self.upload_threads = []
        self.download_threads = []
        self.folder_upload_threads = []

    def connect_to_drive(self) -> None:
        """Connecte à Google Drive"""
        try:
            self.drive_client = GoogleDriveClient()
            self.connected = True
            print("✅ Connexion à Google Drive réussie")
        except Exception as e:
            self.connected = False
            print(f"❌ Erreur de connexion à Google Drive: {e}")

    def setup_ui(self) -> None:
        """Configure l'interface utilisateur avec onglets"""
        # Widget central
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)

        # Barre d'outils et statut
        self.create_toolbar()
        self.create_status_bar()

        # Layout principal
        main_layout = QVBoxLayout()

        # === NOUVEAU : Système d'onglets ===
        self.tab_widget = QTabWidget()

        # Onglet 1: Explorateur de fichiers
        self.explorer_tab = self.create_explorer_tab()
        self.tab_widget.addTab(self.explorer_tab, "📂 Explorateur")

        # Onglet 2: Gestionnaire de transferts
        self.transfer_panel = TransferPanel(self.transfer_manager)
        self.tab_widget.addTab(self.transfer_panel, "📋 Transferts")

        # Connecter le signal de changement d'onglet
        self.tab_widget.currentChanged.connect(self.on_tab_changed)

        main_layout.addWidget(self.tab_widget)

        # Barre de progression (reste en bas)
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(True)
        main_layout.addWidget(self.progress_bar)

        self.central_widget.setLayout(main_layout)

        # Raccourcis clavier
        self.setup_shortcuts()

    def create_explorer_tab(self) -> QWidget:
        """Crée l'onglet explorateur de fichiers"""
        explorer_widget = QWidget()
        explorer_layout = QVBoxLayout(explorer_widget)

        # Splitter pour diviser l'écran
        self.splitter = QSplitter(Qt.Horizontal)

        # Partie gauche - Système local
        local_widget = self.create_local_panel()

        # Partie droite - Google Drive
        drive_widget = self.create_drive_panel()

        # Ajouter au splitter
        self.splitter.addWidget(local_widget)
        self.splitter.addWidget(drive_widget)
        self.splitter.setSizes([int(WINDOW_WIDTH * 0.4), int(WINDOW_WIDTH * 0.6)])

        explorer_layout.addWidget(self.splitter)

        return explorer_widget

    def create_local_panel(self) -> QWidget:
        """Crée le panneau des fichiers locaux"""
        local_widget = QWidget()
        local_layout = QVBoxLayout(local_widget)

        # Chemin local avec bouton browser
        local_path_layout = QHBoxLayout()
        local_path_layout.addWidget(QLabel("📂 Chemin local:"))

        self.local_path_edit = QLineEdit(os.path.expanduser("~"))
        self.local_path_edit.returnPressed.connect(self.change_local_path)
        local_path_layout.addWidget(self.local_path_edit)

        self.browse_button = QPushButton("📁")
        self.browse_button.setFixedWidth(35)
        self.browse_button.clicked.connect(self.browse_local_folder)
        self.browse_button.setToolTip("Choisir un dossier")
        local_path_layout.addWidget(self.browse_button)

        local_layout.addLayout(local_path_layout)

        # Vue des fichiers locaux
        self.local_model = LocalFileModel(["Nom", "Taille", "Date de modification", "Type"])
        self.local_view = LocalTreeView()
        self.local_view.setModel(self.local_model)
        self.local_view.setColumnWidth(0, 250)
        local_layout.addWidget(self.local_view)

        return local_widget

    def create_drive_panel(self) -> QWidget:
        """Crée le panneau Google Drive"""
        drive_widget = QWidget()
        drive_layout = QVBoxLayout(drive_widget)

        # Sélecteur de Drive
        drive_selector_layout = QHBoxLayout()
        drive_selector_layout.addWidget(QLabel("☁️ Drive:"))

        self.drive_selector = QComboBox()
        self.drive_selector.addItem("☁️ Mon Drive", "root")

        # Ajouter les Shared Drives si connecté
        if self.connected:
            try:
                for drive in self.drive_client.list_shared_drives():
                    self.drive_selector.addItem(f"🏢 {drive['name']}", drive['id'])
            except Exception as e:
                print(f"Erreur lors du chargement des Shared Drives: {e}")

        self.drive_selector.currentIndexChanged.connect(self.change_drive)
        drive_selector_layout.addWidget(self.drive_selector)
        drive_layout.addLayout(drive_selector_layout)

        # Navigation Google Drive
        drive_path_layout = QHBoxLayout()

        self.drive_back_btn = QPushButton("⬅️")
        self.drive_back_btn.setFixedWidth(35)
        self.drive_back_btn.clicked.connect(self.drive_go_back)
        self.drive_back_btn.setToolTip("Retour")
        drive_path_layout.addWidget(self.drive_back_btn)

        self.drive_path_label = QLabel("☁️ Racine")
        drive_path_layout.addWidget(self.drive_path_label, 1)

        self.drive_refresh_btn = QPushButton("🔄")
        self.drive_refresh_btn.setFixedWidth(35)
        self.drive_refresh_btn.clicked.connect(self.refresh_drive_files)
        self.drive_refresh_btn.setToolTip("Actualiser")
        drive_path_layout.addWidget(self.drive_refresh_btn)

        drive_layout.addLayout(drive_path_layout)

        # Vue des fichiers Google Drive
        self.drive_model = FileListModel(["Nom", "Taille", "Date de modification", "Type", "ID"])
        self.drive_view = DriveTreeView()
        self.drive_view.setModel(self.drive_model)
        self.drive_view.setColumnWidth(0, 250)
        self.drive_view.hide_column(4)  # Cacher la colonne ID
        drive_layout.addWidget(self.drive_view)

        return drive_widget

    def create_toolbar(self) -> None:
        """Crée la barre d'outils moderne avec émojis"""
        self.toolbar = QToolBar("Actions")
        self.toolbar.setIconSize(QSize(*TOOLBAR_ICON_SIZE))
        self.toolbar.setMovable(False)

        # Actions principales
        self.refresh_action = QAction("🔄 Actualiser", self)
        self.refresh_action.setShortcut("F5")
        self.refresh_action.setToolTip("Actualiser les deux vues (F5)")
        self.refresh_action.triggered.connect(self.refresh_all)
        self.toolbar.addAction(self.refresh_action)

        self.toolbar.addSeparator()

        # === ACTIONS POUR LES TRANSFERTS MODIFIÉES ===
        self.show_transfers_action = QAction("📋 Transferts", self)
        self.show_transfers_action.setToolTip("Aller à l'onglet Transferts")
        self.show_transfers_action.triggered.connect(self.show_transfers_tab)
        self.toolbar.addAction(self.show_transfers_action)

        self.clear_completed_transfers_action = QAction("🧹 Vider terminés", self)
        self.clear_completed_transfers_action.setToolTip("Supprimer les transferts terminés")
        self.clear_completed_transfers_action.triggered.connect(self.clear_completed_transfers)
        self.toolbar.addAction(self.clear_completed_transfers_action)

        self.clear_cache_action = QAction("🗑️ Vider cache", self)
        self.clear_cache_action.setToolTip("Vider le cache des données")
        self.clear_cache_action.triggered.connect(self.clear_cache)
        self.toolbar.addAction(self.clear_cache_action)

        self.new_folder_action = QAction("📁 Nouveau dossier", self)
        self.new_folder_action.setToolTip("Créer un nouveau dossier")
        self.new_folder_action.triggered.connect(self.create_new_folder)
        self.toolbar.addAction(self.new_folder_action)

        self.search_action = QAction("🔍 Rechercher", self)
        self.search_action.setShortcut("Ctrl+F")
        self.search_action.setToolTip("Rechercher dans Google Drive (Ctrl+F)")
        self.search_action.triggered.connect(self.show_search_dialog)
        self.toolbar.addAction(self.search_action)

        self.toolbar.addSeparator()

        # Actions de connexion
        self.disconnect_action = QAction("🔌 Déconnecter", self)
        self.disconnect_action.setToolTip("Se déconnecter de Google Drive")
        self.disconnect_action.triggered.connect(self.disconnect_from_drive)
        self.toolbar.addAction(self.disconnect_action)

        self.reconnect_action = QAction("🔗 Reconnecter", self)
        self.reconnect_action.setToolTip("Se reconnecter à Google Drive")
        self.reconnect_action.triggered.connect(self.reconnect_to_drive)
        self.toolbar.addAction(self.reconnect_action)

        self.toolbar.addSeparator()

        self.safe_mode_action = QAction("🛡️ Mode sécurisé", self)
        self.safe_mode_action.setCheckable(True)
        self.safe_mode_action.setChecked(self.SAFE_MODE)
        self.safe_mode_action.setToolTip("Basculer entre mode sécurisé et rapide pour les uploads")
        self.safe_mode_action.triggered.connect(self.toggle_safe_mode)
        self.toolbar.addAction(self.safe_mode_action)

        self.addToolBar(self.toolbar)
        self.update_toolbar_state()

    def create_status_bar(self) -> None:
        """Crée la barre de statut"""
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

    def setup_shortcuts(self) -> None:
        """Configure les raccourcis clavier"""
        from PyQt5.QtWidgets import QShortcut

        QShortcut(QKeySequence("F5"), self, self.refresh_all)
        QShortcut(QKeySequence("F2"), self, self.rename_selected)
        QShortcut(QKeySequence("Delete"), self, self.delete_selected)
        QShortcut(QKeySequence("Ctrl+F"), self, self.show_search_dialog)
        # Nouveau raccourci pour aller aux transferts
        QShortcut(QKeySequence("Ctrl+T"), self, self.show_transfers_tab)

    def on_tab_changed(self, index: int) -> None:
        """Appelé quand l'onglet change"""
        if index == 1:  # Onglet Transferts
            # Mettre à jour le titre de l'onglet avec le nombre de transferts
            transfer_count = len(self.transfer_manager.get_all_transfers())
            active_count = len(self.transfer_manager.get_active_transfers())
            if active_count > 0:
                self.tab_widget.setTabText(1, f"📋 Transferts ({active_count} actifs)")
            else:
                self.tab_widget.setTabText(1, f"📋 Transferts ({transfer_count})")

    def show_transfers_tab(self) -> None:
        """Affiche l'onglet des transferts"""
        self.tab_widget.setCurrentIndex(1)

    def connect_signals(self) -> None:
        """Connecte les signaux des vues"""
        # Vue locale
        self.local_view.doubleClicked.connect(self.local_item_double_clicked)
        self.local_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.local_view.customContextMenuRequested.connect(self.show_local_context_menu)
        self.local_view.files_dropped.connect(self.handle_local_files_dropped)

        # Vue Google Drive
        self.drive_view.doubleClicked.connect(self.drive_item_double_clicked)
        self.drive_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.drive_view.customContextMenuRequested.connect(self.show_drive_context_menu)
        self.drive_view.local_files_dropped.connect(self.handle_drive_files_dropped)

    def connect_transfer_signals(self) -> None:
        """Connecte les signaux du panneau de transferts"""
        self.transfer_panel.cancel_transfer_requested.connect(self.cancel_transfer)
        self.transfer_panel.pause_transfer_requested.connect(self.pause_transfer)
        self.transfer_panel.resume_transfer_requested.connect(self.resume_transfer)

        # Connecter les signaux du transfer_manager pour mettre à jour l'onglet
        self.transfer_manager.transfer_added.connect(self.update_transfer_tab_title)
        self.transfer_manager.transfer_removed.connect(self.update_transfer_tab_title)
        self.transfer_manager.transfer_status_changed.connect(self.update_transfer_tab_title)

    def update_transfer_tab_title(self, *args) -> None:
        """Met à jour le titre de l'onglet transferts"""
        transfer_count = len(self.transfer_manager.get_all_transfers())
        active_count = len(self.transfer_manager.get_active_transfers())

        if active_count > 0:
            title = f"📋 Transferts ({active_count} actifs)"
        elif transfer_count > 0:
            title = f"📋 Transferts ({transfer_count})"
        else:
            title = "📋 Transferts"

        self.tab_widget.setTabText(1, title)

    def update_toolbar_state(self) -> None:
        """Met à jour l'état des boutons selon la connexion"""
        self.search_action.setEnabled(self.connected)
        self.disconnect_action.setEnabled(self.connected)
        self.reconnect_action.setEnabled(not self.connected)

    # ==================== GESTION DES FICHIERS LOCAUX ====================

    def refresh_local_files(self, path: Optional[str] = None) -> None:
        """Actualise la liste des fichiers locaux avec cache"""
        target_path = path if path is not None else self.local_path_edit.text()

        if not os.path.isdir(target_path):
            target_path = os.path.expanduser("~")
            self.local_path_edit.setText(target_path)

        self.local_model.set_current_path(target_path)

        # Vérifier le cache
        cached_data = self.cache_manager.get_local_cache(target_path)
        if cached_data:
            self.populate_local_model(cached_data, from_cache=True)
            self.status_bar.showMessage("📋 Données du cache affichées - Actualisation en cours...", 2000)

        # Lancer le chargement en arrière-plan
        if self.local_load_thread and self.local_load_thread.isRunning():
            self.local_load_thread.terminate()
            self.local_load_thread.wait()

        self.local_load_thread = LocalFileLoadThread(target_path)
        self.local_load_thread.files_loaded.connect(self.on_local_files_loaded)
        self.local_load_thread.error_occurred.connect(self.on_local_load_error)
        self.local_load_thread.start()

    def on_local_files_loaded(self, path: str, file_list: List[Dict[str, Any]]) -> None:
        """Callback quand les fichiers locaux sont chargés"""
        self.cache_manager.set_local_cache(path, file_list)
        if path == self.local_model.current_path:
            self.populate_local_model(file_list, from_cache=False)
            self.status_bar.showMessage(f"✅ Fichiers locaux actualisés ({len(file_list)} éléments)", 3000)

    def on_local_load_error(self, path: str, error_msg: str) -> None:
        """Callback en cas d'erreur de chargement local"""
        if path == self.local_model.current_path:
            ErrorDialog.show_error("❌ Erreur", f"Impossible de lister les fichiers: {error_msg}", parent=self)

    def populate_local_model(self, file_list: List[Dict[str, Any]], from_cache: bool = False) -> None:
        """Remplit le modèle local avec les données stylées"""
        from PyQt5.QtGui import QStandardItem

        self.local_model.clear()
        self.local_model.setHorizontalHeaderLabels(["Nom", "Taille", "Date de modification", "Type", "Statut"])

        for file_info in file_list:
            if file_info['type'] == 'parent':
                name_item = QStandardItem("📁 ..")
                size_item = QStandardItem("")
                date_item = QStandardItem("")
                type_item = QStandardItem("📂 Dossier parent")
            elif file_info['is_dir']:
                name_item = QStandardItem(f"📁 {file_info['name']}")
                size_item = QStandardItem("")
                date_item = QStandardItem(format_date(file_info['modified']))
                type_item = QStandardItem("📂 Dossier")
            else:
                name_item = QStandardItem(f"📄 {file_info['name']}")
                size_item = QStandardItem(format_file_size(file_info['size']))
                date_item = QStandardItem(format_date(file_info['modified']))
                ext = os.path.splitext(file_info['name'])[1]
                type_item = QStandardItem(f"📄 {ext[1:].upper() if ext else 'Fichier'}")

            status_item = QStandardItem("📋 Cache" if from_cache else "✅ Frais")
            self.local_model.appendRow([name_item, size_item, date_item, type_item, status_item])

    # ==================== GESTION DE GOOGLE DRIVE ====================

    def refresh_drive_files(self, folder_id: Optional[str] = None) -> None:
        """Actualise la liste des fichiers Google Drive avec cache"""
        if not self.connected:
            return

        target_folder_id = folder_id if folder_id is not None else self.drive_model.current_path_id
        self.drive_model.current_path_id = target_folder_id

        # Déterminer le drive actuel
        if target_folder_id == 'root':
            self.drive_model.current_drive_id = 'root'
        else:
            self.drive_model.current_drive_id = self.drive_client.get_drive_id_from_folder(target_folder_id)

        # Vérifier le cache
        cached_data = self.cache_manager.get_drive_cache(target_folder_id)
        if cached_data:
            self.populate_drive_model(cached_data, from_cache=True)
            self.status_bar.showMessage("📋 Données du cache affichées - Actualisation en cours...", 2000)

        # Lancer le chargement en arrière-plan
        if self.drive_load_thread and self.drive_load_thread.isRunning():
            self.drive_load_thread.terminate()
            self.drive_load_thread.wait()

        self.drive_load_thread = DriveFileLoadThread(
            self.drive_client,
            target_folder_id,
            self.drive_model.path_history.copy()
        )
        self.drive_load_thread.files_loaded.connect(self.on_drive_files_loaded)
        self.drive_load_thread.error_occurred.connect(self.on_drive_load_error)
        self.drive_load_thread.start()

    def on_drive_files_loaded(self, folder_id: str, file_list: List[Dict[str, Any]]) -> None:
        """Callback quand les fichiers Google Drive sont chargés"""
        self.cache_manager.set_drive_cache(folder_id, file_list)
        if folder_id == self.drive_model.current_path_id:
            self.populate_drive_model(file_list, from_cache=False)
            self.status_bar.showMessage(f"✅ Fichiers Google Drive actualisés ({len(file_list)} éléments)", 3000)

    def on_drive_load_error(self, folder_id: str, error_msg: str) -> None:
        """Callback en cas d'erreur de chargement Google Drive"""
        if folder_id == self.drive_model.current_path_id:
            ErrorDialog.show_error("❌ Erreur", f"Impossible de lister les fichiers Drive: {error_msg}", parent=self)

    def populate_drive_model(self, file_list: List[Dict[str, Any]], from_cache: bool = False) -> None:
        """Remplit le modèle Google Drive avec les données stylées"""
        from PyQt5.QtGui import QStandardItem

        self.drive_model.clear()
        self.drive_model.setHorizontalHeaderLabels(["Nom", "Taille", "Date de modification", "Type", "ID", "Statut"])

        # Mettre à jour le label de chemin
        self.drive_path_label.setText(self.drive_model.get_path_string())

        for file_info in file_list:
            if file_info['type'] == 'parent':
                name_item = QStandardItem("📁 ..")
                size_item = QStandardItem("")
                date_item = QStandardItem("")
                type_item = QStandardItem("📂 Dossier parent")
                id_item = QStandardItem(file_info.get('id', ''))
            elif file_info['is_dir']:
                name_item = QStandardItem(f"📁 {file_info['name']}")
                size_item = QStandardItem("")
                type_item = QStandardItem("📂 Dossier")
                id_item = QStandardItem(file_info.get('id', ''))
            else:
                emoji = get_file_emoji(file_info.get('mimeType', ''))
                name_item = QStandardItem(f"{emoji} {file_info['name']}")
                size_item = QStandardItem(format_file_size(file_info.get('size', 0)))
                type_item = QStandardItem(get_file_type_description(file_info.get('mimeType', '')))
                id_item = QStandardItem(file_info.get('id', ''))

            date_item = QStandardItem(format_date(file_info.get('modified', '')))
            status_item = QStandardItem("📋 Cache" if from_cache else "✅ Frais")

            self.drive_model.appendRow([name_item, size_item, date_item, type_item, id_item, status_item])

    # ==================== ACTIONS DE LA BARRE D'OUTILS ====================

    def refresh_all(self) -> None:
        """Actualise les fichiers locaux et Google Drive"""
        self.refresh_local_files()
        if self.connected:
            self.refresh_drive_files()

    def clear_cache(self) -> None:
        """Vide le cache et actualise les vues"""
        self.cache_manager.clear_cache()
        self.status_bar.showMessage("🗑️ Cache vidé", 2000)
        self.refresh_all()

    def create_new_folder(self) -> None:
        """Crée un nouveau dossier"""
        focused_widget = QApplication.focusWidget()

        if focused_widget == self.local_view or self.local_view.hasFocus():
            dialog = CreateFolderDialog(self, "📁 Nouveau dossier")
            if dialog.exec_() == dialog.Accepted:
                folder_name = dialog.get_folder_name()
                if folder_name:
                    try:
                        new_path = os.path.join(self.local_model.current_path, folder_name)
                        os.makedirs(new_path, exist_ok=True)
                        self.cache_manager.invalidate_local_cache(self.local_model.current_path)
                        self.refresh_local_files()
                        self.status_bar.showMessage(f"✅ Dossier '{folder_name}' créé", 3000)
                    except Exception as e:
                        ErrorDialog.show_error("❌ Erreur", f"Impossible de créer le dossier: {str(e)}", parent=self)

        elif focused_widget == self.drive_view or self.drive_view.hasFocus():
            if not self.connected:
                ErrorDialog.show_error("❌ Non connecté", "Vous devez être connecté à Google Drive.", parent=self)
                return

            dialog = CreateFolderDialog(self, "📁 Nouveau dossier Drive")
            if dialog.exec_() == dialog.Accepted:
                folder_name = dialog.get_folder_name()
                if folder_name:
                    try:
                        parent_id = self.drive_model.current_path_id
                        is_shared_drive = self.drive_client.is_shared_drive(self.drive_model.current_drive_id)
                        folder_id = self.drive_client.create_folder(folder_name, parent_id, is_shared_drive)
                        self.cache_manager.invalidate_drive_cache(parent_id)
                        self.refresh_drive_files()
                        self.status_bar.showMessage(f"✅ Dossier Google Drive '{folder_name}' créé", 3000)
                    except Exception as e:
                        ErrorDialog.show_error("❌ Erreur", f"Impossible de créer le dossier: {str(e)}", parent=self)

    def show_search_dialog(self) -> None:
        """Affiche une boîte de dialogue pour rechercher des fichiers"""
        if not self.connected:
            ErrorDialog.show_error("❌ Non connecté",
                                   "Vous devez être connecté à Google Drive pour effectuer une recherche.",
                                   parent=self)
            return

        dialog = SearchDialog(self)
        if dialog.exec_() == dialog.Accepted:
            query = dialog.get_search_query()
            if query:
                self.perform_search(query)

    def perform_search(self, query: str) -> None:
        """Effectue une recherche dans Google Drive"""
        try:
            results = self.drive_client.search_files(query)
            if not results:
                self.status_bar.showMessage(f"🔍 Aucun résultat pour '{query}'", 5000)
                return

            # Afficher les résultats de recherche
            self.display_search_results(results, query)

        except Exception as e:
            ErrorDialog.show_error("❌ Erreur de recherche",
                                   f"Impossible d'effectuer la recherche: {str(e)}",
                                   parent=self)

    def display_search_results(self, results: List[Dict[str, Any]], query: str) -> None:
        """Affiche les résultats de recherche"""
        from PyQt5.QtGui import QStandardItem

        self.drive_model.clear()
        self.drive_model.setHorizontalHeaderLabels(["Nom", "Taille", "Date de modification", "Type", "ID", "Statut"])

        # Ajouter un élément pour revenir à la navigation normale
        name_item = QStandardItem("🔙 Retour à la navigation")
        size_item = QStandardItem("")
        date_item = QStandardItem("")
        type_item = QStandardItem("🔙 Navigation")
        id_item = QStandardItem("")
        status_item = QStandardItem("🔍 Recherche")
        self.drive_model.appendRow([name_item, size_item, date_item, type_item, id_item, status_item])

        # Ajouter les résultats
        for file in results:
            name = file.get('name', '')
            if file.get('mimeType') == 'application/vnd.google-apps.folder':
                name_item = QStandardItem(f"📁 {name}")
                type_item = QStandardItem("📂 Dossier")
                size_item = QStandardItem("")
            else:
                emoji = get_file_emoji(file.get('mimeType', ''))
                name_item = QStandardItem(f"{emoji} {name}")
                type_item = QStandardItem(get_file_type_description(file.get('mimeType', '')))
                size_item = QStandardItem(format_file_size(int(file.get('size', 0))))

            date_item = QStandardItem(format_date(file.get('modifiedTime', '')))
            id_item = QStandardItem(file.get('id', ''))
            status_item = QStandardItem("🔍 Recherche")

            self.drive_model.appendRow([name_item, size_item, date_item, type_item, id_item, status_item])

        self.status_bar.showMessage(f"🔍 {len(results)} résultat(s) pour '{query}'", 5000)

    # ==================== MENUS CONTEXTUELS ====================

    def show_local_context_menu(self, position):
        """Affiche un menu contextuel stylé pour les actions sur les fichiers locaux"""
        try:
            indexes = self.local_view.selectedIndexes()
            if not indexes:
                return

            rows = set(index.row() for index in indexes)
            if not rows:
                return

            menu = QMenu(self)

            if rows:
                upload_action = QAction("⬆️ Uploader vers Google Drive", self)
                upload_action.triggered.connect(self.upload_selected_files)
                upload_action.setEnabled(self.connected)
                menu.addAction(upload_action)
                menu.addSeparator()

            if len(rows) == 1:
                row = list(rows)[0]
                # Vérification de sécurité
                if row < self.local_model.rowCount() and self.local_model.item(row, 0):
                    name = self.local_model.item(row, 0).text()
                    clean_name = name.replace("📁 ", "").replace("📄 ", "")
                    if clean_name != "..":
                        rename_action = QAction("✏️ Renommer", self)
                        rename_action.triggered.connect(self.rename_selected)
                        menu.addAction(rename_action)

                        delete_action = QAction("🗑️ Supprimer", self)
                        delete_action.triggered.connect(self.delete_selected)
                        menu.addAction(delete_action)

                        menu.addSeparator()

                        # Actions supplémentaires
                        if os.path.isdir(os.path.join(self.local_model.current_path, clean_name)):
                            open_action = QAction("📂 Ouvrir dans l'Explorateur", self)
                            open_action.triggered.connect(lambda: self.open_in_explorer(clean_name))
                            menu.addAction(open_action)
                        else:
                            open_action = QAction("📄 Ouvrir le fichier", self)
                            open_action.triggered.connect(lambda: self.open_file(clean_name))
                            menu.addAction(open_action)

                        # Propriétés
                        properties_action = QAction("ℹ️ Propriétés", self)
                        properties_action.triggered.connect(self.show_local_file_properties)
                        menu.addAction(properties_action)

            menu.exec_(self.local_view.viewport().mapToGlobal(position))

        except Exception as e:
            print(f"Erreur dans show_local_context_menu: {e}")
            ErrorDialog.show_error("❌ Erreur", f"Erreur dans le menu contextuel: {str(e)}", parent=self)

    def show_drive_context_menu(self, position):
        """Affiche un menu contextuel stylé pour les actions sur les fichiers Google Drive"""
        try:
            if not self.connected:
                return

            indexes = self.drive_view.selectedIndexes()
            if not indexes:
                return

            rows = set(index.row() for index in indexes)
            if not rows:
                return

            menu = QMenu(self)

            if rows:
                download_action = QAction("⬇️ Télécharger", self)
                download_action.triggered.connect(self.download_selected_files)
                menu.addAction(download_action)
                menu.addSeparator()

            if len(rows) == 1:
                row = list(rows)[0]

                # Vérifications de sécurité
                if row >= self.drive_model.rowCount():
                    return

                # Vérifier que les éléments existent
                name_item = self.drive_model.item(row, 0)
                type_item = self.drive_model.item(row, 3)
                id_item = self.drive_model.item(row, 4)

                if not name_item or not type_item:
                    return

                name = name_item.text()
                clean_name = name.split(" ", 1)[1] if " " in name else name
                file_type = type_item.text()
                file_id = id_item.text() if id_item else ""

                if clean_name != ".." and "Retour à la navigation" not in clean_name:
                    rename_action = QAction("✏️ Renommer", self)
                    rename_action.triggered.connect(self.rename_selected)
                    menu.addAction(rename_action)

                    if "📂 Dossier" in file_type:
                        create_subfolder_action = QAction("📁 Créer un sous-dossier", self)
                        create_subfolder_action.triggered.connect(self.create_subfolder_selected)
                        menu.addAction(create_subfolder_action)

                    menu.addSeparator()

                    delete_action = QAction("🗑️ Mettre à la corbeille", self)
                    delete_action.triggered.connect(self.delete_selected)
                    menu.addAction(delete_action)

                    perm_delete_action = QAction("💥 Supprimer définitivement", self)
                    perm_delete_action.triggered.connect(self.permanently_delete_selected)
                    menu.addAction(perm_delete_action)

                    menu.addSeparator()

                    # Actions supplémentaires
                    share_action = QAction("🔗 Partager", self)
                    share_action.triggered.connect(self.share_selected_file)
                    menu.addAction(share_action)

                    details_action = QAction("ℹ️ Propriétés", self)
                    details_action.triggered.connect(self.show_file_details)
                    menu.addAction(details_action)

            menu.exec_(self.drive_view.viewport().mapToGlobal(position))

        except Exception as e:
            print(f"Erreur dans show_drive_context_menu: {e}")
            ErrorDialog.show_error("❌ Erreur", f"Erreur dans le menu contextuel Google Drive: {str(e)}", parent=self)

    # ==================== ACTIONS SUR LES FICHIERS ====================

    def upload_selected_files(self):
        """Upload les fichiers et dossiers sélectionnés vers Google Drive (version corrigée)"""
        try:
            if not self.connected:
                ErrorDialog.show_error("❌ Non connecté",
                                       "Vous devez être connecté à Google Drive pour uploader des fichiers.",
                                       parent=self)
                return

            indexes = self.local_view.selectedIndexes()
            if not indexes:
                return

            rows_names = set((index.row(), self.local_model.item(index.row(), 0).text())
                             for index in indexes if index.column() == 0 and self.local_model.item(index.row(), 0))
            items_to_upload = [(row, name.replace("📁 ", "").replace("📄 ", ""))
                               for row, name in rows_names if ".." not in name]

            if not items_to_upload:
                return

            destination_id = self.drive_model.current_path_id
            is_shared_drive = self.drive_client.is_shared_drive(self.drive_model.current_drive_id)

            # Compter les dossiers
            folder_count = sum(1 for row, name in items_to_upload
                               if os.path.isdir(os.path.join(self.local_model.current_path, name)))

            if folder_count > 0:
                upload_mode = 10  # Mode sécurisé par défaut
            else:
                upload_mode = 1

            for row, name in items_to_upload:
                item_path = os.path.join(self.local_model.current_path, name)

                if os.path.isfile(item_path):
                    # Upload de fichier simple
                    upload_thread = UploadThread(
                        self.drive_client, item_path, destination_id,
                        is_shared_drive, self.transfer_manager
                    )
                    upload_thread.progress_signal.connect(self.update_progress)
                    upload_thread.completed_signal.connect(self.upload_completed)
                    upload_thread.error_signal.connect(self.upload_error)
                    upload_thread.status_signal.connect(self.update_status)
                    upload_thread.time_signal.connect(self.update_upload_time)
                    self.upload_threads.append(upload_thread)
                    upload_thread.start()

                elif os.path.isdir(item_path):
                    # MODIFIÉ : Upload de dossier avec nouveau système
                    folder_upload_thread = SafeFolderUploadThread(
                        self.drive_client, item_path, destination_id,
                        is_shared_drive, self.transfer_manager,
                        max_parallel_uploads=upload_mode
                    )
                    folder_upload_thread.progress_signal.connect(self.update_progress)
                    folder_upload_thread.completed_signal.connect(self.folder_upload_completed)
                    folder_upload_thread.error_signal.connect(self.upload_error)
                    folder_upload_thread.status_signal.connect(self.update_status)
                    folder_upload_thread.time_signal.connect(self.update_upload_time)
                    self.folder_upload_threads.append(folder_upload_thread)
                    folder_upload_thread.start()

            # Afficher l'onglet des transferts
            self.show_transfers_tab()

        except Exception as e:
            print(f"Erreur dans upload_selected_files: {e}")
            ErrorDialog.show_error("❌ Erreur d'upload", f"Erreur lors de l'upload: {str(e)}", parent=self)

    def choose_upload_mode(self, folder_count: int) -> Optional[int]:
        """
        Permet à l'utilisateur de choisir le mode d'upload pour les dossiers

        Args:
            folder_count: Nombre de dossiers à uploader

        Returns:
            1 pour séquentiel, 2 pour parallèle limité, None si annulé
        """
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QRadioButton, QLabel, QDialogButtonBox, QGroupBox

        dialog = QDialog(self)
        dialog.setWindowTitle("🚀 Mode d'upload des dossiers")
        dialog.setModal(True)
        dialog.resize(400, 250)

        layout = QVBoxLayout()

        # Information
        info_label = QLabel(f"Vous allez uploader {folder_count} dossier(s).\nChoisissez le mode d'upload :")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        # Options
        group_box = QGroupBox("Mode d'upload")
        group_layout = QVBoxLayout()

        # Mode sécurisé (recommandé)
        safe_radio = QRadioButton("🛡️ Mode sécurisé (recommandé)")
        safe_radio.setChecked(True)
        safe_info = QLabel(
            "• Upload séquentiel (un fichier à la fois)\n• Plus lent mais très fiable\n• Aucun risque d'erreur SSL")
        safe_info.setStyleSheet("color: #888; margin-left: 20px; font-size: 9pt;")
        group_layout.addWidget(safe_radio)
        group_layout.addWidget(safe_info)

        # Mode rapide
        fast_radio = QRadioButton("⚡ Mode rapide")
        fast_info = QLabel(
            "• Upload parallèle limité (2 fichiers simultanés)\n• Plus rapide mais peut causer des erreurs\n• Risque d'erreurs SSL/timeout")
        fast_info.setStyleSheet("color: #888; margin-left: 20px; font-size: 9pt;")
        group_layout.addWidget(fast_radio)
        group_layout.addWidget(fast_info)

        group_box.setLayout(group_layout)
        layout.addWidget(group_box)

        # Boutons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)

        dialog.setLayout(layout)

        if dialog.exec_() == QDialog.Accepted:
            if safe_radio.isChecked():
                return 1  # Mode sécurisé
            else:
                return 2  # Mode rapide
        else:
            return None  # Annulé


    def download_selected_files(self):
        """Télécharge les fichiers sélectionnés depuis Google Drive"""
        try:
            indexes = self.drive_view.selectedIndexes()
            if not indexes:
                return

            rows_info = []
            for index in indexes:
                if index.column() == 0:
                    row = index.row()
                    if row < self.drive_model.rowCount():
                        name_item = self.drive_model.item(row, 0)
                        type_item = self.drive_model.item(row, 3)
                        id_item = self.drive_model.item(row, 4)
                        size_item = self.drive_model.item(row, 1)

                        if name_item and type_item and id_item:
                            # Récupérer la taille pour le calcul de vitesse
                            size_text = size_item.text() if size_item else ""
                            file_size = self.parse_file_size(size_text)

                            rows_info.append((row, name_item.text(), type_item.text(),
                                              id_item.text(), file_size))

            files_to_download = [(row, name.split(" ", 1)[1] if " " in name else name, file_id, file_size)
                                 for row, name, file_type, file_id, file_size in rows_info
                                 if
                                 ".." not in name and "📂 Dossier" not in file_type and "Retour à la navigation" not in name]

            if not files_to_download:
                return

            destination_dir = QFileDialog.getExistingDirectory(
                self, "📁 Choisir le dossier de destination", self.local_model.current_path)

            if not destination_dir:
                return

            for row, name, file_id, file_size in files_to_download:
                download_thread = DownloadThread(
                    self.drive_client, file_id, name, destination_dir,
                    file_size, self.transfer_manager
                )
                download_thread.progress_signal.connect(self.update_progress)
                download_thread.completed_signal.connect(self.download_completed)
                download_thread.error_signal.connect(self.download_error)
                download_thread.time_signal.connect(self.update_download_time)
                self.download_threads.append(download_thread)
                download_thread.start()

            # Afficher l'onglet des transferts
            self.show_transfers_tab()

            self.status_bar.showMessage(f"⬇️ Téléchargement de {len(files_to_download)} fichier(s)...")

        except Exception as e:
            print(f"Erreur dans download_selected_files: {e}")
            ErrorDialog.show_error("❌ Erreur de téléchargement", f"Erreur lors du téléchargement: {str(e)}",
                                   parent=self)

    def rename_selected(self):
        """Renomme l'élément sélectionné"""
        try:
            focused_widget = QApplication.focusWidget()

            if focused_widget == self.local_view or self.local_view.hasFocus():
                indexes = self.local_view.selectedIndexes()
                if not indexes:
                    return

                row = indexes[0].row()
                if row >= self.local_model.rowCount() or not self.local_model.item(row, 0):
                    return

                old_name = self.local_model.item(row, 0).text().replace("📁 ", "").replace("📄 ", "")

                if old_name == "..":
                    return

                dialog = RenameDialog(old_name, self)
                if dialog.exec_() == dialog.Accepted:
                    new_name = dialog.get_new_name()
                    if new_name and new_name != old_name:
                        old_path = os.path.join(self.local_model.current_path, old_name)
                        new_path = os.path.join(self.local_model.current_path, new_name)

                        try:
                            os.rename(old_path, new_path)
                            self.cache_manager.invalidate_local_cache(self.local_model.current_path)
                            self.refresh_local_files()
                            self.status_bar.showMessage(f"✅ '{old_name}' renommé en '{new_name}'", 3000)
                        except Exception as e:
                            ErrorDialog.show_error("❌ Erreur", f"Impossible de renommer: {str(e)}", parent=self)

            elif focused_widget == self.drive_view or self.drive_view.hasFocus():
                if not self.connected:
                    return

                indexes = self.drive_view.selectedIndexes()
                if not indexes:
                    return

                row = indexes[0].row()
                if row >= self.drive_model.rowCount():
                    return

                name_item = self.drive_model.item(row, 0)
                id_item = self.drive_model.item(row, 4)

                if not name_item or not id_item:
                    return

                old_name = name_item.text()
                clean_old_name = old_name.split(" ", 1)[1] if " " in old_name else old_name
                file_id = id_item.text()

                if clean_old_name == ".." or "Retour à la navigation" in clean_old_name:
                    return

                dialog = RenameDialog(clean_old_name, self)
                if dialog.exec_() == dialog.Accepted:
                    new_name = dialog.get_new_name()
                    if new_name and new_name != clean_old_name:
                        try:
                            self.drive_client.rename_item(file_id, new_name)
                            self.cache_manager.invalidate_drive_cache(self.drive_model.current_path_id)
                            self.refresh_drive_files()
                            self.status_bar.showMessage(f"✅ '{clean_old_name}' renommé en '{new_name}'", 3000)
                        except Exception as e:
                            ErrorDialog.show_error("❌ Erreur", f"Impossible de renommer: {str(e)}", parent=self)

        except Exception as e:
            print(f"Erreur dans rename_selected: {e}")
            ErrorDialog.show_error("❌ Erreur", f"Erreur lors du renommage: {str(e)}", parent=self)

    def delete_selected(self):
        """Supprime l'élément sélectionné"""
        try:
            focused_widget = QApplication.focusWidget()

            if focused_widget == self.local_view or self.local_view.hasFocus():
                indexes = self.local_view.selectedIndexes()
                if not indexes:
                    return

                rows_names = set((index.row(), self.local_model.item(index.row(), 0).text())
                                 for index in indexes if index.column() == 0 and self.local_model.item(index.row(), 0))
                items_to_delete = [(row, name.replace("📁 ", "").replace("📄 ", ""))
                                   for row, name in rows_names if ".." not in name]

                if not items_to_delete:
                    return

                item_count = len(items_to_delete)
                if item_count == 1:
                    message = f"🗑️ Voulez-vous vraiment supprimer '{items_to_delete[0][1]}'?"
                else:
                    message = f"🗑️ Voulez-vous vraiment supprimer ces {item_count} éléments?"

                if ConfirmationDialog.ask_confirmation("🗑️ Confirmation", message, self):
                    errors = []
                    for row, name in items_to_delete:
                        path = os.path.join(self.local_model.current_path, name)
                        try:
                            if os.path.isdir(path):
                                shutil.rmtree(path)
                            else:
                                os.remove(path)
                        except Exception as e:
                            errors.append(f"Impossible de supprimer '{name}': {str(e)}")

                    self.cache_manager.invalidate_local_cache(self.local_model.current_path)
                    self.refresh_local_files()

                    if errors:
                        ErrorDialog.show_error("❌ Erreurs de suppression", "\n".join(errors), parent=self)
                    else:
                        self.status_bar.showMessage(f"✅ {item_count} élément(s) supprimé(s)", 3000)

            elif focused_widget == self.drive_view or self.drive_view.hasFocus():
                if not self.connected:
                    return

                indexes = self.drive_view.selectedIndexes()
                if not indexes:
                    return

                rows_info = []
                for index in indexes:
                    if index.column() == 0:
                        row = index.row()
                        if row < self.drive_model.rowCount():
                            name_item = self.drive_model.item(row, 0)
                            id_item = self.drive_model.item(row, 4)
                            if name_item and id_item:
                                rows_info.append((row, name_item.text(), id_item.text()))

                items_to_delete = [(row, name.split(" ", 1)[1] if " " in name else name, file_id)
                                   for row, name, file_id in rows_info
                                   if ".." not in name and "Retour à la navigation" not in name]

                if not items_to_delete:
                    return

                item_count = len(items_to_delete)
                if item_count == 1:
                    message = f"🗑️ Voulez-vous vraiment mettre '{items_to_delete[0][1]}' à la corbeille?"
                else:
                    message = f"🗑️ Voulez-vous vraiment mettre ces {item_count} éléments à la corbeille?"

                if ConfirmationDialog.ask_confirmation("🗑️ Confirmation", message, self):
                    errors = []
                    for row, name, file_id in items_to_delete:
                        try:
                            self.drive_client.delete_item(file_id)
                        except Exception as e:
                            errors.append(f"Impossible de supprimer '{name}': {str(e)}")

                    self.cache_manager.invalidate_drive_cache(self.drive_model.current_path_id)
                    self.refresh_drive_files()

                    if errors:
                        ErrorDialog.show_error("❌ Erreurs de suppression", "\n".join(errors), parent=self)
                    else:
                        self.status_bar.showMessage(f"✅ {item_count} élément(s) mis à la corbeille", 3000)

        except Exception as e:
            print(f"Erreur dans delete_selected: {e}")
            ErrorDialog.show_error("❌ Erreur", f"Erreur lors de la suppression: {str(e)}", parent=self)

    def permanently_delete_selected(self):
        """Supprime définitivement l'élément sélectionné de Google Drive"""
        try:
            if not self.connected:
                return

            indexes = self.drive_view.selectedIndexes()
            if not indexes:
                return

            rows_info = []
            for index in indexes:
                if index.column() == 0:
                    row = index.row()
                    if row < self.drive_model.rowCount():
                        name_item = self.drive_model.item(row, 0)
                        id_item = self.drive_model.item(row, 4)
                        if name_item and id_item:
                            rows_info.append((row, name_item.text(), id_item.text()))

            items_to_delete = [(row, name.split(" ", 1)[1] if " " in name else name, file_id)
                               for row, name, file_id in rows_info
                               if ".." not in name and "Retour à la navigation" not in name]

            if not items_to_delete:
                return

            item_count = len(items_to_delete)
            if item_count == 1:
                message = (f"⚠️ ATTENTION: Voulez-vous vraiment supprimer définitivement '{items_to_delete[0][1]}'?\n\n"
                           "Cette action est irréversible et ne peut pas être annulée.")
            else:
                message = (f"⚠️ ATTENTION: Voulez-vous vraiment supprimer définitivement ces {item_count} éléments?\n\n"
                           "Cette action est irréversible et ne peut pas être annulée.")

            if ConfirmationDialog.ask_confirmation("💥 Suppression définitive", message, self):
                errors = []
                for row, name, file_id in items_to_delete:
                    try:
                        self.drive_client.permanently_delete_item(file_id)
                    except Exception as e:
                        errors.append(f"Impossible de supprimer définitivement '{name}': {str(e)}")

                self.cache_manager.invalidate_drive_cache(self.drive_model.current_path_id)
                self.refresh_drive_files()

                if errors:
                    ErrorDialog.show_error("❌ Erreurs de suppression", "\n".join(errors), parent=self)
                else:
                    self.status_bar.showMessage(f"💥 {item_count} élément(s) définitivement supprimé(s)", 3000)

        except Exception as e:
            print(f"Erreur dans permanently_delete_selected: {e}")
            ErrorDialog.show_error("❌ Erreur", f"Erreur lors de la suppression définitive: {str(e)}", parent=self)

    def create_subfolder_selected(self):
        """Crée un sous-dossier dans le dossier sélectionné"""
        try:
            if not self.connected:
                return

            indexes = self.drive_view.selectedIndexes()
            if not indexes:
                return

            row = indexes[0].row()
            if row >= self.drive_model.rowCount():
                return

            name_item = self.drive_model.item(row, 0)
            type_item = self.drive_model.item(row, 3)
            id_item = self.drive_model.item(row, 4)

            if not name_item or not type_item or not id_item:
                return

            folder_id = id_item.text()
            folder_name = name_item.text().split(" ", 1)[1] if " " in name_item.text() else name_item.text()
            folder_type = type_item.text()

            if ".." in folder_name or "📂 Dossier" not in folder_type:
                return

            dialog = CreateFolderDialog(self, f"📁 Nouveau sous-dossier dans '{folder_name}'")
            if dialog.exec_() == dialog.Accepted:
                subfolder_name = dialog.get_folder_name()
                if subfolder_name:
                    try:
                        is_shared_drive = self.drive_client.is_shared_drive(self.drive_model.current_drive_id)
                        subfolder_id = self.drive_client.create_folder(subfolder_name, folder_id, is_shared_drive)
                        self.cache_manager.invalidate_drive_cache(folder_id)
                        self.refresh_drive_files()
                        self.status_bar.showMessage(f"✅ Sous-dossier '{subfolder_name}' créé", 3000)
                    except Exception as e:
                        ErrorDialog.show_error("❌ Erreur", f"Impossible de créer le sous-dossier: {str(e)}", parent=self)

        except Exception as e:
            print(f"Erreur dans create_subfolder_selected: {e}")
            ErrorDialog.show_error("❌ Erreur", f"Erreur lors de la création du sous-dossier: {str(e)}", parent=self)

    def show_file_details(self):
        """Affiche les détails d'un fichier Google Drive"""
        try:
            if not self.connected:
                return

            indexes = self.drive_view.selectedIndexes()
            if not indexes:
                return

            row = indexes[0].row()
            if row >= self.drive_model.rowCount():
                return

            name_item = self.drive_model.item(row, 0)
            id_item = self.drive_model.item(row, 4)

            if not name_item or not id_item:
                return

            name = name_item.text()
            clean_name = name.split(" ", 1)[1] if " " in name else name
            file_id = id_item.text()

            if clean_name == ".." or "Retour à la navigation" in clean_name:
                return

            metadata = self.drive_client.get_file_metadata(file_id)
            dialog = FileDetailsDialog(metadata, self)
            dialog.exec_()

        except Exception as e:
            print(f"Erreur dans show_file_details: {e}")
            ErrorDialog.show_error("❌ Erreur", f"Impossible d'obtenir les détails: {str(e)}", parent=self)

    def show_local_file_properties(self):
        """Affiche les propriétés d'un fichier local"""
        try:
            indexes = self.local_view.selectedIndexes()
            if not indexes:
                return

            row = indexes[0].row()
            if row >= self.local_model.rowCount() or not self.local_model.item(row, 0):
                return

            name = self.local_model.item(row, 0).text()
            clean_name = name.replace("📁 ", "").replace("📄 ", "")

            if clean_name == "..":
                return

            file_path = os.path.join(self.local_model.current_path, clean_name)

            if os.path.exists(file_path):
                stats = os.stat(file_path)

                # Créer un dictionnaire de métadonnées similaire à Google Drive
                metadata = {
                    'name': clean_name,
                    'path': file_path,
                    'size': stats.st_size if os.path.isfile(file_path) else None,
                    'modifiedTime': format_date(stats.st_mtime),
                    'createdTime': format_date(stats.st_ctime),
                    'isDirectory': os.path.isdir(file_path),
                    'permissions': oct(stats.st_mode)[-3:],
                }

                # Utiliser une boîte de dialogue simple pour les propriétés locales
                from PyQt5.QtWidgets import QDialog, QVBoxLayout, QFormLayout, QDialogButtonBox

                dialog = QDialog(self)
                dialog.setWindowTitle(f"ℹ️ Propriétés: {clean_name}")
                dialog.resize(400, 300)

                layout = QVBoxLayout(dialog)
                form_layout = QFormLayout()

                form_layout.addRow("📄 Nom:", QLabel(metadata['name']))
                form_layout.addRow("📂 Chemin:", QLabel(metadata['path']))
                form_layout.addRow("🏷️ Type:", QLabel("📂 Dossier" if metadata['isDirectory'] else "📄 Fichier"))

                if metadata['size'] is not None:
                    form_layout.addRow("📏 Taille:", QLabel(format_file_size(metadata['size'])))

                form_layout.addRow("📅 Modifié:", QLabel(metadata['modifiedTime']))
                form_layout.addRow("🕐 Créé:", QLabel(metadata['createdTime']))
                form_layout.addRow("🔒 Permissions:", QLabel(metadata['permissions']))

                layout.addLayout(form_layout)

                button_box = QDialogButtonBox(QDialogButtonBox.Ok)
                button_box.accepted.connect(dialog.accept)
                layout.addWidget(button_box)

                dialog.exec_()

        except Exception as e:
            print(f"Erreur dans show_local_file_properties: {e}")
            ErrorDialog.show_error("❌ Erreur", f"Impossible d'obtenir les propriétés: {str(e)}", parent=self)

    def share_selected_file(self):
        """Partage un fichier Google Drive (fonctionnalité future)"""
        self.status_bar.showMessage("🔗 Fonctionnalité de partage à venir...", 3000)

    def open_in_explorer(self, folder_name):
        """Ouvre un dossier dans l'explorateur système"""
        try:
            folder_path = os.path.join(self.local_model.current_path, folder_name)

            if sys.platform == "win32":
                os.startfile(folder_path)
            elif sys.platform == "darwin":  # macOS
                subprocess.run(["open", folder_path])
            else:  # Linux et autres Unix
                subprocess.run(["xdg-open", folder_path])

        except Exception as e:
            print(f"Erreur dans open_in_explorer: {e}")
            ErrorDialog.show_error("❌ Erreur", f"Impossible d'ouvrir le dossier: {str(e)}", parent=self)

    def open_file(self, file_name):
        """Ouvre un fichier avec l'application par défaut"""
        try:
            file_path = os.path.join(self.local_model.current_path, file_name)

            if sys.platform == "win32":
                os.startfile(file_path)
            elif sys.platform == "darwin":  # macOS
                subprocess.run(["open", file_path])
            else:  # Linux et autres Unix
                subprocess.run(["xdg-open", file_path])

        except Exception as e:
            print(f"Erreur dans open_file: {e}")
            ErrorDialog.show_error("❌ Erreur", f"Impossible d'ouvrir le fichier: {str(e)}", parent=self)

    # ==================== NAVIGATION ====================

    def local_item_double_clicked(self, index) -> None:
        """Gère le double-clic sur un élément local"""
        if not index.isValid():
            return

        row = index.row()
        if row >= self.local_model.rowCount() or not self.local_model.item(row, 0):
            return

        name = self.local_model.item(row, 0).text()
        clean_name = name.replace("📁 ", "").replace("📄 ", "")

        if clean_name == "..":
            parent_dir = self.local_model.get_parent_path()
            self.local_path_edit.setText(parent_dir)
            self.change_local_path()
            return

        full_path = os.path.join(self.local_model.current_path, clean_name)
        if os.path.isdir(full_path):
            self.local_path_edit.setText(full_path)
            self.change_local_path()

    def drive_item_double_clicked(self, index) -> None:
        """Gère le double-clic sur un élément Google Drive"""
        if not index.isValid():
            return

        row = index.row()
        if row >= self.drive_model.rowCount():
            return

        name_item = self.drive_model.item(row, 0)
        type_item = self.drive_model.item(row, 3)
        id_item = self.drive_model.item(row, 4)

        if not name_item or not type_item or not id_item:
            return

        name = name_item.text()
        clean_name = name.split(" ", 1)[1] if " " in name else name
        type_str = type_item.text()
        file_id = id_item.text()

        if clean_name == "..":
            if self.drive_model.can_go_back():
                self.drive_model.go_back()
                self.refresh_drive_files(self.drive_model.current_path_id)
            return

        if "Retour à la navigation" in clean_name:
            self.refresh_drive_files()
            return

        if "📂 Dossier" in type_str:
            self.drive_model.navigate_to_folder(clean_name, file_id)
            self.refresh_drive_files(file_id)

    def drive_go_back(self) -> None:
        """Remonte d'un niveau dans Google Drive"""
        if self.drive_model.can_go_back():
            self.drive_model.go_back()
            self.refresh_drive_files(self.drive_model.current_path_id)

    def change_drive(self, index: int) -> None:
        """Change entre Mon Drive et les Shared Drives"""
        if not self.connected:
            return

        drive_id = self.drive_selector.currentData()
        self.drive_model.reset_to_root()
        self.drive_model.current_path_id = drive_id
        self.drive_model.current_drive_id = drive_id
        self.drive_model.path_history = [(self.drive_selector.currentText(), drive_id)]
        self.refresh_drive_files(drive_id)

    def browse_local_folder(self) -> None:
        """Ouvre un dialog pour choisir un dossier local"""
        folder = QFileDialog.getExistingDirectory(
            self, "📁 Choisir un dossier", self.local_path_edit.text())
        if folder:
            self.local_path_edit.setText(folder)
            self.change_local_path()

    def change_local_path(self) -> None:
        """Change le chemin local actuel"""
        new_path = self.local_path_edit.text()
        if os.path.isdir(new_path):
            self.refresh_local_files(new_path)
        else:
            ErrorDialog.show_error("❌ Chemin invalide",
                                   "Le chemin spécifié n'est pas un dossier valide.",
                                   parent=self)
            self.local_path_edit.setText(self.local_model.current_path)

    # ==================== GESTION DE LA CONNEXION ====================

    def disconnect_from_drive(self) -> None:
        """Se déconnecte de Google Drive"""
        if ConfirmationDialog.ask_confirmation(
                '🔌 Déconnexion',
                'Voulez-vous vraiment vous déconnecter de Google Drive?',
                self
        ):
            if self.drive_client:
                self.drive_client.disconnect()
            self.connected = False
            self.drive_client = None
            self.drive_model.clear()
            self.drive_model.setHorizontalHeaderLabels(
                ["Nom", "Taille", "Date de modification", "Type", "ID", "Statut"])
            self.drive_selector.clear()
            self.drive_selector.addItem("❌ Non connecté", "")
            self.status_bar.showMessage("🔌 Déconnecté de Google Drive", 3000)
            self.update_toolbar_state()

    def reconnect_to_drive(self) -> None:
        """Se reconnecte à Google Drive"""
        self.connect_to_drive()
        if self.connected:
            self.drive_selector.clear()
            self.drive_selector.addItem("☁️ Mon Drive", "root")
            try:
                for drive in self.drive_client.list_shared_drives():
                    self.drive_selector.addItem(f"🏢 {drive['name']}", drive['id'])
            except Exception as e:
                print(f"Erreur lors du chargement des Shared Drives: {e}")
            self.refresh_drive_files()
            self.status_bar.showMessage("🔗 Reconnecté à Google Drive", 3000)
        self.update_toolbar_state()

    # ==================== CALLBACKS POUR LES THREADS ====================

    def update_progress(self, value):
        """Met à jour la barre de progression"""
        self.progress_bar.setValue(value)
        self.progress_bar.setFormat(f"⏳ {value}%")

    def update_status(self, message):
        """Met à jour le message de statut"""
        self.status_bar.showMessage(message)

    def upload_completed(self, file_id):
        """Appelé lorsqu'un upload est terminé"""
        self.status_bar.showMessage("✅ Upload terminé avec succès", 3000)
        self.cache_manager.invalidate_drive_cache(self.drive_model.current_path_id)
        self.refresh_drive_files()

    def folder_upload_completed(self, folder_id):
        """Appelé lorsqu'un upload de dossier est terminé"""
        self.progress_bar.setVisible(False)
        self.status_bar.showMessage("✅ Upload de dossier terminé avec succès", 3000)
        self.cache_manager.invalidate_drive_cache(self.drive_model.current_path_id)
        self.refresh_drive_files()

    def upload_error(self, error_msg):
        """Appelé lorsqu'une erreur se produit pendant l'upload"""
        self.progress_bar.setVisible(False)
        self.status_bar.showMessage(f"❌ Erreur d'upload: {error_msg}", 5000)
        ErrorDialog.show_error("❌ Erreur d'upload", f"Une erreur s'est produite: {error_msg}", parent=self)

    def download_completed(self, file_path):
        """Appelé lorsqu'un téléchargement est terminé"""
        self.status_bar.showMessage(f"✅ Téléchargement terminé: {os.path.basename(file_path)}", 3000)
        if os.path.dirname(file_path) == self.local_model.current_path:
            self.cache_manager.invalidate_local_cache(self.local_model.current_path)
            self.refresh_local_files()

    def download_error(self, error_msg):
        """Appelé lorsqu'une erreur se produit pendant le téléchargement"""
        self.progress_bar.setVisible(False)
        self.status_bar.showMessage(f"❌ Erreur de téléchargement: {error_msg}", 5000)
        ErrorDialog.show_error("❌ Erreur de téléchargement", f"Une erreur s'est produite: {error_msg}", parent=self)

    def update_upload_time(self, time_taken):
        """Met à jour le temps d'upload dans la barre de statut"""
        self.status_bar.showMessage(f"⚡ Upload terminé en {time_taken:.2f} secondes", 5000)

    def update_download_time(self, time_taken):
        """Met à jour le temps de téléchargement dans la barre de statut"""
        self.status_bar.showMessage(f"⚡ Téléchargement terminé en {time_taken:.2f} secondes", 5000)

    # ==================== DRAG & DROP ====================

    def handle_local_files_dropped(self, file_paths):
        """Gère les fichiers déposés dans la vue locale"""
        try:
            destination_folder = self.local_model.current_path

            if ConfirmationDialog.ask_confirmation(
                    '📋 Copier les fichiers',
                    f'Voulez-vous copier {len(file_paths)} fichier(s) vers {destination_folder}?',
                    self
            ):
                errors = []
                copied_count = 0

                for file_path in file_paths:
                    try:
                        if os.path.isfile(file_path):
                            filename = os.path.basename(file_path)
                            destination_path = os.path.join(destination_folder, filename)
                            shutil.copy2(file_path, destination_path)
                            copied_count += 1
                        elif os.path.isdir(file_path):
                            folder_name = os.path.basename(file_path)
                            destination_path = os.path.join(destination_folder, folder_name)
                            shutil.copytree(file_path, destination_path, dirs_exist_ok=True)
                            copied_count += 1
                    except Exception as e:
                        errors.append(f"Erreur lors de la copie de {os.path.basename(file_path)}: {str(e)}")

                if errors:
                    ErrorDialog.show_error("❌ Erreurs de copie", "\n".join(errors), parent=self)

                if copied_count > 0:
                    self.status_bar.showMessage(f"✅ {copied_count} élément(s) copié(s)", 3000)
                    self.cache_manager.invalidate_local_cache(destination_folder)
                    self.refresh_local_files()

        except Exception as e:
            print(f"Erreur dans handle_local_files_dropped: {e}")
            ErrorDialog.show_error("❌ Erreur", f"Erreur lors du glisser-déposer: {str(e)}", parent=self)

    def handle_drive_files_dropped(self, file_paths):
        """Gère les fichiers déposés dans la vue Google Drive"""
        try:
            if not self.connected:
                ErrorDialog.show_error("❌ Non connecté",
                                       "Vous devez être connecté à Google Drive pour uploader des fichiers.",
                                       parent=self)
                return

            if not file_paths:
                return

            if ConfirmationDialog.ask_confirmation(
                    '⬆️ Upload vers Google Drive',
                    f'Voulez-vous uploader {len(file_paths)} fichier(s)/dossier(s) vers Google Drive?',
                    self
            ):
                self.upload_files_list(file_paths)

        except Exception as e:
            print(f"Erreur dans handle_drive_files_dropped: {e}")
            ErrorDialog.show_error("❌ Erreur", f"Erreur lors du glisser-déposer: {str(e)}", parent=self)

    def upload_files_list(self, file_paths):
        """Upload une liste de fichiers/dossiers vers Google Drive (version corrigée)"""
        try:
            if not self.connected:
                return

            destination_id = self.drive_model.current_path_id
            is_shared_drive = self.drive_client.is_shared_drive(self.drive_model.current_drive_id)

            # Compter les dossiers pour choisir le mode
            folder_count = sum(1 for path in file_paths if os.path.isdir(path))

            if folder_count > 0:
                upload_mode = 10  # Mode sécurisé par défaut
            else:
                upload_mode = 1

            for file_path in file_paths:
                if os.path.isfile(file_path):
                    upload_thread = UploadThread(
                        self.drive_client, file_path, destination_id,
                        is_shared_drive, self.transfer_manager
                    )
                    upload_thread.progress_signal.connect(self.update_progress)
                    upload_thread.completed_signal.connect(self.upload_completed)
                    upload_thread.error_signal.connect(self.upload_error)
                    upload_thread.status_signal.connect(self.update_status)
                    upload_thread.time_signal.connect(self.update_upload_time)
                    self.upload_threads.append(upload_thread)
                    upload_thread.start()

                elif os.path.isdir(file_path):
                    # MODIFIÉ : Upload de dossier avec nouveau système
                    folder_upload_thread = SafeFolderUploadThread(
                        self.drive_client, file_path, destination_id,
                        is_shared_drive, self.transfer_manager,
                        max_parallel_uploads=upload_mode
                    )
                    folder_upload_thread.progress_signal.connect(self.update_progress)
                    folder_upload_thread.completed_signal.connect(self.folder_upload_completed)
                    folder_upload_thread.error_signal.connect(self.upload_error)
                    folder_upload_thread.status_signal.connect(self.update_status)
                    folder_upload_thread.time_signal.connect(self.update_upload_time)
                    self.folder_upload_threads.append(folder_upload_thread)
                    folder_upload_thread.start()

            # Afficher l'onglet des transferts
            self.show_transfers_tab()

            mode_text = "sécurisé" if upload_mode == 1 else "rapide"
            self.status_bar.showMessage(f"🚀 Upload de {len(file_paths)} élément(s) en mode {mode_text}...")

        except Exception as e:
            print(f"Erreur dans upload_files_list: {e}")
            ErrorDialog.show_error("❌ Erreur d'upload", f"Erreur lors de l'upload: {str(e)}", parent=self)

    def toggle_safe_mode(self):
        """Bascule entre mode sécurisé et mode rapide par défaut"""
        self.SAFE_MODE = not self.SAFE_MODE
        self.MAX_PARALLEL_UPLOADS = 1 if self.SAFE_MODE else 2

        mode_text = "sécurisé" if self.SAFE_MODE else "rapide"
        self.status_bar.showMessage(f"🔄 Mode d'upload par défaut: {mode_text}", 3000)


    # ========= MÉTHODES POUR GÉRER LES TRANSFERTS =========

    def cancel_transfer(self, transfer_id: str) -> None:
        """Annule un transfert"""
        # Trouver et annuler le thread correspondant
        for thread_list in [self.upload_threads, self.download_threads, self.folder_upload_threads]:
            for thread in thread_list:
                if hasattr(thread, 'transfer_id') and thread.transfer_id == transfer_id:
                    thread.cancel()
                    break

    def pause_transfer(self, transfer_id: str) -> None:
        """Suspend un transfert (fonctionnalité future)"""
        # Pour l'instant, juste mettre à jour le statut
        pass

    def resume_transfer(self, transfer_id: str) -> None:
        """Reprend un transfert suspendu (fonctionnalité future)"""
        # Pour l'instant, juste mettre à jour le statut
        pass

    def clear_completed_transfers(self) -> None:
        """Supprime tous les transferts terminés"""
        self.transfer_manager.clear_completed_transfers()
        self.status_bar.showMessage("🧹 Transferts terminés supprimés", 2000)

    # === MÉTHODES UTILITAIRES ===

    def parse_file_size(self, size_text: str) -> int:
        """
        Parse une taille de fichier formatée en bytes

        Args:
            size_text: Texte de taille (ex: "1.5 MB")

        Returns:
            Taille en bytes
        """
        if not size_text or size_text == "":
            return 0

        try:
            parts = size_text.split()
            if len(parts) != 2:
                return 0

            value = float(parts[0])
            unit = parts[1].upper()

            multipliers = {
                'B': 1,
                'KB': 1024,
                'MB': 1024 * 1024,
                'GB': 1024 * 1024 * 1024,
                'TB': 1024 * 1024 * 1024 * 1024
            }

            return int(value * multipliers.get(unit, 1))
        except:
            return 0
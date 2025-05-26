"""
Fenêtre principale de l'application Google Drive Explorer
"""

import os
import shutil
from typing import List, Dict, Any, Optional
from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QPushButton, QLabel, QFileDialog, QMessageBox,
                             QMenu, QAction, QSplitter, QToolBar, QStatusBar,
                             QProgressBar, QLineEdit, QComboBox, QApplication)
from PyQt5.QtCore import Qt, QSize, QTimer, pyqtSignal
from PyQt5.QtGui import QKeySequence

from config.settings import (WINDOW_TITLE, WINDOW_WIDTH, WINDOW_HEIGHT,
                             TOOLBAR_ICON_SIZE, CACHE_CLEANUP_INTERVAL_MS)
from core.cache_manager import CacheManager
from core.google_drive_client import GoogleDriveClient
from threads.file_load_threads import LocalFileLoadThread, DriveFileLoadThread
from threads.transfer_threads import UploadThread, FolderUploadThread, DownloadThread
from models.file_models import FileListModel, LocalFileModel
from views.tree_views import LocalTreeView, DriveTreeView
from views.dialogs import (SearchDialog, FileDetailsDialog, RenameDialog,
                           CreateFolderDialog, ConfirmationDialog, ErrorDialog)
from utils.helpers import (format_file_size, get_file_emoji, get_file_type_description,
                           format_date, sanitize_filename)


class DriveExplorerMainWindow(QMainWindow):
    """Fenêtre principale de l'application avec cache, threading et style moderne"""

    def __init__(self):
        """Initialise la fenêtre principale"""
        super().__init__()

        # Initialiser les composants principaux
        self.setup_core_components()

        # Configuration de la fenêtre
        self.setWindowTitle(WINDOW_TITLE)
        self.resize(WINDOW_WIDTH, WINDOW_HEIGHT)

        # Créer l'interface utilisateur
        self.setup_ui()

        # Connecter les signaux
        self.connect_signals()

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
        except Exception as e:
            self.connected = False
            ErrorDialog.show_error(
                "❌ Erreur de connexion",
                f"Impossible de se connecter à Google Drive: {str(e)}",
                parent=self
            )

    def setup_ui(self) -> None:
        """Configure l'interface utilisateur avec style moderne"""
        # Widget central
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)

        # Barre d'outils et statut
        self.create_toolbar()
        self.create_status_bar()

        # Layout principal
        main_layout = QVBoxLayout()

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

        main_layout.addWidget(self.splitter)

        # Barre de progression
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(True)
        main_layout.addWidget(self.progress_bar)

        self.central_widget.setLayout(main_layout)

        # Raccourcis clavier
        self.setup_shortcuts()

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
            for drive in self.drive_client.list_shared_drives():
                self.drive_selector.addItem(f"🏢 {drive['name']}", drive['id'])

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

    def update_toolbar_state(self) -> None:
        """Met à jour l'état des boutons selon la connexion"""
        self.search_action.setEnabled(self.connected)
        self.disconnect_action.setEnabled(self.connected)
        self.reconnect_action.setEnabled(not self.connected)

    # Méthodes de gestion des fichiers locaux
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

    # Méthodes de gestion de Google Drive
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
            elif file_info['is_dir']:
                name_item = QStandardItem(f"📁 {file_info['name']}")
                size_item = QStandardItem("")
                type_item = QStandardItem("📂 Dossier")
            else:
                emoji = get_file_emoji(file_info['mimeType'])
                name_item = QStandardItem(f"{emoji} {file_info['name']}")
                size_item = QStandardItem(format_file_size(file_info['size']))
                type_item = QStandardItem(get_file_type_description(file_info['mimeType']))

            date_item = QStandardItem(format_date(file_info['modified']))
            id_item = QStandardItem(file_info['id'])
            status_item = QStandardItem("📋 Cache" if from_cache else "✅ Frais")

            self.drive_model.appendRow([name_item, size_item, date_item, type_item, id_item, status_item])

    # Actions de la barre d'outils
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

    # Navigation
    def local_item_double_clicked(self, index) -> None:
        """Gère le double-clic sur un élément local"""
        if not index.isValid():
            return

        name = self.local_model.item(index.row(), 0).text()
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
        name = self.drive_model.item(row, 0).text()
        clean_name = name.split(" ", 1)[1] if " " in name else name
        type_str = self.drive_model.item(row, 3).text()
        file_id = self.drive_model.item(row, 4).text()

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

    # Gestion de la connexion
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
            for drive in self.drive_client.list_shared_drives():
                self.drive_selector.addItem(f"🏢 {drive['name']}", drive['id'])
            self.refresh_drive_files()
            self.status_bar.showMessage("🔗 Reconnecté à Google Drive", 3000)
        self.update_toolbar_state()

    # Méthodes contextuelles (seront ajoutées dans la prochaine partie)
    def show_local_context_menu(self, position) -> None:
        """Affiche le menu contextuel pour les fichiers locaux"""
        pass  # À implémenter

    def show_drive_context_menu(self, position) -> None:
        """Affiche le menu contextuel pour Google Drive"""
        pass  # À implémenter

    def rename_selected(self) -> None:
        """Renomme l'élément sélectionné"""
        pass  # À implémenter

    def delete_selected(self) -> None:
        """Supprime l'élément sélectionné"""
        pass  # À implémenter

    def handle_local_files_dropped(self, file_paths: List[str]) -> None:
        """Gère les fichiers déposés dans la vue locale"""
        pass  # À implémenter

    def handle_drive_files_dropped(self, file_paths: List[str]) -> None:
        """Gère les fichiers déposés dans la vue Google Drive"""
        pass  # À implémenter

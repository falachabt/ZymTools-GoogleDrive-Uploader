"""
Google Drive Explorer Avancé avec fonctionnalités modernes
- Interface double-panneau (style FileZilla)
- Support des Shared Drives
- Barres de progression pour téléchargements/uploads
- Navigation avancée et multiples options
"""

import os
import sys
import io
import pickle
import time
import threading
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
                            QFormLayout, QInputDialog, QShortcut)
from PyQt5.QtCore import Qt, QSize, QMimeData, QUrl, pyqtSignal, QThread, QModelIndex, QDir
from PyQt5.QtGui import QStandardItemModel, QStandardItem, QIcon, QKeySequence
from functools import partial

# Définir les scopes de l'API Google Drive
SCOPES = ['https://www.googleapis.com/auth/drive']


def resource_path(relative_path):
    """Obtient le chemin absolu vers une ressource, fonctionne pour dev et PyInstaller"""
    try:
        # PyInstaller crée un répertoire temporaire et stocke le chemin dans _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

class UploadThread(QThread):
    """Thread pour uploader les fichiers en arrière-plan"""
    # Signaux pour la mise à jour de la progression
    progress_signal = pyqtSignal(int)
    completed_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)

    def __init__(self, drive_client, file_path, parent_id='root'):
        super().__init__()
        self.drive_client = drive_client
        self.file_path = file_path
        self.parent_id = parent_id
        self.file_size = os.path.getsize(file_path)

    def run(self):
        """Méthode exécutée lors du démarrage du thread"""
        try:
            file_id = self.drive_client.upload_file(self.file_path, self.parent_id, self.progress_signal)
            self.completed_signal.emit(file_id)
        except Exception as e:
            self.error_signal.emit(str(e))

class DownloadThread(QThread):
    """Thread pour télécharger les fichiers en arrière-plan"""
    # Signaux pour la mise à jour de la progression
    progress_signal = pyqtSignal(int)
    completed_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)

    def __init__(self, drive_client, file_id, file_name, local_dir):
        super().__init__()
        self.drive_client = drive_client
        self.file_id = file_id
        self.file_name = file_name
        self.local_dir = local_dir

    def run(self):
        """Méthode exécutée lors du démarrage du thread"""
        try:
            file_path = self.drive_client.download_file(self.file_id, self.file_name, self.local_dir, self.progress_signal)
            self.completed_signal.emit(file_path)
        except Exception as e:
            self.error_signal.emit(str(e))

class GoogleDriveClient:
    """Classe pour gérer les interactions avec l'API Google Drive"""

    def __init__(self):
        """Initialise la connexion à Google Drive"""
        self.service = self._get_drive_service()

    def _get_drive_service(self):
        """Authentifie et crée le service Google Drive"""
        creds = None

        # Cherche le token existant
        token_path = resource_path('token.pickle')
        if os.path.exists(token_path):
            with open(token_path, 'rb') as token:
                creds = pickle.load(token)

        # Si pas de credentials valides, demande à l'utilisateur de se connecter
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                credentials_path = resource_path('credentials.json')
                flow = InstalledAppFlow.from_client_secrets_file(
                    credentials_path, SCOPES)
                creds = flow.run_local_server(port=0)

            # Sauvegarde le token pour la prochaine fois
            # Sauvegarder dans le répertoire courant car on ne peut pas écrire dans _MEIPASS
            with open('token.pickle', 'wb') as token:
                pickle.dump(creds, token)

        # Retourne le service Google Drive
        return build('drive', 'v3', credentials=creds)

    def list_files(self, parent_id='root'):
        """Liste les fichiers dans Google Drive"""
        query = f"'{parent_id}' in parents and trashed=false"
        results = self.service.files().list(
            q=query,
            pageSize=100,
            fields="nextPageToken, files(id, name, mimeType, size, modifiedTime)"
        ).execute()

        return results.get('files', [])

    def list_shared_drives(self):
        """Liste les Shared Drives disponibles"""
        try:
            results = self.service.drives().list(
                pageSize=50
            ).execute()
            return results.get('drives', [])
        except Exception as e:
            print(f"Erreur lors du listage des Shared Drives: {str(e)}")
            return []

    def search_files(self, query_string):
        """Recherche des fichiers par nom"""
        query = f"name contains '{query_string}' and trashed=false"
        results = self.service.files().list(
            q=query,
            pageSize=100,
            fields="nextPageToken, files(id, name, mimeType, size, modifiedTime, parents)"
        ).execute()

        return results.get('files', [])

    def get_file_metadata(self, file_id):
        """Récupère les métadonnées d'un fichier"""
        return self.service.files().get(
            fileId=file_id,
            fields="id, name, mimeType, size, modifiedTime, parents, description"
        ).execute()

    def download_file(self, file_id, file_name, local_dir, progress_callback=None):
        """Télécharge un fichier depuis Google Drive avec progression"""
        request = self.service.files().get_media(fileId=file_id)

        file_path = os.path.join(local_dir, file_name)

        with open(file_path, 'wb') as f:
            downloader = MediaIoBaseDownload(f, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()
                if progress_callback:
                    progress_callback.emit(int(status.progress() * 100))

        return file_path

    def upload_file(self, file_path, parent_id='root', progress_callback=None):
        """Upload un fichier vers Google Drive avec progression"""
        file_name = os.path.basename(file_path)
        file_metadata = {
            'name': file_name,
            'parents': [parent_id]
        }

        # Utiliser un chunksize approprié pour permettre la mise à jour de la progression
        chunksize = 1024 * 1024  # 1MB

        media = MediaFileUpload(
            file_path,
            resumable=True,
            chunksize=chunksize
        )

        # Créer la requête mais ne pas l'exécuter immédiatement
        request = self.service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id'
        )

        # Exécuter la requête avec mise à jour de la progression
        response = None
        file_size = os.path.getsize(file_path)
        uploaded = 0

        while response is None:
            status, response = request.next_chunk()
            if status:
                uploaded += chunksize
                progress = min(int((uploaded / file_size) * 100), 100)
                if progress_callback:
                    progress_callback.emit(progress)

        return response.get('id')

    def create_folder(self, folder_name, parent_id='root'):
        """Crée un nouveau dossier dans Google Drive"""
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
        """Renomme un fichier ou dossier"""
        file_metadata = {'name': new_name}

        updated_file = self.service.files().update(
            fileId=file_id,
            body=file_metadata,
            fields='id, name'
        ).execute()

        return updated_file

    def delete_item(self, file_id):
        """Supprime un fichier ou dossier (met à la corbeille)"""
        self.service.files().update(
            fileId=file_id,
            body={'trashed': True}
        ).execute()

    def permanently_delete_item(self, file_id):
        """Supprime définitivement un fichier ou dossier"""
        self.service.files().delete(fileId=file_id).execute()

class FileListModel(QStandardItemModel):
    """Modèle personnalisé pour les listes de fichiers avec plus d'informations"""

    def __init__(self, headers):
        super().__init__()
        self.setHorizontalHeaderLabels(headers)
        self.current_path_id = 'root'
        self.path_history = [('Racine', 'root')]  # Historique de navigation (nom, id)

class LocalFileModel(QStandardItemModel):
    """Modèle pour les fichiers locaux"""

    def __init__(self, headers):
        super().__init__()
        self.setHorizontalHeaderLabels(headers)
        self.current_path = os.path.expanduser("~")  # Commencer dans le dossier utilisateur

class DriveExplorerWindow(QMainWindow):
    """Fenêtre principale de l'application"""

    def __init__(self):
        super().__init__()

        # Initialiser le client Google Drive
        try:
            self.drive_client = GoogleDriveClient()
            self.connected = True

            # Charger les Shared Drives
            self.shared_drives = self.drive_client.list_shared_drives()
        except Exception as e:
            self.connected = False
            QMessageBox.critical(self, "Erreur de connexion",
                                 f"Impossible de se connecter à Google Drive: {str(e)}")
            self.shared_drives = []

        # Initialiser les variables pour les uploads et téléchargements
        self.upload_threads = []
        self.download_threads = []

        # Configuration de la fenêtre
        self.setWindowTitle("Google Drive Explorer Avancé")
        self.resize(1200, 800)

        # Créer le widget central
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)

        # Créer la barre d'outils
        self.create_toolbar()

        # Créer la barre de statut
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        # Créer le layout principal
        main_layout = QVBoxLayout()

        # Créer un splitter pour diviser l'écran
        self.splitter = QSplitter(Qt.Horizontal)

        # Partie gauche - Système local
        local_widget = QWidget()
        local_layout = QVBoxLayout(local_widget)

        # Chemin local
        local_path_layout = QHBoxLayout()
        local_path_layout.addWidget(QLabel("Chemin local:"))
        self.local_path_edit = QLineEdit(os.path.expanduser("~"))
        self.local_path_edit.returnPressed.connect(self.change_local_path)
        local_path_layout.addWidget(self.local_path_edit)
        local_layout.addLayout(local_path_layout)

        # Vue des fichiers locaux
        self.local_model = LocalFileModel(["Nom", "Taille", "Date de modification", "Type"])

        self.local_view = QTreeView()
        self.local_view.setModel(self.local_model)
        self.local_view.setSelectionMode(QTreeView.ExtendedSelection)
        self.local_view.doubleClicked.connect(self.local_item_double_clicked)
        self.local_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.local_view.customContextMenuRequested.connect(self.show_local_context_menu)
        self.local_view.setDragEnabled(True)
        self.local_view.setAcceptDrops(True)
        self.local_view.setColumnWidth(0, 250)
        local_layout.addWidget(self.local_view)

        # Partie droite - Google Drive
        drive_widget = QWidget()
        drive_layout = QVBoxLayout(drive_widget)

        # Sélecteur de Drive
        drive_selector_layout = QHBoxLayout()
        drive_selector_layout.addWidget(QLabel("Drive:"))
        self.drive_selector = QComboBox()
        self.drive_selector.addItem("Mon Drive", "root")

        # Ajouter les Shared Drives
        for drive in self.shared_drives:
            self.drive_selector.addItem(drive['name'], drive['id'])

        self.drive_selector.currentIndexChanged.connect(self.change_drive)
        drive_selector_layout.addWidget(self.drive_selector)

        drive_layout.addLayout(drive_selector_layout)

        # Navigation Google Drive
        drive_path_layout = QHBoxLayout()
        self.drive_back_btn = QPushButton("←")
        self.drive_back_btn.setFixedWidth(30)
        self.drive_back_btn.clicked.connect(self.drive_go_back)
        drive_path_layout.addWidget(self.drive_back_btn)

        self.drive_path_label = QLabel("Racine")
        drive_path_layout.addWidget(self.drive_path_label, 1)

        self.drive_refresh_btn = QPushButton("⟳")
        self.drive_refresh_btn.setFixedWidth(30)
        self.drive_refresh_btn.clicked.connect(self.refresh_drive_files)
        drive_path_layout.addWidget(self.drive_refresh_btn)

        drive_layout.addLayout(drive_path_layout)

        # Vue des fichiers Google Drive
        self.drive_model = FileListModel(["Nom", "Taille", "Date de modification", "Type", "ID"])

        self.drive_view = QTreeView()
        self.drive_view.setModel(self.drive_model)
        self.drive_view.setSelectionMode(QTreeView.ExtendedSelection)
        self.drive_view.doubleClicked.connect(self.drive_item_double_clicked)
        self.drive_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.drive_view.customContextMenuRequested.connect(self.show_drive_context_menu)
        self.drive_view.setDragEnabled(True)
        self.drive_view.setAcceptDrops(True)
        self.drive_view.setColumnWidth(0, 250)
        self.drive_view.setColumnHidden(4, True)  # Cacher la colonne ID
        drive_layout.addWidget(self.drive_view)

        # Ajouter les widgets au splitter
        self.splitter.addWidget(local_widget)
        self.splitter.addWidget(drive_widget)
        self.splitter.setSizes([int(self.width() * 0.4), int(self.width() * 0.6)])

        main_layout.addWidget(self.splitter)

        # Barre de progression
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        main_layout.addWidget(self.progress_bar)

        self.central_widget.setLayout(main_layout)

        # Raccourcis clavier
        QShortcut(QKeySequence("F5"), self, self.refresh_all)
        QShortcut(QKeySequence("F2"), self, self.rename_selected)
        QShortcut(QKeySequence("Delete"), self, self.delete_selected)
        QShortcut(QKeySequence("Ctrl+F"), self, self.show_search_dialog)

        # Charger les fichiers au démarrage
        self.refresh_local_files()
        if self.connected:
            self.refresh_drive_files()

    def create_toolbar(self):
        """Crée la barre d'outils avec les actions principales"""
        self.toolbar = QToolBar("Actions")
        self.toolbar.setIconSize(QSize(24, 24))

        # Action de rafraîchissement
        refresh_action = QAction("Actualiser", self)
        refresh_action.triggered.connect(self.refresh_all)
        self.toolbar.addAction(refresh_action)

        self.toolbar.addSeparator()

        # Action pour créer un dossier
        new_folder_action = QAction("Nouveau dossier", self)
        new_folder_action.triggered.connect(self.create_new_folder)
        self.toolbar.addAction(new_folder_action)

        # Action pour rechercher
        search_action = QAction("Rechercher", self)
        search_action.triggered.connect(self.show_search_dialog)
        self.toolbar.addAction(search_action)

        self.addToolBar(self.toolbar)

    def refresh_all(self):
        """Actualise les fichiers locaux et Google Drive"""
        self.refresh_local_files()
        self.refresh_drive_files()

    def refresh_local_files(self):
        """Actualise la liste des fichiers locaux"""
        self.local_model.clear()
        self.local_model.setHorizontalHeaderLabels(["Nom", "Taille", "Date de modification", "Type"])

        # Obtenir le chemin actuel
        current_path = self.local_path_edit.text()
        if not os.path.isdir(current_path):
            current_path = os.path.expanduser("~")
            self.local_path_edit.setText(current_path)

        self.local_model.current_path = current_path

        # Ajouter l'élément "Remonter"
        if current_path != os.path.dirname(current_path):
            name_item = QStandardItem("..")
            name_item.setData(QIcon.fromTheme("folder"), Qt.DecorationRole)
            size_item = QStandardItem("")
            date_item = QStandardItem("")
            type_item = QStandardItem("Dossier parent")
            self.local_model.appendRow([name_item, size_item, date_item, type_item])

        # Lister les dossiers d'abord
        try:
            items = []
            for item in os.listdir(current_path):
                item_path = os.path.join(current_path, item)
                try:
                    stats = os.stat(item_path)
                    is_dir = os.path.isdir(item_path)

                    # Mettre les dossiers en premier
                    items.append((item, stats, is_dir))
                except Exception:
                    pass

            # Trier: dossiers d'abord, puis par nom
            items.sort(key=lambda x: (not x[2], x[0].lower()))

            for item, stats, is_dir in items:
                name_item = QStandardItem(item)

                if is_dir:
                    name_item.setData(QIcon.fromTheme("folder"), Qt.DecorationRole)
                    size_item = QStandardItem("")
                    type_item = QStandardItem("Dossier")
                else:
                    name_item.setData(QIcon.fromTheme("text-x-generic"), Qt.DecorationRole)
                    size_item = QStandardItem(self.format_size(stats.st_size))
                    # Obtenir l'extension du fichier
                    ext = os.path.splitext(item)[1]
                    type_item = QStandardItem(ext[1:].upper() if ext else "Fichier")

                date_modified = datetime.fromtimestamp(stats.st_mtime).strftime("%Y-%m-%d %H:%M")
                date_item = QStandardItem(date_modified)

                self.local_model.appendRow([name_item, size_item, date_item, type_item])

        except Exception as e:
            QMessageBox.warning(self, "Erreur", f"Impossible de lister les fichiers: {str(e)}")

    def refresh_drive_files(self, folder_id=None):
        """Actualise la liste des fichiers Google Drive"""
        if not self.connected:
            return

        self.drive_model.clear()
        self.drive_model.setHorizontalHeaderLabels(["Nom", "Taille", "Date de modification", "Type", "ID"])

        # Utiliser l'ID du dossier fourni ou le dossier actuel
        current_folder_id = folder_id if folder_id is not None else self.drive_model.current_path_id
        self.drive_model.current_path_id = current_folder_id

        # Mettre à jour le label de chemin
        if current_folder_id == 'root':
            self.drive_path_label.setText("Racine")
        else:
            path_text = " / ".join([name for name, _ in self.drive_model.path_history])
            self.drive_path_label.setText(path_text)

        # Si nous ne sommes pas à la racine, ajouter l'option pour remonter
        if len(self.drive_model.path_history) > 1:
            name_item = QStandardItem("..")
            name_item.setData(QIcon.fromTheme("folder"), Qt.DecorationRole)
            size_item = QStandardItem("")
            date_item = QStandardItem("")
            type_item = QStandardItem("Dossier parent")
            id_item = QStandardItem(self.drive_model.path_history[-2][1])  # ID du dossier parent
            self.drive_model.appendRow([name_item, size_item, date_item, type_item, id_item])

        # Obtenir les fichiers du dossier actuel
        try:
            files = self.drive_client.list_files(current_folder_id)

            # Trier: dossiers d'abord, puis par nom
            folders = []
            other_files = []

            for file in files:
                if file.get('mimeType') == 'application/vnd.google-apps.folder':
                    folders.append(file)
                else:
                    other_files.append(file)

            # Trier par nom
            folders.sort(key=lambda x: x['name'].lower())
            other_files.sort(key=lambda x: x['name'].lower())

            # Ajouter les dossiers d'abord
            for file in folders + other_files:
                name_item = QStandardItem(file.get('name', ''))

                if file.get('mimeType') == 'application/vnd.google-apps.folder':
                    name_item.setData(QIcon.fromTheme("folder"), Qt.DecorationRole)
                    type_item = QStandardItem("Dossier")
                    size_item = QStandardItem("")
                else:
                    name_item.setData(QIcon.fromTheme("text-x-generic"), Qt.DecorationRole)
                    type_item = QStandardItem(self.get_file_type(file.get('mimeType', '')))
                    size_item = QStandardItem(self.format_size(int(file.get('size', 0))))

                # Formater la date
                date_str = ""
                if 'modifiedTime' in file:
                    try:
                        date_obj = datetime.strptime(file['modifiedTime'], "%Y-%m-%dT%H:%M:%S.%fZ")
                        date_str = date_obj.strftime("%Y-%m-%d %H:%M")
                    except:
                        date_str = file['modifiedTime']

                date_item = QStandardItem(date_str)
                id_item = QStandardItem(file.get('id', ''))

                self.drive_model.appendRow([name_item, size_item, date_item, type_item, id_item])

        except Exception as e:
            QMessageBox.warning(self, "Erreur", f"Impossible de lister les fichiers Drive: {str(e)}")

    def get_file_type(self, mime_type):
        """Retourne le type de fichier à partir du MIME type"""
        mime_map = {
            'application/vnd.google-apps.document': 'Document Google',
            'application/vnd.google-apps.spreadsheet': 'Feuille de calcul Google',
            'application/vnd.google-apps.presentation': 'Présentation Google',
            'application/vnd.google-apps.form': 'Formulaire Google',
            'application/vnd.google-apps.drawing': 'Dessin Google',
            'application/pdf': 'PDF',
            'image/jpeg': 'JPEG',
            'image/png': 'PNG',
            'text/plain': 'Texte',
            'text/html': 'HTML',
            'application/zip': 'ZIP',
            'video/mp4': 'MP4',
            'audio/mpeg': 'MP3'
        }

        return mime_map.get(mime_type, mime_type.split('/')[-1].upper())

    def format_size(self, size_bytes):
        """Formate la taille en bytes de façon lisible"""
        if size_bytes == 0:
            return "0 B"

        size_names = ("B", "KB", "MB", "GB", "TB")
        i = 0
        while size_bytes >= 1024 and i < len(size_names) - 1:
            size_bytes /= 1024
            i += 1

        return f"{size_bytes:.2f} {size_names[i]}"

    def change_local_path(self):
        """Change le chemin local actuel"""
        new_path = self.local_path_edit.text()
        if os.path.isdir(new_path):
            self.local_model.current_path = new_path
            self.refresh_local_files()
        else:
            QMessageBox.warning(self, "Chemin invalide", "Le chemin spécifié n'est pas un dossier valide.")
            self.local_path_edit.setText(self.local_model.current_path)

    def local_item_double_clicked(self, index):
        """Gère le double-clic sur un élément local"""
        if not index.isValid():
            return

        name = self.local_model.item(index.row(), 0).text()

        # Si c'est "..", remonter d'un niveau
        if name == "..":
            parent_dir = os.path.dirname(self.local_model.current_path)
            self.local_path_edit.setText(parent_dir)
            self.change_local_path()
            return

        # Construire le chemin complet
        full_path = os.path.join(self.local_model.current_path, name)

        # Si c'est un dossier, y entrer
        if os.path.isdir(full_path):
            self.local_path_edit.setText(full_path)
            self.change_local_path()

    def drive_item_double_clicked(self, index):
        """Gère le double-clic sur un élément Google Drive"""
        if not index.isValid():
            return

        row = index.row()
        name = self.drive_model.item(row, 0).text()
        type_str = self.drive_model.item(row, 3).text()
        file_id = self.drive_model.item(row, 4).text()

        # Si c'est "..", remonter d'un niveau
        if name == "..":
            if len(self.drive_model.path_history) > 1:
                self.drive_model.path_history.pop()  # Enlever le dossier actuel
                parent_name, parent_id = self.drive_model.path_history[-1]
                self.refresh_drive_files(parent_id)
            return

        # Si c'est un dossier, y entrer
        if type_str == "Dossier":
            # Ajouter à l'historique
            self.drive_model.path_history.append((name, file_id))
            self.refresh_drive_files(file_id)

    def drive_go_back(self):
        """Remonte d'un niveau dans Google Drive"""
        if len(self.drive_model.path_history) > 1:
            self.drive_model.path_history.pop()  # Enlever le dossier actuel
            parent_name, parent_id = self.drive_model.path_history[-1]
            self.refresh_drive_files(parent_id)

    def change_drive(self, index):
        """Change entre Mon Drive et les Shared Drives"""
        drive_id = self.drive_selector.currentData()

        # Réinitialiser l'historique de navigation
        self.drive_model.path_history = [(self.drive_selector.currentText(), drive_id)]
        self.drive_model.current_path_id = drive_id

        self.refresh_drive_files(drive_id)

    def show_local_context_menu(self, position):
        """Affiche un menu contextuel pour les actions sur les fichiers locaux"""
        indexes = self.local_view.selectedIndexes()
        if not indexes:
            return

        # Obtenir les lignes uniques
        rows = set(index.row() for index in indexes)
        if not rows:
            return

        menu = QMenu(self)

        # Actions pour fichiers multiples
        if rows:
            upload_action = QAction("Uploader vers Google Drive", self)
            upload_action.triggered.connect(self.upload_selected_files)
            menu.addAction(upload_action)

            menu.addSeparator()

        # Actions pour un seul fichier
        if len(rows) == 1:
            row = list(rows)[0]
            name = self.local_model.item(row, 0).text()

            # Si ce n'est pas ".."
            if name != "..":
                rename_action = QAction("Renommer", self)
                rename_action.triggered.connect(self.rename_selected)
                menu.addAction(rename_action)

                delete_action = QAction("Supprimer", self)
                delete_action.triggered.connect(self.delete_selected)
                menu.addAction(delete_action)

        menu.exec_(self.local_view.viewport().mapToGlobal(position))

    def show_drive_context_menu(self, position):
        """Affiche un menu contextuel pour les actions sur les fichiers Google Drive"""
        indexes = self.drive_view.selectedIndexes()
        if not indexes:
            return

        # Obtenir les lignes uniques
        rows = set(index.row() for index in indexes)
        if not rows:
            return

        menu = QMenu(self)

        # Actions pour fichiers multiples
        if rows:
            download_action = QAction("Télécharger", self)
            download_action.triggered.connect(self.download_selected_files)
            menu.addAction(download_action)

            menu.addSeparator()

        # Actions pour un seul fichier
        if len(rows) == 1:
            row = list(rows)[0]
            name = self.drive_model.item(row, 0).text()
            file_type = self.drive_model.item(row, 3).text()

            # Si ce n'est pas ".."
            if name != "..":
                rename_action = QAction("Renommer", self)
                rename_action.triggered.connect(self.rename_selected)
                menu.addAction(rename_action)

                # Si c'est un dossier, option pour créer un sous-dossier
                if file_type == "Dossier":
                    create_subfolder_action = QAction("Créer un sous-dossier", self)
                    create_subfolder_action.triggered.connect(self.create_subfolder_selected)
                    menu.addAction(create_subfolder_action)

                delete_action = QAction("Supprimer", self)
                delete_action.triggered.connect(self.delete_selected)
                menu.addAction(delete_action)

                # Option pour supprimer définitivement
                perm_delete_action = QAction("Supprimer définitivement", self)
                perm_delete_action.triggered.connect(self.permanently_delete_selected)
                menu.addAction(perm_delete_action)

                menu.addSeparator()

                # Option pour voir les détails
                details_action = QAction("Propriétés", self)
                details_action.triggered.connect(self.show_file_details)
                menu.addAction(details_action)

        menu.exec_(self.drive_view.viewport().mapToGlobal(position))

    def upload_selected_files(self):
        """Upload les fichiers sélectionnés vers Google Drive"""
        # Obtenir les fichiers sélectionnés
        indexes = self.local_view.selectedIndexes()
        if not indexes:
            return

        # Obtenir les lignes uniques et les noms de fichiers
        rows_names = set((index.row(), self.local_model.item(index.row(), 0).text())
                         for index in indexes if index.column() == 0)

        # Exclure ".."
        files_to_upload = [(row, name) for row, name in rows_names if name != ".."]

        if not files_to_upload:
            return

        # Obtenir l'ID du dossier de destination
        destination_id = self.drive_model.current_path_id

        # Uploader chaque fichier
        for row, name in files_to_upload:
            file_path = os.path.join(self.local_model.current_path, name)

            # Vérifier si c'est un fichier
            if not os.path.isfile(file_path):
                continue

            # Créer un thread pour l'upload
            upload_thread = UploadThread(self.drive_client, file_path, destination_id)

            # Connecter les signaux
            upload_thread.progress_signal.connect(self.update_progress)
            upload_thread.completed_signal.connect(self.upload_completed)
            upload_thread.error_signal.connect(self.upload_error)

            # Démarrer le thread
            self.upload_threads.append(upload_thread)
            upload_thread.start()

            # Afficher la barre de progression
            self.progress_bar.setValue(0)
            self.progress_bar.setVisible(True)
            self.status_bar.showMessage(f"Upload de {name}...")

    def download_selected_files(self):
        """Télécharge les fichiers sélectionnés depuis Google Drive"""
        # Obtenir les fichiers sélectionnés
        indexes = self.drive_view.selectedIndexes()
        if not indexes:
            return

        # Obtenir les lignes uniques et les informations de fichiers
        rows_info = set((index.row(),
                        self.drive_model.item(index.row(), 0).text(),
                        self.drive_model.item(index.row(), 3).text(),
                        self.drive_model.item(index.row(), 4).text())
                       for index in indexes if index.column() == 0)

        # Exclure ".." et les dossiers
        files_to_download = [(row, name, file_id)
                            for row, name, file_type, file_id in rows_info
                            if name != ".." and file_type != "Dossier"]

        if not files_to_download:
            return

        # Demander le dossier de destination
        destination_dir = QFileDialog.getExistingDirectory(
            self, "Choisir le dossier de destination", self.local_model.current_path)

        if not destination_dir:
            return

        # Télécharger chaque fichier
        for row, name, file_id in files_to_download:
            # Créer un thread pour le téléchargement
            download_thread = DownloadThread(self.drive_client, file_id, name, destination_dir)

            # Connecter les signaux
            download_thread.progress_signal.connect(self.update_progress)
            download_thread.completed_signal.connect(self.download_completed)
            download_thread.error_signal.connect(self.download_error)

            # Démarrer le thread
            self.download_threads.append(download_thread)
            download_thread.start()

            # Afficher la barre de progression
            self.progress_bar.setValue(0)
            self.progress_bar.setVisible(True)
            self.status_bar.showMessage(f"Téléchargement de {name}...")

    def update_progress(self, value):
        """Met à jour la barre de progression"""
        self.progress_bar.setValue(value)

    def upload_completed(self, file_id):
        """Appelé lorsqu'un upload est terminé"""
        self.progress_bar.setVisible(False)
        self.status_bar.showMessage("Upload terminé avec succès", 3000)
        self.refresh_drive_files()

    def upload_error(self, error_msg):
        """Appelé lorsqu'une erreur se produit pendant l'upload"""
        self.progress_bar.setVisible(False)
        self.status_bar.showMessage(f"Erreur d'upload: {error_msg}", 5000)
        QMessageBox.warning(self, "Erreur d'upload", f"Une erreur s'est produite: {error_msg}")

    def download_completed(self, file_path):
        """Appelé lorsqu'un téléchargement est terminé"""
        self.progress_bar.setVisible(False)
        self.status_bar.showMessage(f"Téléchargement terminé: {file_path}", 3000)

        # Si le dossier de destination est le dossier actuellement affiché, actualiser
        if os.path.dirname(file_path) == self.local_model.current_path:
            self.refresh_local_files()

    def download_error(self, error_msg):
        """Appelé lorsqu'une erreur se produit pendant le téléchargement"""
        self.progress_bar.setVisible(False)
        self.status_bar.showMessage(f"Erreur de téléchargement: {error_msg}", 5000)
        QMessageBox.warning(self, "Erreur de téléchargement", f"Une erreur s'est produite: {error_msg}")

    def create_new_folder(self):
        """Crée un nouveau dossier"""
        # Déterminer où créer le dossier (local ou Google Drive)
        focused_widget = QApplication.focusWidget()

        if focused_widget == self.local_view or self.local_view.hasFocus():
            # Créer un dossier local
            folder_name, ok = QInputDialog.getText(self, "Nouveau dossier",
                                                "Nom du dossier:")
            if ok and folder_name:
                try:
                    new_path = os.path.join(self.local_model.current_path, folder_name)
                    os.makedirs(new_path, exist_ok=True)
                    self.refresh_local_files()
                    self.status_bar.showMessage(f"Dossier '{folder_name}' créé", 3000)
                except Exception as e:
                    QMessageBox.warning(self, "Erreur", f"Impossible de créer le dossier: {str(e)}")

        elif focused_widget == self.drive_view or self.drive_view.hasFocus():
            # Créer un dossier Google Drive
            folder_name, ok = QInputDialog.getText(self, "Nouveau dossier Drive",
                                                "Nom du dossier:")
            if ok and folder_name:
                try:
                    parent_id = self.drive_model.current_path_id
                    folder_id = self.drive_client.create_folder(folder_name, parent_id)
                    self.refresh_drive_files()
                    self.status_bar.showMessage(f"Dossier Google Drive '{folder_name}' créé", 3000)
                except Exception as e:
                    QMessageBox.warning(self, "Erreur", f"Impossible de créer le dossier: {str(e)}")

    def create_subfolder_selected(self):
        """Crée un sous-dossier dans le dossier sélectionné"""
        indexes = self.drive_view.selectedIndexes()
        if not indexes:
            return

        # Obtenir le dossier parent
        row = indexes[0].row()
        folder_id = self.drive_model.item(row, 4).text()
        folder_name = self.drive_model.item(row, 0).text()
        folder_type = self.drive_model.item(row, 3).text()

        if folder_name == ".." or folder_type != "Dossier":
            return

        # Demander le nom du sous-dossier
        subfolder_name, ok = QInputDialog.getText(self, f"Nouveau sous-dossier dans '{folder_name}'",
                                              "Nom du sous-dossier:")

        if ok and subfolder_name:
            try:
                subfolder_id = self.drive_client.create_folder(subfolder_name, folder_id)
                self.refresh_drive_files()
                self.status_bar.showMessage(f"Sous-dossier '{subfolder_name}' créé", 3000)
            except Exception as e:
                QMessageBox.warning(self, "Erreur", f"Impossible de créer le sous-dossier: {str(e)}")

    def rename_selected(self):
        """Renomme l'élément sélectionné"""
        # Déterminer quel élément est sélectionné (local ou Google Drive)
        focused_widget = QApplication.focusWidget()

        if focused_widget == self.local_view or self.local_view.hasFocus():
            # Renommer un fichier local
            indexes = self.local_view.selectedIndexes()
            if not indexes:
                return

            row = indexes[0].row()
            old_name = self.local_model.item(row, 0).text()

            if old_name == "..":
                return

            new_name, ok = QInputDialog.getText(self, "Renommer",
                                            "Nouveau nom:", text=old_name)

            if ok and new_name and new_name != old_name:
                old_path = os.path.join(self.local_model.current_path, old_name)
                new_path = os.path.join(self.local_model.current_path, new_name)

                try:
                    os.rename(old_path, new_path)
                    self.refresh_local_files()
                    self.status_bar.showMessage(f"'{old_name}' renommé en '{new_name}'", 3000)
                except Exception as e:
                    QMessageBox.warning(self, "Erreur", f"Impossible de renommer: {str(e)}")

        elif focused_widget == self.drive_view or self.drive_view.hasFocus():
            # Renommer un fichier Google Drive
            indexes = self.drive_view.selectedIndexes()
            if not indexes:
                return

            row = indexes[0].row()
            old_name = self.drive_model.item(row, 0).text()
            file_id = self.drive_model.item(row, 4).text()

            if old_name == "..":
                return

            new_name, ok = QInputDialog.getText(self, "Renommer",
                                            "Nouveau nom:", text=old_name)

            if ok and new_name and new_name != old_name:
                try:
                    self.drive_client.rename_item(file_id, new_name)
                    self.refresh_drive_files()
                    self.status_bar.showMessage(f"'{old_name}' renommé en '{new_name}'", 3000)
                except Exception as e:
                    QMessageBox.warning(self, "Erreur", f"Impossible de renommer: {str(e)}")

    def delete_selected(self):
        """Supprime l'élément sélectionné"""
        # Déterminer quel élément est sélectionné (local ou Google Drive)
        focused_widget = QApplication.focusWidget()

        if focused_widget == self.local_view or self.local_view.hasFocus():
            # Supprimer un fichier local
            indexes = self.local_view.selectedIndexes()
            if not indexes:
                return

            # Obtenir les lignes uniques et les noms de fichiers
            rows_names = set((index.row(), self.local_model.item(index.row(), 0).text())
                            for index in indexes if index.column() == 0)

            # Exclure ".."
            items_to_delete = [(row, name) for row, name in rows_names if name != ".."]

            if not items_to_delete:
                return

            # Confirmation
            item_count = len(items_to_delete)
            if item_count == 1:
                message = f"Voulez-vous vraiment supprimer '{items_to_delete[0][1]}'?"
            else:
                message = f"Voulez-vous vraiment supprimer ces {item_count} éléments?"

            confirm = QMessageBox.question(self, "Confirmation", message,
                                        QMessageBox.Yes | QMessageBox.No)

            if confirm == QMessageBox.Yes:
                errors = []
                for row, name in items_to_delete:
                    path = os.path.join(self.local_model.current_path, name)
                    try:
                        if os.path.isdir(path):
                            # Pour les dossiers, supprimer récursivement
                            import shutil
                            shutil.rmtree(path)
                        else:
                            # Pour les fichiers, supprimer directement
                            os.remove(path)
                    except Exception as e:
                        errors.append(f"Impossible de supprimer '{name}': {str(e)}")

                self.refresh_local_files()

                if errors:
                    QMessageBox.warning(self, "Erreurs de suppression",
                                      "\n".join(errors))
                else:
                    self.status_bar.showMessage(f"{item_count} élément(s) supprimé(s)", 3000)

        elif focused_widget == self.drive_view or self.drive_view.hasFocus():
            # Supprimer un fichier Google Drive (mettre à la corbeille)
            indexes = self.drive_view.selectedIndexes()
            if not indexes:
                return

            # Obtenir les lignes uniques et les informations de fichiers
            rows_info = set((index.row(),
                            self.drive_model.item(index.row(), 0).text(),
                            self.drive_model.item(index.row(), 4).text())
                        for index in indexes if index.column() == 0)

            # Exclure ".."
            items_to_delete = [(row, name, file_id)
                              for row, name, file_id in rows_info
                              if name != ".."]

            if not items_to_delete:
                return

            # Confirmation
            item_count = len(items_to_delete)
            if item_count == 1:
                message = f"Voulez-vous vraiment mettre '{items_to_delete[0][1]}' à la corbeille?"
            else:
                message = f"Voulez-vous vraiment mettre ces {item_count} éléments à la corbeille?"

            confirm = QMessageBox.question(self, "Confirmation", message,
                                        QMessageBox.Yes | QMessageBox.No)

            if confirm == QMessageBox.Yes:
                errors = []
                for row, name, file_id in items_to_delete:
                    try:
                        self.drive_client.delete_item(file_id)
                    except Exception as e:
                        errors.append(f"Impossible de supprimer '{name}': {str(e)}")

                self.refresh_drive_files()

                if errors:
                    QMessageBox.warning(self, "Erreurs de suppression",
                                      "\n".join(errors))
                else:
                    self.status_bar.showMessage(f"{item_count} élément(s) mis à la corbeille", 3000)

    def permanently_delete_selected(self):
        """Supprime définitivement l'élément sélectionné de Google Drive"""
        indexes = self.drive_view.selectedIndexes()
        if not indexes:
            return

        # Obtenir les lignes uniques et les informations de fichiers
        rows_info = set((index.row(),
                        self.drive_model.item(index.row(), 0).text(),
                        self.drive_model.item(index.row(), 4).text())
                       for index in indexes if index.column() == 0)

        # Exclure ".."
        items_to_delete = [(row, name, file_id)
                          for row, name, file_id in rows_info
                          if name != ".."]

        if not items_to_delete:
            return

        # Confirmation (avec avertissement)
        item_count = len(items_to_delete)
        if item_count == 1:
            message = (f"ATTENTION: Voulez-vous vraiment supprimer définitivement '{items_to_delete[0][1]}'?\n\n"
                      "Cette action est irréversible et ne peut pas être annulée.")
        else:
            message = (f"ATTENTION: Voulez-vous vraiment supprimer définitivement ces {item_count} éléments?\n\n"
                      "Cette action est irréversible et ne peut pas être annulée.")

        confirm = QMessageBox.warning(self, "Suppression définitive", message,
                                    QMessageBox.Yes | QMessageBox.No,
                                    QMessageBox.No)

        if confirm == QMessageBox.Yes:
            errors = []
            for row, name, file_id in items_to_delete:
                try:
                    self.drive_client.permanently_delete_item(file_id)
                except Exception as e:
                    errors.append(f"Impossible de supprimer définitivement '{name}': {str(e)}")

            self.refresh_drive_files()

            if errors:
                QMessageBox.warning(self, "Erreurs de suppression",
                                  "\n".join(errors))
            else:
                self.status_bar.showMessage(f"{item_count} élément(s) définitivement supprimé(s)", 3000)

    def show_file_details(self):
        """Affiche les détails d'un fichier Google Drive"""
        indexes = self.drive_view.selectedIndexes()
        if not indexes:
            return

        row = indexes[0].row()
        name = self.drive_model.item(row, 0).text()
        file_id = self.drive_model.item(row, 4).text()

        if name == "..":
            return

        try:
            # Obtenir les métadonnées complètes
            metadata = self.drive_client.get_file_metadata(file_id)

            # Créer une boîte de dialogue pour afficher les détails
            dialog = QDialog(self)
            dialog.setWindowTitle(f"Propriétés: {name}")
            dialog.resize(400, 300)

            layout = QVBoxLayout(dialog)

            form_layout = QFormLayout()

            # Ajouter les principales métadonnées
            form_layout.addRow("Nom:", QLabel(metadata.get('name', '')))
            form_layout.addRow("ID:", QLabel(metadata.get('id', '')))
            form_layout.addRow("Type:", QLabel(self.get_file_type(metadata.get('mimeType', ''))))

            if 'size' in metadata:
                form_layout.addRow("Taille:", QLabel(self.format_size(int(metadata.get('size', 0)))))

            if 'modifiedTime' in metadata:
                try:
                    date_obj = datetime.strptime(metadata['modifiedTime'], "%Y-%m-%dT%H:%M:%S.%fZ")
                    date_str = date_obj.strftime("%Y-%m-%d %H:%M")
                except:
                    date_str = metadata['modifiedTime']
                form_layout.addRow("Modifié le:", QLabel(date_str))

            if 'description' in metadata and metadata['description']:
                form_layout.addRow("Description:", QLabel(metadata['description']))

            layout.addLayout(form_layout)

            # Boutons
            button_box = QDialogButtonBox(QDialogButtonBox.Ok)
            button_box.accepted.connect(dialog.accept)
            layout.addWidget(button_box)

            dialog.setLayout(layout)
            dialog.exec_()

        except Exception as e:
            QMessageBox.warning(self, "Erreur", f"Impossible d'obtenir les détails: {str(e)}")

    def show_search_dialog(self):
        """Affiche une boîte de dialogue pour rechercher des fichiers dans Google Drive"""
        dialog = QDialog(self)
        dialog.setWindowTitle("Rechercher dans Google Drive")
        dialog.resize(400, 100)

        layout = QVBoxLayout(dialog)

        form_layout = QFormLayout()
        search_edit = QLineEdit()
        form_layout.addRow("Rechercher:", search_edit)

        layout.addLayout(form_layout)

        # Boutons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)

        if dialog.exec_() == QDialog.Accepted:
            query = search_edit.text().strip()
            if query:
                self.perform_search(query)

    def perform_search(self, query):
        """Effectue une recherche dans Google Drive"""
        try:
            results = self.drive_client.search_files(query)

            if not results:
                self.status_bar.showMessage(f"Aucun résultat pour '{query}'", 5000)
                return

            # Effacer et préparer le modèle
            self.drive_model.clear()
            self.drive_model.setHorizontalHeaderLabels(["Nom", "Taille", "Date de modification", "Type", "ID"])

            # Ajouter un élément pour revenir à la navigation normale
            name_item = QStandardItem("Retour à la navigation")
            name_item.setData(QIcon.fromTheme("go-previous"), Qt.DecorationRole)
            size_item = QStandardItem("")
            date_item = QStandardItem("")
            type_item = QStandardItem("Navigation")
            id_item = QStandardItem("")
            self.drive_model.appendRow([name_item, size_item, date_item, type_item, id_item])

            # Ajouter les résultats de recherche
            for file in results:
                name_item = QStandardItem(file.get('name', ''))

                if file.get('mimeType') == 'application/vnd.google-apps.folder':
                    name_item.setData(QIcon.fromTheme("folder"), Qt.DecorationRole)
                    type_item = QStandardItem("Dossier")
                    size_item = QStandardItem("")
                else:
                    name_item.setData(QIcon.fromTheme("text-x-generic"), Qt.DecorationRole)
                    type_item = QStandardItem(self.get_file_type(file.get('mimeType', '')))
                    size_item = QStandardItem(self.format_size(int(file.get('size', 0))))

                # Formater la date
                date_str = ""
                if 'modifiedTime' in file:
                    try:
                        date_obj = datetime.strptime(file['modifiedTime'], "%Y-%m-%dT%H:%M:%S.%fZ")
                        date_str = date_obj.strftime("%Y-%m-%d %H:%M")
                    except:
                        date_str = file['modifiedTime']

                date_item = QStandardItem(date_str)
                id_item = QStandardItem(file.get('id', ''))

                self.drive_model.appendRow([name_item, size_item, date_item, type_item, id_item])

            # Mettre à jour le statut
            self.status_bar.showMessage(f"{len(results)} résultat(s) pour '{query}'", 5000)

            # Connecter un gestionnaire spécial pour les clics sur les résultats de recherche
            self.drive_view.doubleClicked.disconnect()
            self.drive_view.doubleClicked.connect(self.search_result_double_clicked)

        except Exception as e:
            QMessageBox.warning(self, "Erreur de recherche", f"Impossible d'effectuer la recherche: {str(e)}")

    def search_result_double_clicked(self, index):
        """Gère le double-clic sur un résultat de recherche"""
        if not index.isValid():
            return

        row = index.row()
        name = self.drive_model.item(row, 0).text()
        file_id = self.drive_model.item(row, 4).text()
        file_type = self.drive_model.item(row, 3).text()

        # Si c'est le premier élément (retour à la navigation)
        if row == 0 and name == "Retour à la navigation":
            # Restaurer la navigation normale et déconnecter ce gestionnaire
            self.drive_view.doubleClicked.disconnect()
            self.drive_view.doubleClicked.connect(self.drive_item_double_clicked)
            self.refresh_drive_files()
            return

        # Si c'est un dossier, y naviguer
        if file_type == "Dossier":
            # Restaurer la navigation normale
            self.drive_view.doubleClicked.disconnect()
            self.drive_view.doubleClicked.connect(self.drive_item_double_clicked)

            # Récupérer le chemin complet du dossier
            try:
                # Obtenir les métadonnées pour connaître le parent
                metadata = self.drive_client.get_file_metadata(file_id)

                # Réinitialiser l'historique de navigation
                self.drive_model.path_history = [(self.drive_selector.currentText(), self.drive_selector.currentData())]

                # Ajouter ce dossier
                self.drive_model.path_history.append((name, file_id))
                self.refresh_drive_files(file_id)
            except Exception as e:
                QMessageBox.warning(self, "Erreur", f"Impossible de naviguer vers ce dossier: {str(e)}")


def main():
    """Fonction principale de l'application"""
    # Créer l'application
    app = QApplication(sys.argv)

    # Créer et afficher la fenêtre principale
    main_window = DriveExplorerWindow()
    main_window.show()

    # Exécuter l'application
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
"""
Boîtes de dialogue personnalisées pour l'application
"""

from datetime import datetime
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                             QLineEdit, QPushButton, QDialogButtonBox,
                             QFormLayout, QTextEdit, QMessageBox)
from PyQt5.QtCore import Qt

from utils.helpers import format_file_size, get_file_type_description


class SearchDialog(QDialog):
    """Boîte de dialogue pour la recherche de fichiers"""

    def __init__(self, parent=None):
        """
        Initialise la boîte de dialogue de recherche

        Args:
            parent: Widget parent
        """
        super().__init__(parent)
        self.setWindowTitle("🔍 Rechercher dans Google Drive")
        self.setModal(True)
        self.resize(400, 150)
        self.setup_ui()

    def setup_ui(self) -> None:
        """Configure l'interface utilisateur"""
        layout = QVBoxLayout()

        # Formulaire de recherche
        form_layout = QFormLayout()

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Entrez votre recherche...")
        self.search_edit.returnPressed.connect(self.accept)
        form_layout.addRow("🔍 Rechercher:", self.search_edit)

        layout.addLayout(form_layout)

        # Boutons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self.setLayout(layout)
        self.search_edit.setFocus()

    def get_search_query(self) -> str:
        """
        Récupère la requête de recherche

        Returns:
            Texte de recherche saisi par l'utilisateur
        """
        return self.search_edit.text().strip()


class FileDetailsDialog(QDialog):
    """Boîte de dialogue pour afficher les détails d'un fichier"""

    def __init__(self, file_metadata: dict, parent=None):
        """
        Initialise la boîte de dialogue des détails

        Args:
            file_metadata: Métadonnées du fichier
            parent: Widget parent
        """
        super().__init__(parent)
        self.file_metadata = file_metadata
        file_name = file_metadata.get('name', 'Fichier')
        self.setWindowTitle(f"ℹ️ Propriétés: {file_name}")
        self.setModal(True)
        self.resize(500, 400)
        self.setup_ui()

    def setup_ui(self) -> None:
        """Configure l'interface utilisateur"""
        layout = QVBoxLayout()

        # Formulaire avec les détails
        form_layout = QFormLayout()

        # Informations de base avec émojis
        form_layout.addRow("📄 Nom:", QLabel(self.file_metadata.get('name', '')))
        form_layout.addRow("🆔 ID:", QLabel(self.file_metadata.get('id', '')))

        mime_type = self.file_metadata.get('mimeType', '')
        form_layout.addRow("🏷️ Type:", QLabel(get_file_type_description(mime_type)))

        # Taille si disponible
        if 'size' in self.file_metadata:
            size_bytes = int(self.file_metadata.get('size', 0))
            form_layout.addRow("📏 Taille:", QLabel(format_file_size(size_bytes)))

        # Date de modification
        if 'modifiedTime' in self.file_metadata:
            try:
                date_obj = datetime.strptime(
                    self.file_metadata['modifiedTime'],
                    "%Y-%m-%dT%H:%M:%S.%fZ"
                )
                date_str = date_obj.strftime("%Y-%m-%d %H:%M")
            except Exception:
                date_str = self.file_metadata['modifiedTime']
            form_layout.addRow("📅 Modifié le:", QLabel(date_str))

        # Description si disponible
        if 'description' in self.file_metadata and self.file_metadata['description']:
            desc_label = QLabel(self.file_metadata['description'])
            desc_label.setWordWrap(True)
            form_layout.addRow("📝 Description:", desc_label)

        # Drive ID si disponible
        if 'driveId' in self.file_metadata:
            form_layout.addRow("☁️ Drive ID:", QLabel(self.file_metadata['driveId']))

        layout.addLayout(form_layout)

        # Bouton OK
        button_box = QDialogButtonBox(QDialogButtonBox.Ok)
        button_box.accepted.connect(self.accept)
        layout.addWidget(button_box)

        self.setLayout(layout)


class RenameDialog(QDialog):
    """Boîte de dialogue pour renommer un fichier/dossier"""

    def __init__(self, current_name: str, parent=None):
        """
        Initialise la boîte de dialogue de renommage

        Args:
            current_name: Nom actuel du fichier/dossier
            parent: Widget parent
        """
        super().__init__(parent)
        self.current_name = current_name
        self.setWindowTitle("✏️ Renommer")
        self.setModal(True)
        self.resize(400, 120)
        self.setup_ui()

    def setup_ui(self) -> None:
        """Configure l'interface utilisateur"""
        layout = QVBoxLayout()

        # Formulaire
        form_layout = QFormLayout()

        self.name_edit = QLineEdit(self.current_name)
        self.name_edit.selectAll()
        self.name_edit.returnPressed.connect(self.accept)
        form_layout.addRow("Nouveau nom:", self.name_edit)

        layout.addLayout(form_layout)

        # Boutons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self.setLayout(layout)
        self.name_edit.setFocus()

    def get_new_name(self) -> str:
        """
        Récupère le nouveau nom saisi

        Returns:
            Nouveau nom du fichier/dossier
        """
        return self.name_edit.text().strip()


class CreateFolderDialog(QDialog):
    """Boîte de dialogue pour créer un nouveau dossier"""

    def __init__(self, parent=None, title: str = "📁 Nouveau dossier"):
        """
        Initialise la boîte de dialogue de création de dossier

        Args:
            parent: Widget parent
            title: Titre de la boîte de dialogue
        """
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.resize(400, 120)
        self.setup_ui()

    def setup_ui(self) -> None:
        """Configure l'interface utilisateur"""
        layout = QVBoxLayout()

        # Formulaire
        form_layout = QFormLayout()

        self.folder_name_edit = QLineEdit()
        self.folder_name_edit.setPlaceholderText("Nom du dossier...")
        self.folder_name_edit.returnPressed.connect(self.accept)
        form_layout.addRow("Nom du dossier:", self.folder_name_edit)

        layout.addLayout(form_layout)

        # Boutons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self.setLayout(layout)
        self.folder_name_edit.setFocus()

    def get_folder_name(self) -> str:
        """
        Récupère le nom du dossier saisi

        Returns:
            Nom du dossier à créer
        """
        return self.folder_name_edit.text().strip()


class ConfirmationDialog(QMessageBox):
    """Boîte de dialogue de confirmation personnalisée"""

    def __init__(self, title: str, message: str, parent=None):
        """
        Initialise la boîte de dialogue de confirmation

        Args:
            title: Titre de la boîte de dialogue
            message: Message à afficher
            parent: Widget parent
        """
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setText(message)
        self.setIcon(QMessageBox.Question)
        self.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        self.setDefaultButton(QMessageBox.No)

    @staticmethod
    def ask_confirmation(title: str, message: str, parent=None) -> bool:
        """
        Affiche une boîte de dialogue de confirmation

        Args:
            title: Titre de la boîte de dialogue
            message: Message à afficher
            parent: Widget parent

        Returns:
            True si l'utilisateur a confirmé, False sinon
        """
        dialog = ConfirmationDialog(title, message, parent)
        return dialog.exec_() == QMessageBox.Yes


class ErrorDialog(QMessageBox):
    """Boîte de dialogue d'erreur personnalisée"""

    def __init__(self, title: str, message: str, details: str = None, parent=None):
        """
        Initialise la boîte de dialogue d'erreur

        Args:
            title: Titre de la boîte de dialogue
            message: Message d'erreur principal
            details: Détails techniques de l'erreur (optionnel)
            parent: Widget parent
        """
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setText(message)
        self.setIcon(QMessageBox.Critical)
        self.setStandardButtons(QMessageBox.Ok)

        if details:
            self.setDetailedText(details)

    @staticmethod
    def show_error(title: str, message: str, details: str = None, parent=None) -> None:
        """
        Affiche une boîte de dialogue d'erreur

        Args:
            title: Titre de la boîte de dialogue
            message: Message d'erreur principal
            details: Détails techniques de l'erreur (optionnel)
            parent: Widget parent
        """
        dialog = ErrorDialog(title, message, details, parent)
        dialog.exec_()


class ProgressDialog(QDialog):
    """Boîte de dialogue de progression pour les opérations longues"""

    def __init__(self, title: str, parent=None):
        """
        Initialise la boîte de dialogue de progression

        Args:
            title: Titre de la boîte de dialogue
            parent: Widget parent
        """
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setFixedSize(400, 120)
        self.setup_ui()

    def setup_ui(self) -> None:
        """Configure l'interface utilisateur"""
        layout = QVBoxLayout()

        # Label de statut
        self.status_label = QLabel("Préparation...")
        layout.addWidget(self.status_label)

        # Barre de progression
        from PyQt5.QtWidgets import QProgressBar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        # Bouton d'annulation (optionnel)
        self.cancel_button = QPushButton("Annuler")
        self.cancel_button.clicked.connect(self.reject)
        layout.addWidget(self.cancel_button)

        self.setLayout(layout)

    def update_progress(self, value: int, status: str = None) -> None:
        """
        Met à jour la progression

        Args:
            value: Valeur de progression (0-100)
            status: Message de statut (optionnel)
        """
        self.progress_bar.setValue(value)
        if status:
            self.status_label.setText(status)

    def set_status(self, status: str) -> None:
        """
        Met à jour le message de statut

        Args:
            status: Nouveau message de statut
        """
        self.status_label.setText(status)

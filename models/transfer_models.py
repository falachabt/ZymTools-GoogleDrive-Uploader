"""
Modèles de données pour la gestion des transferts
"""

import os
from datetime import datetime
from enum import Enum
from typing import Dict, Any, Optional
from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtGui import QStandardItemModel, QStandardItem

from utils.helpers import format_file_size


class TransferStatus(Enum):
    """Énumération des statuts de transfert"""
    PENDING = "⏳ En attente"
    IN_PROGRESS = "🔄 En cours"
    COMPLETED = "✅ Terminé"
    ERROR = "❌ Erreur"
    CANCELLED = "🚫 Annulé"
    PAUSED = "⏸️ Suspendu"


class TransferType(Enum):
    """Énumération des types de transfert"""
    UPLOAD_FILE = "⬆️ Upload fichier"
    UPLOAD_FOLDER = "⬆️ Upload dossier"
    DOWNLOAD_FILE = "⬇️ Download fichier"
    DOWNLOAD_FOLDER = "⬇️ Download dossier"


class TransferItem:
    """Représente un élément de transfert"""

    def __init__(self, transfer_id: str, transfer_type: TransferType,
                 source_path: str, destination_path: str, file_name: str,
                 file_size: int = 0):
        """
        Initialise un élément de transfert

        Args:
            transfer_id: Identifiant unique du transfert
            transfer_type: Type de transfert
            source_path: Chemin source
            destination_path: Chemin de destination
            file_name: Nom du fichier
            file_size: Taille du fichier en bytes
        """
        self.transfer_id = transfer_id
        self.transfer_type = transfer_type
        self.source_path = source_path
        self.destination_path = destination_path
        self.file_name = file_name
        self.file_size = file_size
        self.status = TransferStatus.PENDING
        self.progress = 0
        self.speed = 0  # Bytes par seconde
        self.error_message = ""
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
        self.bytes_transferred = 0

    def get_elapsed_time(self) -> float:
        """Retourne le temps écoulé en secondes"""
        if not self.start_time:
            return 0
        end_time = self.end_time or datetime.now()
        return (end_time - self.start_time).total_seconds()

    def get_eta(self) -> Optional[float]:
        """Retourne le temps estimé d'arrivée en secondes"""
        if self.progress <= 0 or self.speed <= 0:
            return None

        remaining_bytes = self.file_size - self.bytes_transferred
        return remaining_bytes / self.speed

    def get_speed_text(self) -> str:
        """Retourne la vitesse formatée"""
        if self.speed <= 0:
            return "0 B/s"
        return f"{format_file_size(int(self.speed))}/s"

    def get_eta_text(self) -> str:
        """Retourne l'ETA formaté"""
        eta = self.get_eta()
        if eta is None:
            return "∞"

        if eta < 60:
            return f"{int(eta)}s"
        elif eta < 3600:
            return f"{int(eta // 60)}m {int(eta % 60)}s"
        else:
            return f"{int(eta // 3600)}h {int((eta % 3600) // 60)}m"


class TransferManager(QObject):
    """Gestionnaire central des transferts"""

    # Signaux pour notifier les changements
    transfer_added = pyqtSignal(str)  # transfer_id
    transfer_updated = pyqtSignal(str)  # transfer_id
    transfer_removed = pyqtSignal(str)  # transfer_id
    transfer_status_changed = pyqtSignal(str, TransferStatus)  # transfer_id, status

    def __init__(self):
        """Initialise le gestionnaire de transferts"""
        super().__init__()
        self.transfers: Dict[str, TransferItem] = {}
        self._next_id = 1

    def generate_transfer_id(self) -> str:
        """Génère un ID unique pour un transfert"""
        transfer_id = f"transfer_{self._next_id}"
        self._next_id += 1
        return transfer_id

    def add_transfer(self, transfer_type: TransferType, source_path: str,
                     destination_path: str, file_name: str, file_size: int = 0) -> str:
        """
        Ajoute un nouveau transfert

        Args:
            transfer_type: Type de transfert
            source_path: Chemin source
            destination_path: Chemin de destination
            file_name: Nom du fichier
            file_size: Taille du fichier

        Returns:
            ID du transfert créé
        """
        transfer_id = self.generate_transfer_id()
        transfer = TransferItem(
            transfer_id, transfer_type, source_path,
            destination_path, file_name, file_size
        )

        self.transfers[transfer_id] = transfer
        self.transfer_added.emit(transfer_id)
        return transfer_id

    def update_transfer_progress(self, transfer_id: str, progress: int,
                                 bytes_transferred: int = 0, speed: float = 0) -> None:
        """
        Met à jour le progrès d'un transfert

        Args:
            transfer_id: ID du transfert
            progress: Progrès en pourcentage (0-100)
            bytes_transferred: Bytes transférés
            speed: Vitesse en bytes/seconde
        """
        if transfer_id in self.transfers:
            transfer = self.transfers[transfer_id]
            transfer.progress = progress
            transfer.bytes_transferred = bytes_transferred
            transfer.speed = speed

            if transfer.status == TransferStatus.PENDING:
                self.update_transfer_status(transfer_id, TransferStatus.IN_PROGRESS)

            self.transfer_updated.emit(transfer_id)

    def update_transfer_status(self, transfer_id: str, status: TransferStatus,
                               error_message: str = "") -> None:
        """
        Met à jour le statut d'un transfert

        Args:
            transfer_id: ID du transfert
            status: Nouveau statut
            error_message: Message d'erreur si applicable
        """
        if transfer_id in self.transfers:
            transfer = self.transfers[transfer_id]
            old_status = transfer.status
            transfer.status = status
            transfer.error_message = error_message

            if status == TransferStatus.IN_PROGRESS and not transfer.start_time:
                transfer.start_time = datetime.now()
            elif status in [TransferStatus.COMPLETED, TransferStatus.ERROR, TransferStatus.CANCELLED]:
                transfer.end_time = datetime.now()
                if status == TransferStatus.COMPLETED:
                    transfer.progress = 100

            self.transfer_status_changed.emit(transfer_id, status)
            self.transfer_updated.emit(transfer_id)

    def remove_transfer(self, transfer_id: str) -> None:
        """
        Supprime un transfert

        Args:
            transfer_id: ID du transfert à supprimer
        """
        if transfer_id in self.transfers:
            del self.transfers[transfer_id]
            self.transfer_removed.emit(transfer_id)

    def get_transfer(self, transfer_id: str) -> Optional[TransferItem]:
        """
        Récupère un transfert par son ID

        Args:
            transfer_id: ID du transfert

        Returns:
            TransferItem ou None si non trouvé
        """
        return self.transfers.get(transfer_id)

    def get_all_transfers(self) -> Dict[str, TransferItem]:
        """Retourne tous les transferts"""
        return self.transfers.copy()

    def get_active_transfers(self) -> Dict[str, TransferItem]:
        """Retourne les transferts actifs (en cours ou en attente)"""
        return {
            tid: transfer for tid, transfer in self.transfers.items()
            if transfer.status in [TransferStatus.PENDING, TransferStatus.IN_PROGRESS, TransferStatus.PAUSED]
        }

    def get_completed_transfers(self) -> Dict[str, TransferItem]:
        """Retourne les transferts terminés"""
        return {
            tid: transfer for tid, transfer in self.transfers.items()
            if transfer.status in [TransferStatus.COMPLETED, TransferStatus.ERROR, TransferStatus.CANCELLED]
        }

    def clear_completed_transfers(self) -> None:
        """Supprime tous les transferts terminés"""
        completed_ids = list(self.get_completed_transfers().keys())
        for transfer_id in completed_ids:
            self.remove_transfer(transfer_id)

    def cancel_transfer(self, transfer_id: str) -> None:
        """
        Annule un transfert

        Args:
            transfer_id: ID du transfert à annuler
        """
        self.update_transfer_status(transfer_id, TransferStatus.CANCELLED)

    def pause_transfer(self, transfer_id: str) -> None:
        """
        Suspend un transfert

        Args:
            transfer_id: ID du transfert à suspendre
        """
        if transfer_id in self.transfers:
            transfer = self.transfers[transfer_id]
            if transfer.status == TransferStatus.IN_PROGRESS:
                self.update_transfer_status(transfer_id, TransferStatus.PAUSED)

    def resume_transfer(self, transfer_id: str) -> None:
        """
        Reprend un transfert suspendu

        Args:
            transfer_id: ID du transfert à reprendre
        """
        if transfer_id in self.transfers:
            transfer = self.transfers[transfer_id]
            if transfer.status == TransferStatus.PAUSED:
                self.update_transfer_status(transfer_id, TransferStatus.IN_PROGRESS)


class TransferListModel(QStandardItemModel):
    """Modèle pour afficher la liste des transferts"""

    def __init__(self, transfer_manager: TransferManager):
        """
        Initialise le modèle

        Args:
            transfer_manager: Gestionnaire de transferts
        """
        super().__init__()
        self.transfer_manager = transfer_manager
        self.setHorizontalHeaderLabels([
            "Fichier", "Type", "Statut", "Progrès",
            "Vitesse", "ETA", "Taille", "Destination"
        ])

        # Connecter aux signaux du gestionnaire
        self.transfer_manager.transfer_added.connect(self.on_transfer_added)
        self.transfer_manager.transfer_updated.connect(self.on_transfer_updated)
        self.transfer_manager.transfer_removed.connect(self.on_transfer_removed)

        # Dictionnaire pour suivre les transferts de dossiers et leurs fichiers
        self.folder_transfers = {}

    def on_transfer_added(self, transfer_id: str) -> None:
        """Appelé quand un transfert est ajouté"""
        transfer = self.transfer_manager.get_transfer(transfer_id)
        if transfer:
            self.add_transfer_row(transfer)

    def on_transfer_updated(self, transfer_id: str) -> None:
        """Appelé quand un transfert est mis à jour"""
        transfer = self.transfer_manager.get_transfer(transfer_id)
        if transfer:
            self.update_transfer_row(transfer)

    def on_transfer_removed(self, transfer_id: str) -> None:
        """Appelé quand un transfert est supprimé"""
        # Vérifier si c'est un transfert de dossier
        if transfer_id in self.folder_transfers:
            # Supprimer aussi les fichiers individuels
            for child_row in self.folder_transfers[transfer_id]:
                for row in range(self.rowCount()):
                    item = self.item(row, 0)
                    if item and item.data() == f"{transfer_id}_{child_row}":
                        self.removeRow(row)
                        break
            # Supprimer l'entrée du dictionnaire
            del self.folder_transfers[transfer_id]

        # Trouver et supprimer la ligne correspondante
        for row in range(self.rowCount()):
            item = self.item(row, 0)
            if item and item.data() == transfer_id:
                self.removeRow(row)
                break

    def add_transfer_row(self, transfer: TransferItem) -> None:
        """Ajoute une ligne pour un transfert"""
        row = self.rowCount()

        # Fichier
        file_item = QStandardItem(transfer.file_name)
        file_item.setData(transfer.transfer_id)  # Stocker l'ID pour référence

        # Type
        type_item = QStandardItem(transfer.transfer_type.value)

        # Statut
        status_item = QStandardItem(transfer.status.value)

        # Progrès
        progress_item = QStandardItem(f"{transfer.progress}%")

        # Vitesse
        speed_item = QStandardItem(transfer.get_speed_text())

        # ETA
        eta_item = QStandardItem(transfer.get_eta_text())

        # Taille
        size_item = QStandardItem(format_file_size(transfer.file_size) if transfer.file_size > 0 else "")

        # Destination
        dest_item = QStandardItem(transfer.destination_path)

        self.setItem(row, 0, file_item)
        self.setItem(row, 1, type_item)
        self.setItem(row, 2, status_item)
        self.setItem(row, 3, progress_item)
        self.setItem(row, 4, speed_item)
        self.setItem(row, 5, eta_item)
        self.setItem(row, 6, size_item)
        self.setItem(row, 7, dest_item)

        # Si c'est un transfert de dossier, ajouter les fichiers individuels
        if transfer.transfer_type in [TransferType.UPLOAD_FOLDER, TransferType.DOWNLOAD_FOLDER]:
            self.add_folder_files(transfer)

    def add_folder_files(self, transfer: TransferItem) -> None:
        """Ajoute les fichiers individuels d'un dossier"""
        from utils.helpers import count_files_in_directory
        import os

        # Initialiser la liste des fichiers pour ce transfert
        self.folder_transfers[transfer.transfer_id] = []

        # Pour les uploads de dossier, lister les fichiers
        if transfer.transfer_type == TransferType.UPLOAD_FOLDER and os.path.isdir(transfer.source_path):
            files_to_add = []

            # Parcourir le dossier et ajouter chaque fichier
            for root, dirs, files in os.walk(transfer.source_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    rel_path = os.path.relpath(file_path, transfer.source_path)

                    # Ajouter à la liste des fichiers à traiter
                    files_to_add.append({
                        'name': file,
                        'path': file_path,
                        'rel_path': rel_path,
                        'size': os.path.getsize(file_path) if os.path.exists(file_path) else 0
                    })

            # Ajouter chaque fichier au modèle
            for i, file_info in enumerate(files_to_add):
                row = self.rowCount()

                # Créer un ID unique pour ce fichier dans le transfert
                file_id = f"{transfer.transfer_id}_{i}"
                self.folder_transfers[transfer.transfer_id].append(i)

                # Fichier (avec indentation pour montrer la hiérarchie)
                file_item = QStandardItem(f"  └─ {file_info['rel_path']}")
                file_item.setData(file_id)

                # Type (même que le parent)
                type_item = QStandardItem(transfer.transfer_type.value)

                # Statut (même que le parent)
                status_item = QStandardItem(transfer.status.value)

                # Progrès (même que le parent pour l'instant)
                progress_item = QStandardItem(f"{transfer.progress}%")

                # Vitesse (vide pour les fichiers individuels)
                speed_item = QStandardItem("")

                # ETA (vide pour les fichiers individuels)
                eta_item = QStandardItem("")

                # Taille
                size_item = QStandardItem(format_file_size(file_info['size']))

                # Destination (même que le parent)
                dest_item = QStandardItem(transfer.destination_path)

                self.setItem(row, 0, file_item)
                self.setItem(row, 1, type_item)
                self.setItem(row, 2, status_item)
                self.setItem(row, 3, progress_item)
                self.setItem(row, 4, speed_item)
                self.setItem(row, 5, eta_item)
                self.setItem(row, 6, size_item)
                self.setItem(row, 7, dest_item)

    def update_transfer_row(self, transfer: TransferItem) -> None:
        """Met à jour une ligne de transfert"""
        # Trouver la ligne correspondante
        for row in range(self.rowCount()):
            item = self.item(row, 0)
            if item and item.data() == transfer.transfer_id:
                # Mettre à jour les colonnes
                self.item(row, 2).setText(transfer.status.value)
                self.item(row, 3).setText(f"{transfer.progress}%")
                self.item(row, 4).setText(transfer.get_speed_text())
                self.item(row, 5).setText(transfer.get_eta_text())

                # Si c'est un transfert de dossier, mettre à jour aussi les fichiers individuels
                if transfer.transfer_id in self.folder_transfers:
                    for child_row in self.folder_transfers[transfer.transfer_id]:
                        for r in range(self.rowCount()):
                            child_item = self.item(r, 0)
                            if child_item and child_item.data() == f"{transfer.transfer_id}_{child_row}":
                                # Mettre à jour le statut et le progrès
                                self.item(r, 2).setText(transfer.status.value)
                                self.item(r, 3).setText(f"{transfer.progress}%")
                                break

                break

    def get_transfer_id_from_row(self, row: int) -> Optional[str]:
        """
        Récupère l'ID du transfert à partir d'une ligne

        Args:
            row: Numéro de ligne

        Returns:
            ID du transfert ou None
        """
        item = self.item(row, 0)
        if item:
            return item.data()
        return None

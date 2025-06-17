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
    # NOUVEAU : Type pour les fichiers individuels dans un dossier
    UPLOAD_FILE_IN_FOLDER = "⬆️ Fichier (dossier)"
    DOWNLOAD_FILE_IN_FOLDER = "⬇️ Fichier (dossier)"


class TransferItem:
    """Représente un élément de transfert"""

    def __init__(self, transfer_id: str, transfer_type: TransferType,
                 source_path: str, destination_path: str, file_name: str,
                 file_size: int = 0, parent_transfer_id: str = None):
        """
        Initialise un élément de transfert

        Args:
            transfer_id: Identifiant unique du transfert
            transfer_type: Type de transfert
            source_path: Chemin source
            destination_path: Chemin de destination
            file_name: Nom du fichier
            file_size: Taille du fichier en bytes
            parent_transfer_id: ID du transfert parent (pour les fichiers dans un dossier)
        """
        self.transfer_id = transfer_id
        self.transfer_type = transfer_type
        self.source_path = source_path
        self.destination_path = destination_path
        self.file_name = file_name
        self.file_size = file_size
        self.parent_transfer_id = parent_transfer_id  # NOUVEAU
        self.status = TransferStatus.PENDING
        self.progress = 0
        self.speed = 0  # Bytes par seconde
        self.error_message = ""
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
        self.bytes_transferred = 0

    def is_individual_file(self) -> bool:
        """Retourne True si c'est un fichier individuel dans un dossier"""
        return self.parent_transfer_id is not None

    def is_folder_transfer(self) -> bool:
        """Retourne True si c'est un transfert de dossier"""
        return self.transfer_type in [TransferType.UPLOAD_FOLDER, TransferType.DOWNLOAD_FOLDER]

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
    """Gestionnaire central des transferts - VERSION AMÉLIORÉE"""

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
                     destination_path: str, file_name: str, file_size: int = 0,
                     parent_transfer_id: str = None) -> str:
        """
        Ajoute un nouveau transfert

        Args:
            transfer_type: Type de transfert
            source_path: Chemin source
            destination_path: Chemin de destination
            file_name: Nom du fichier
            file_size: Taille du fichier
            parent_transfer_id: ID du transfert parent (optionnel)

        Returns:
            ID du transfert créé
        """
        transfer_id = self.generate_transfer_id()
        transfer = TransferItem(
            transfer_id, transfer_type, source_path,
            destination_path, file_name, file_size, parent_transfer_id
        )

        self.transfers[transfer_id] = transfer
        self.transfer_added.emit(transfer_id)
        return transfer_id

    def add_folder_transfer_with_files(self, folder_path: str, destination_path: str,
                                       folder_name: str) -> tuple:
        """
        Ajoute un transfert de dossier et crée des transferts individuels pour chaque fichier

        Args:
            folder_path: Chemin du dossier source
            destination_path: Chemin de destination
            folder_name: Nom du dossier

        Returns:
            Tuple (folder_transfer_id, list_of_file_transfer_ids)
        """
        # Créer le transfert principal du dossier
        total_size = self._calculate_folder_size(folder_path)
        folder_transfer_id = self.add_transfer(
            TransferType.UPLOAD_FOLDER,
            folder_path,
            destination_path,
            folder_name,
            total_size
        )

        # Créer des transferts individuels pour chaque fichier
        file_transfer_ids = []
        for root, dirs, files in os.walk(folder_path):
            for file in files:
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, folder_path)

                try:
                    file_size = os.path.getsize(file_path)
                    file_transfer_id = self.add_transfer(
                        TransferType.UPLOAD_FILE_IN_FOLDER,
                        file_path,
                        destination_path,
                        rel_path,  # Utiliser le chemin relatif comme nom
                        file_size,
                        folder_transfer_id  # Lier au transfert parent
                    )
                    file_transfer_ids.append(file_transfer_id)
                except OSError:
                    # Ignorer les fichiers inaccessibles
                    continue

        return folder_transfer_id, file_transfer_ids

    def _calculate_folder_size(self, folder_path: str) -> int:
        """Calcule la taille totale d'un dossier"""
        total_size = 0
        try:
            for root, dirs, files in os.walk(folder_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    try:
                        total_size += os.path.getsize(file_path)
                    except OSError:
                        continue
        except OSError:
            pass
        return total_size

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

            # Si c'est un fichier individuel, mettre à jour le progrès du dossier parent
            if transfer.parent_transfer_id:
                self._update_parent_folder_progress(transfer.parent_transfer_id)

    def _update_parent_folder_progress(self, folder_transfer_id: str) -> None:
        """Met à jour le progrès d'un dossier basé sur ses fichiers individuels"""
        if folder_transfer_id not in self.transfers:
            return

        # Récupérer tous les fichiers de ce dossier
        child_transfers = self.get_child_transfers(folder_transfer_id)
        if not child_transfers:
            return

        # Calculer le progrès moyen
        total_progress = sum(t.progress for t in child_transfers.values())
        avg_progress = total_progress / len(child_transfers)

        # Calculer la vitesse totale
        total_speed = sum(t.speed for t in child_transfers.values())

        # Calculer les bytes transférés totaux
        total_bytes = sum(t.bytes_transferred for t in child_transfers.values())

        folder_transfer = self.transfers[folder_transfer_id]
        folder_transfer.progress = int(avg_progress)
        folder_transfer.speed = total_speed
        folder_transfer.bytes_transferred = total_bytes

        # Mettre à jour le statut du dossier
        completed_count = sum(1 for t in child_transfers.values() if t.status == TransferStatus.COMPLETED)
        error_count = sum(1 for t in child_transfers.values() if t.status == TransferStatus.ERROR)

        if completed_count == len(child_transfers):
            # Tous les fichiers sont terminés
            self.update_transfer_status(folder_transfer_id, TransferStatus.COMPLETED)
        elif error_count > 0 and completed_count + error_count == len(child_transfers):
            # Tous les fichiers sont terminés mais il y a des erreurs
            self.update_transfer_status(folder_transfer_id, TransferStatus.ERROR)
        elif any(t.status == TransferStatus.IN_PROGRESS for t in child_transfers.values()):
            # Au moins un fichier est en cours
            if folder_transfer.status != TransferStatus.IN_PROGRESS:
                self.update_transfer_status(folder_transfer_id, TransferStatus.IN_PROGRESS)

        self.transfer_updated.emit(folder_transfer_id)

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

            # Si c'est un fichier individuel, mettre à jour le parent
            if transfer.parent_transfer_id:
                self._update_parent_folder_progress(transfer.parent_transfer_id)

    def get_child_transfers(self, parent_transfer_id: str) -> Dict[str, TransferItem]:
        """Retourne tous les transferts enfants d'un transfert parent"""
        return {
            tid: transfer for tid, transfer in self.transfers.items()
            if transfer.parent_transfer_id == parent_transfer_id
        }

    def get_main_transfers(self) -> Dict[str, TransferItem]:
        """Retourne seulement les transferts principaux (pas les fichiers individuels)"""
        return {
            tid: transfer for tid, transfer in self.transfers.items()
            if transfer.parent_transfer_id is None
        }

    def get_individual_file_transfers(self) -> Dict[str, TransferItem]:
        """Retourne seulement les fichiers individuels"""
        return {
            tid: transfer for tid, transfer in self.transfers.items()
            if transfer.parent_transfer_id is not None
        }

    def remove_transfer(self, transfer_id: str) -> None:
        """
        Supprime un transfert

        Args:
            transfer_id: ID du transfert à supprimer
        """
        if transfer_id in self.transfers:
            transfer = self.transfers[transfer_id]

            # Si c'est un transfert de dossier, supprimer aussi tous ses fichiers
            if transfer.is_folder_transfer():
                child_ids = list(self.get_child_transfers(transfer_id).keys())
                for child_id in child_ids:
                    if child_id in self.transfers:
                        del self.transfers[child_id]
                        self.transfer_removed.emit(child_id)

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
        if transfer_id in self.transfers:
            transfer = self.transfers[transfer_id]

            # Si c'est un dossier, annuler tous ses fichiers
            if transfer.is_folder_transfer():
                for child_id in self.get_child_transfers(transfer_id):
                    self.update_transfer_status(child_id, TransferStatus.CANCELLED)

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
    """Modèle pour afficher la liste des transferts - VERSION AMÉLIORÉE"""

    def __init__(self, transfer_manager: TransferManager, show_individual_files: bool = False):
        """
        Initialise le modèle

        Args:
            transfer_manager: Gestionnaire de transferts
            show_individual_files: True pour afficher les fichiers individuels (pour les queues)
        """
        super().__init__()
        self.transfer_manager = transfer_manager
        self.show_individual_files = show_individual_files
        self.setHorizontalHeaderLabels([
            "Fichier", "Type", "Statut", "Progrès",
            "Vitesse", "ETA", "Taille", "Destination"
        ])

        # Connecter aux signaux du gestionnaire
        self.transfer_manager.transfer_added.connect(self.on_transfer_added)
        self.transfer_manager.transfer_updated.connect(self.on_transfer_updated)
        self.transfer_manager.transfer_removed.connect(self.on_transfer_removed)

    def on_transfer_added(self, transfer_id: str) -> None:
        """Appelé quand un transfert est ajouté"""
        transfer = self.transfer_manager.get_transfer(transfer_id)
        if transfer and self._should_show_transfer(transfer):
            self.add_transfer_row(transfer)

    def _should_show_transfer(self, transfer: TransferItem) -> bool:
        """Détermine si un transfert doit être affiché dans ce modèle"""
        if self.show_individual_files:
            # Pour les queues : afficher seulement les fichiers individuels
            return transfer.is_individual_file()
        else:
            # Pour la liste complète : afficher seulement les transferts principaux
            return not transfer.is_individual_file()

    def on_transfer_updated(self, transfer_id: str) -> None:
        """Appelé quand un transfert est mis à jour"""
        transfer = self.transfer_manager.get_transfer(transfer_id)
        if transfer and self._should_show_transfer(transfer):
            self.update_transfer_row(transfer)

    def on_transfer_removed(self, transfer_id: str) -> None:
        """Appelé quand un transfert est supprimé"""
        # Trouver et supprimer la ligne correspondante
        for row in range(self.rowCount()):
            item = self.item(row, 0)
            if item and item.data() == transfer_id:
                self.removeRow(row)
                break

    def add_transfer_row(self, transfer: TransferItem) -> None:
        """Ajoute une ligne pour un transfert"""
        row = self.rowCount()

        # Fichier - afficher le chemin relatif pour les fichiers individuels
        display_name = transfer.file_name
        if transfer.is_individual_file():
            display_name = f"  └─ {transfer.file_name}"

        file_item = QStandardItem(display_name)
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

    def refresh_model(self) -> None:
        """Rafraîchit complètement le modèle"""
        self.clear()
        self.setHorizontalHeaderLabels([
            "Fichier", "Type", "Statut", "Progrès",
            "Vitesse", "ETA", "Taille", "Destination"
        ])

        # Ajouter tous les transferts appropriés
        for transfer in self.transfer_manager.get_all_transfers().values():
            if self._should_show_transfer(transfer):
                self.add_transfer_row(transfer)
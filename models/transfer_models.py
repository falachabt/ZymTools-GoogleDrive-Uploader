"""
Modèles de données pour la gestion des transferts
"""

import os
from datetime import datetime
from enum import Enum
from typing import Dict, Any, Optional, List
from PyQt5.QtCore import QObject, pyqtSignal, QTimer
from PyQt5.QtGui import QStandardItemModel, QStandardItem
from PyQt5.QtCore import Qt

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


class FileTransferItem:
    """Représente un fichier individuel dans un transfert"""
    
    def __init__(self, file_path: str, file_name: str, file_size: int = 0, 
                 relative_path: str = "", destination_folder_id: str = ""):
        """
        Initialise un élément de transfert de fichier
        
        Args:
            file_path: Chemin complet du fichier
            file_name: Nom du fichier
            file_size: Taille du fichier en bytes
            relative_path: Chemin relatif dans le dossier parent
            destination_folder_id: ID du dossier de destination sur Google Drive
        """
        self.file_path = file_path
        self.file_name = file_name
        self.file_size = file_size
        self.relative_path = relative_path
        self.destination_folder_id = destination_folder_id
        self.status = TransferStatus.PENDING
        self.progress = 0
        self.speed = 0
        self.error_message = ""
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
        self.bytes_transferred = 0
        self.uploaded_file_id: str = ""  # ID du fichier une fois uploadé
        self.retry_count = 0
        self.exists_on_drive = False  # True si le fichier existe déjà sur Drive


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
        self.destination_folder_id: str = ""  # ID du dossier de destination sur Google Drive
        
        # Enhanced for individual file tracking
        self.child_files: Dict[str, FileTransferItem] = {}  # Pour les transferts de dossiers
        self.is_folder_transfer = transfer_type in [TransferType.UPLOAD_FOLDER, TransferType.DOWNLOAD_FOLDER]

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
        """Retourne la vitesse formatée (agrégée pour les dossiers)"""
        if self.is_folder_transfer and self.child_files:
            # Calculer la vitesse agrégée des fichiers en cours
            total_speed = sum(f.speed for f in self.child_files.values() 
                            if f.status == TransferStatus.IN_PROGRESS)
            if total_speed <= 0:
                return "0 B/s"
            return f"{format_file_size(int(total_speed))}/s"
        else:
            # Fichier simple
            if self.speed <= 0:
                return "0 B/s"
            return f"{format_file_size(int(self.speed))}/s"

    def get_eta_text(self) -> str:
        """Retourne l'ETA formaté (calculé pour les dossiers)"""
        if self.is_folder_transfer and self.child_files:
            # Calculer l'ETA basé sur les fichiers restants et leur vitesse moyenne
            in_progress_files = [f for f in self.child_files.values() 
                               if f.status == TransferStatus.IN_PROGRESS]
            pending_files = [f for f in self.child_files.values() 
                           if f.status == TransferStatus.PENDING]
            
            if not in_progress_files and not pending_files:
                return "-"
            
            # Calculer la vitesse moyenne des fichiers en cours
            total_speed = sum(f.speed for f in in_progress_files if f.speed > 0)
            if total_speed <= 0:
                return "∞"
            
            # Estimer le temps restant basé sur la taille moyenne et les fichiers restants
            if in_progress_files:
                avg_file_size = sum(f.file_size for f in in_progress_files) / len(in_progress_files)
                remaining_bytes = sum((f.file_size - (f.file_size * f.progress / 100)) for f in in_progress_files)
                remaining_bytes += len(pending_files) * avg_file_size
                
                eta_seconds = remaining_bytes / total_speed
                
                if eta_seconds < 60:
                    return f"{int(eta_seconds)}s"
                elif eta_seconds < 3600:
                    return f"{int(eta_seconds // 60)}m {int(eta_seconds % 60)}s"
                else:
                    return f"{int(eta_seconds // 3600)}h {int((eta_seconds % 3600) // 60)}m"
            
            return "∞"
        else:
            # Fichier simple
            eta = self.get_eta()
            if eta is None:
                return "∞"

            if eta < 60:
                return f"{int(eta)}s"
            elif eta < 3600:
                return f"{int(eta // 60)}m {int(eta % 60)}s"
            else:
                return f"{int(eta // 3600)}h {int((eta % 3600) // 60)}m"

    def add_child_file(self, file_item: 'FileTransferItem') -> None:
        """Ajoute un fichier enfant au transfert de dossier"""
        if self.is_folder_transfer:
            self.child_files[file_item.file_path] = file_item
    
    def update_child_file_status(self, file_path: str, status: TransferStatus, 
                               progress: int = 0, error_message: str = "") -> None:
        """Met à jour le statut d'un fichier enfant"""
        if file_path in self.child_files:
            file_item = self.child_files[file_path]
            file_item.status = status
            file_item.progress = progress
            file_item.error_message = error_message
            if status == TransferStatus.IN_PROGRESS and not file_item.start_time:
                file_item.start_time = datetime.now()
            elif status in [TransferStatus.COMPLETED, TransferStatus.ERROR, TransferStatus.CANCELLED]:
                file_item.end_time = datetime.now()
    
    def get_completed_files_count(self) -> int:
        """Retourne le nombre de fichiers terminés avec succès"""
        return sum(1 for f in self.child_files.values() if f.status == TransferStatus.COMPLETED)
    
    def get_failed_files_count(self) -> int:
        """Retourne le nombre de fichiers en erreur"""
        return sum(1 for f in self.child_files.values() if f.status == TransferStatus.ERROR)
    
    def get_failed_files(self) -> Dict[str, 'FileTransferItem']:
        """Retourne les fichiers en erreur"""
        return {path: file_item for path, file_item in self.child_files.items() 
                if file_item.status == TransferStatus.ERROR}
    
    def get_overall_progress(self) -> int:
        """Calcule le progrès global basé sur les fichiers enfants (pondéré par taille)"""
        if not self.child_files:
            return self.progress
        
        # Calcul pondéré par la taille des fichiers
        total_size = sum(f.file_size for f in self.child_files.values())
        if total_size == 0:
            # Si pas de taille, utiliser le comptage simple
            completed_files = sum(1 for f in self.child_files.values() 
                                if f.status in [TransferStatus.COMPLETED, TransferStatus.ERROR])
            return int((completed_files / len(self.child_files)) * 100)
        
        # Progrès pondéré par taille
        completed_bytes = 0
        for f in self.child_files.values():
            if f.status == TransferStatus.COMPLETED:
                completed_bytes += f.file_size
            elif f.status == TransferStatus.IN_PROGRESS:
                completed_bytes += (f.file_size * f.progress / 100)
        
        return int((completed_bytes / total_size) * 100) if total_size > 0 else 0


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
        
        # Throttling pour les signaux UI
        self._last_update_time = {}  # Par transfer_id
        self._update_interval = 0.05  # Réduit à 0.05s pour des mises à jour très fréquentes des statistiques de dossier

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
            
            # Pour les dossiers, calculer le progrès global automatiquement
            if transfer.is_folder_transfer and transfer.child_files:
                transfer.progress = transfer.get_overall_progress()
            else:
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

    def add_file_to_transfer(self, transfer_id: str, file_item: FileTransferItem) -> None:
        """
        Ajoute un fichier à un transfert de dossier
        
        Args:
            transfer_id: ID du transfert parent
            file_item: Élément de fichier à ajouter
        """
        if transfer_id in self.transfers:
            transfer = self.transfers[transfer_id]
            transfer.add_child_file(file_item)
            self.transfer_updated.emit(transfer_id)
    
    def update_file_status_in_transfer(self, transfer_id: str, file_path: str, 
                                     status: TransferStatus, progress: int = 0, 
                                     error_message: str = "", speed: float = 0) -> None:
        """
        Met à jour le statut d'un fichier dans un transfert de dossier
        
        Args:
            transfer_id: ID du transfert parent
            file_path: Chemin du fichier
            status: Nouveau statut
            progress: Progrès en pourcentage
            error_message: Message d'erreur si applicable
            speed: Vitesse en bytes/seconde
        """
        if transfer_id in self.transfers:
            transfer = self.transfers[transfer_id]
            transfer.update_child_file_status(file_path, status, progress, error_message)
            
            # Mettre à jour la vitesse du fichier
            if file_path in transfer.child_files:
                transfer.child_files[file_path].speed = speed
            
            # CHANGEMENT: Approche simplifiée pour le statut du dossier
            if transfer.is_folder_transfer:
                # Dès qu'un fichier commence, le dossier passe en cours
                if status == TransferStatus.IN_PROGRESS and transfer.status == TransferStatus.PENDING:
                    transfer.status = TransferStatus.IN_PROGRESS
                    transfer.start_time = datetime.now()
                    print(f"DEBUG: Dossier {transfer.file_name} passé en IN_PROGRESS")
                
                # Mettre à jour le progrès global du transfert
                overall_progress = transfer.get_overall_progress()
                transfer.progress = overall_progress
                
                # Déterminer le statut global basé sur les fichiers
                failed_count = transfer.get_failed_files_count()
                completed_count = transfer.get_completed_files_count()
                in_progress_count = sum(1 for f in transfer.child_files.values() if f.status == TransferStatus.IN_PROGRESS)
                total_count = len(transfer.child_files)
                
                # Vérifier si tous les fichiers sont traités
                if completed_count + failed_count == total_count and total_count > 0:
                    # Tous les fichiers sont traités
                    if failed_count == 0:
                        # Tous réussis
                        transfer.status = TransferStatus.COMPLETED
                    elif completed_count > 0:
                        # Certains réussis, certains échoués - garder en erreur mais avec infos détaillées
                        transfer.status = TransferStatus.ERROR
                        transfer.error_message = f"{failed_count} fichier(s) échoué(s) sur {total_count}"
                    else:
                        # Tous échoués
                        transfer.status = TransferStatus.ERROR
                        transfer.error_message = "Tous les fichiers ont échoué"
                    
                    transfer.end_time = datetime.now()
                    print(f"DEBUG: Dossier {transfer.file_name} terminé avec statut {transfer.status.value}")
            
            # Toujours émettre immédiatement pour les changements de statut importants
            if status == TransferStatus.IN_PROGRESS or transfer.status in [TransferStatus.COMPLETED, TransferStatus.ERROR]:
                self.transfer_updated.emit(transfer_id)
            else:
                self._emit_transfer_updated_throttled(transfer_id)
    
    def _emit_transfer_updated_throttled(self, transfer_id: str) -> None:
        """Émet le signal transfer_updated avec throttling pour éviter la surcharge UI"""
        import time
        current_time = time.time()
        last_update = self._last_update_time.get(transfer_id, 0)
        
        # Émettre seulement si assez de temps s'est écoulé
        if current_time - last_update >= self._update_interval:
            self._last_update_time[transfer_id] = current_time
            self.transfer_updated.emit(transfer_id)
    
    def get_failed_files_for_retry(self, transfer_id: str) -> Dict[str, FileTransferItem]:
        """
        Retourne les fichiers en erreur d'un transfert pour retry
        
        Args:
            transfer_id: ID du transfert
            
        Returns:
            Dictionnaire des fichiers en erreur
        """
        if transfer_id in self.transfers:
            transfer = self.transfers[transfer_id]
            return transfer.get_failed_files()
        return {}
    
    def retry_failed_files(self, transfer_id: str) -> List[FileTransferItem]:
        """
        Marque les fichiers échoués d'un transfert pour retry
        
        Args:
            transfer_id: ID du transfert
            
        Returns:
            Liste des fichiers à réessayer
        """
        failed_files = []
        if transfer_id in self.transfers:
            transfer = self.transfers[transfer_id]
            for file_path, file_item in transfer.get_failed_files().items():
                file_item.status = TransferStatus.PENDING
                file_item.retry_count += 1
                file_item.error_message = ""
                file_item.start_time = None
                file_item.end_time = None
                failed_files.append(file_item)
            
            # Remettre le transfert en cours si il y a des fichiers à retry
            if failed_files:
                transfer.status = TransferStatus.IN_PROGRESS
                self.transfer_updated.emit(transfer_id)
        
        return failed_files


class TransferListModel(QStandardItemModel):
    """Modèle pour afficher la liste des transferts avec support des fichiers individuels"""

    def __init__(self, transfer_manager: TransferManager):
        """
        Initialise le modèle

        Args:
            transfer_manager: Gestionnaire de transferts
        """
        super().__init__()
        self.transfer_manager = transfer_manager
        self.setHorizontalHeaderLabels([
            "Fichier/Dossier", "Type", "Statut", "Progrès",
            "Vitesse", "ETA", "Taille", "Destination"
        ])

        # Connecter aux signaux du gestionnaire
        self.transfer_manager.transfer_added.connect(self.on_transfer_added)
        self.transfer_manager.transfer_updated.connect(self.on_transfer_updated)
        self.transfer_manager.transfer_removed.connect(self.on_transfer_removed)
        
        # Timer pour rafraîchir les statistiques de dossier
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self.refresh_folder_statistics)
        self.refresh_timer.start(200)  # Rafraîchir toutes les 0.2 secondes pour des mises à jour plus réactives

    def on_transfer_added(self, transfer_id: str) -> None:
        """Appelé quand un transfert est ajouté"""
        transfer = self.transfer_manager.get_transfer(transfer_id)
        if transfer:
            self.add_transfer_row(transfer)

    def on_transfer_updated(self, transfer_id: str) -> None:
        """Appelé quand un transfert est mis à jour"""
        transfer = self.transfer_manager.get_transfer(transfer_id)
        if transfer:
            # Pour les dossiers, forcer une mise à jour immédiate des statistiques
            if transfer.is_folder_transfer:
                self._update_folder_statistics_display(transfer)
            else:
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

        # Fichier/Dossier
        file_item = QStandardItem(transfer.file_name)
        file_item.setData(transfer.transfer_id)  # Stocker l'ID pour référence
        
        # Pour les dossiers, ajouter un indicateur expandable
        if transfer.is_folder_transfer:
            file_item.setText(f"📁 {transfer.file_name}")
            file_item.setData(True, Qt.UserRole + 1)  # Marquer comme dossier

        # Type
        type_item = QStandardItem(transfer.transfer_type.value)

        # Statut
        status_item = QStandardItem(transfer.status.value)

        # Progrès (utiliser le progrès calculé pour les dossiers)
        if transfer.is_folder_transfer and transfer.child_files:
            overall_progress = transfer.get_overall_progress()
            completed = transfer.get_completed_files_count()
            failed = transfer.get_failed_files_count()
            total = len(transfer.child_files)
            progress_text = f"{overall_progress}% ({completed + failed}/{total})"
            if failed > 0:
                progress_text += f" - {failed} erreur(s)"
        else:
            progress_text = f"{transfer.progress}%"
        progress_item = QStandardItem(progress_text)

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
        
        # Ajouter les fichiers enfants si c'est un dossier
        if transfer.is_folder_transfer and transfer.child_files:
            self.add_child_files(file_item, transfer)

    def add_child_files(self, parent_item: QStandardItem, transfer: TransferItem) -> None:
        """Ajoute les fichiers enfants sous un transfert de dossier"""
        for file_path, file_item in transfer.child_files.items():
            # Créer une ligne enfant pour chaque fichier
            child_row = []
            
            # Nom du fichier avec indentation
            name_item = QStandardItem(f"  📄 {file_item.file_name}")
            name_item.setData(file_path, Qt.UserRole)  # Stocker le chemin du fichier
            child_row.append(name_item)
            
            # Type
            child_row.append(QStandardItem("Fichier"))
            
            # Statut
            status_text = file_item.status.value
            if file_item.retry_count > 0:
                status_text += f" (Retry {file_item.retry_count})"
            child_row.append(QStandardItem(status_text))
            
            # Progrès
            child_row.append(QStandardItem(f"{file_item.progress}%"))
            
            # Vitesse
            child_row.append(QStandardItem(f"{format_file_size(int(file_item.speed))}/s" if file_item.speed > 0 else ""))
            
            # ETA
            child_row.append(QStandardItem(""))
            
            # Taille
            child_row.append(QStandardItem(format_file_size(file_item.file_size) if file_item.file_size > 0 else ""))
            
            # Destination
            child_row.append(QStandardItem(file_item.relative_path))
            
            parent_item.appendRow(child_row)

    def update_transfer_row(self, transfer: TransferItem) -> None:
        """Met à jour une ligne de transfert"""
        # Trouver la ligne correspondante
        for row in range(self.rowCount()):
            item = self.item(row, 0)
            if item and item.data() == transfer.transfer_id:
                # Mettre à jour les colonnes principales
                self.item(row, 2).setText(transfer.status.value)
                
                # Progrès avec informations détaillées pour les dossiers (utiliser le progrès calculé)
                if transfer.is_folder_transfer and transfer.child_files:
                    overall_progress = transfer.get_overall_progress()
                    completed = transfer.get_completed_files_count()
                    failed = transfer.get_failed_files_count()
                    total = len(transfer.child_files)
                    progress_text = f"{overall_progress}% ({completed + failed}/{total})"
                    if failed > 0:
                        progress_text += f" - {failed} erreur(s)"
                else:
                    progress_text = f"{transfer.progress}%"
                
                self.item(row, 3).setText(progress_text)
                self.item(row, 4).setText(transfer.get_speed_text())
                self.item(row, 5).setText(transfer.get_eta_text())
                
                # Mettre à jour les fichiers enfants
                if transfer.is_folder_transfer:
                    self.update_child_files(item, transfer)
                break

    def update_child_files(self, parent_item: QStandardItem, transfer: TransferItem) -> None:
        """Met à jour les fichiers enfants d'un transfert de dossier"""
        # Optimisation: ne pas recréer tous les enfants à chaque update
        # Vérifier si on a des enfants à ajouter
        current_child_count = parent_item.rowCount()
        target_child_count = len(transfer.child_files)
        
        # Si on n'a pas d'enfants ou pas assez, les ajouter
        if current_child_count < target_child_count:
            # Supprimer tous les enfants et les recréer (plus simple et plus fiable)
            parent_item.removeRows(0, current_child_count)
            self.add_child_files(parent_item, transfer)
        elif current_child_count > 0:
            # Mettre à jour les enfants existants seulement
            self._update_existing_child_files(parent_item, transfer)
    
    def _update_existing_child_files(self, parent_item: QStandardItem, transfer: TransferItem) -> None:
        """Met à jour les enfants existants sans les recréer"""
        file_items = list(transfer.child_files.values())
        
        for i in range(min(parent_item.rowCount(), len(file_items))):
            file_item = file_items[i]
            
            # Mettre à jour le statut (colonne 2)
            status_item = parent_item.child(i, 2)
            if status_item:
                status_text = file_item.status.value
                if file_item.retry_count > 0:
                    status_text += f" (Retry {file_item.retry_count})"
                status_item.setText(status_text)
            
            # Mettre à jour le progrès (colonne 3)
            progress_item = parent_item.child(i, 3)
            if progress_item:
                progress_item.setText(f"{file_item.progress}%")
            
            # Mettre à jour la vitesse (colonne 4)
            speed_item = parent_item.child(i, 4)
            if speed_item:
                speed_text = f"{format_file_size(int(file_item.speed))}/s" if file_item.speed > 0 else ""
                speed_item.setText(speed_text)

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

    def refresh_folder_statistics(self) -> None:
        """Rafraîchit les statistiques des dossiers en cours de transfert"""
        try:
            # Parcourir tous les transferts actifs et mettre à jour leurs statistiques
            active_transfers = self.transfer_manager.get_active_transfers()
            
            for transfer_id, transfer in active_transfers.items():
                if transfer.is_folder_transfer and transfer.child_files:
                    # Vérifier si le dossier devrait être en cours
                    in_progress_files = [f for f in transfer.child_files.values() 
                                       if f.status == TransferStatus.IN_PROGRESS]
                    completed_files = [f for f in transfer.child_files.values() 
                                     if f.status == TransferStatus.COMPLETED]
                    
                    # Si des fichiers sont en cours ou terminés et le dossier est toujours en attente
                    if (in_progress_files or completed_files) and transfer.status == TransferStatus.PENDING:
                        transfer.status = TransferStatus.IN_PROGRESS
                        if not transfer.start_time:
                            transfer.start_time = datetime.now()
                        print(f"DEBUG: Dossier {transfer.file_name} forcé en IN_PROGRESS par refresh")
                    
                    # Mettre à jour seulement les statistiques sans émettre de signal
                    self._update_folder_statistics_display(transfer)
                    
        except Exception as e:
            # Ne pas faire planter l'application pour une erreur de rafraîchissement
            print(f"Erreur lors du rafraîchissement des statistiques de dossier: {e}")
            import traceback
            traceback.print_exc()

    def _update_folder_statistics_display(self, transfer: TransferItem) -> None:
        """Met à jour l'affichage des statistiques d'un dossier spécifique"""
        # Trouver la ligne correspondante
        for row in range(self.rowCount()):
            item = self.item(row, 0)
            if item and item.data() == transfer.transfer_id:
                # Debug: Afficher les statistiques calculées
                overall_progress = transfer.get_overall_progress()
                completed = transfer.get_completed_files_count()
                failed = transfer.get_failed_files_count()
                total = len(transfer.child_files)
                speed_text = transfer.get_speed_text()
                eta_text = transfer.get_eta_text()
                
                # Mettre à jour le statut (colonne 2)
                status_item = self.item(row, 2)
                if status_item:
                    status_item.setText(transfer.status.value)
                
                # Progrès avec informations détaillées (colonne 3)
                progress_text = f"{overall_progress}% ({completed + failed}/{total})"
                if failed > 0:
                    progress_text += f" - {failed} erreur(s)"
                
                # Mettre à jour l'affichage
                progress_item = self.item(row, 3)
                if progress_item:
                    progress_item.setText(progress_text)
                
                # Vitesse (colonne 4)
                speed_item = self.item(row, 4)  
                if speed_item:
                    speed_item.setText(speed_text)
                
                # ETA (colonne 5)
                eta_item = self.item(row, 5)
                if eta_item:
                    eta_item.setText(eta_text)
                
                # Debug pour les dossiers qui devraient être actifs
                if transfer.child_files and any(f.status in [TransferStatus.IN_PROGRESS, TransferStatus.COMPLETED] for f in transfer.child_files.values()):
                    if transfer.status == TransferStatus.PENDING:
                        print(f"WARNING: Dossier {transfer.file_name} reste en PENDING malgré fichiers actifs!")
                
                break
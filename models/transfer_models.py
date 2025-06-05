
"""
Modèles pour la gestion des transferts avec support des sous-transferts
"""

import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum
from PyQt5.QtCore import QAbstractItemModel, QModelIndex, Qt, pyqtSignal, QObject


class TransferType(Enum):
    """Types de transferts"""
    UPLOAD_FILE = "upload_file"
    UPLOAD_FOLDER = "upload_folder"
    DOWNLOAD_FILE = "download_file"
    DOWNLOAD_FOLDER = "download_folder"


class TransferStatus(Enum):
    """États des transferts"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ERROR = "error"
    CANCELLED = "cancelled"
    PAUSED = "paused"


@dataclass
class SubTransfer:
    """Représente un sous-transfert (fichier individuel dans un dossier)"""
    id: str
    parent_transfer_id: str
    name: str
    relative_path: str
    size: int
    status: TransferStatus = TransferStatus.PENDING
    progress: int = 0
    error_message: str = ""
    start_time: Optional[float] = None
    end_time: Optional[float] = None


@dataclass
class Transfer:
    """Représente un transfert principal"""
    id: str
    transfer_type: TransferType
    source_path: str
    destination_path: str
    name: str
    total_size: int
    status: TransferStatus = TransferStatus.PENDING
    progress: int = 0
    transferred_bytes: int = 0
    speed: float = 0.0
    error_message: str = ""
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    
    # Nouveaux champs pour les sous-transferts
    sub_transfers: Dict[str, SubTransfer] = field(default_factory=dict)
    total_sub_transfers: int = 0
    completed_sub_transfers: int = 0
    failed_sub_transfers: int = 0


class TransferManager(QObject):
    """Gestionnaire des transferts avec support des sous-transferts"""
    
    transfer_added = pyqtSignal(str)  # transfer_id
    transfer_updated = pyqtSignal(str)  # transfer_id
    transfer_removed = pyqtSignal(str)  # transfer_id
    sub_transfer_updated = pyqtSignal(str, str)  # transfer_id, sub_transfer_id
    
    def __init__(self):
        super().__init__()
        self.transfers: Dict[str, Transfer] = {}
    
    def add_transfer(self, transfer_type: TransferType, source_path: str,
                    destination_path: str, name: str, total_size: int) -> str:
        """
        Ajoute un nouveau transfert
        
        Returns:
            ID du transfert créé
        """
        transfer_id = str(uuid.uuid4())
        
        transfer = Transfer(
            id=transfer_id,
            transfer_type=transfer_type,
            source_path=source_path,
            destination_path=destination_path,
            name=name,
            total_size=total_size,
            start_time=time.time()
        )
        
        self.transfers[transfer_id] = transfer
        self.transfer_added.emit(transfer_id)
        
        return transfer_id
    
    def add_sub_transfer(self, parent_transfer_id: str, name: str,
                        relative_path: str, size: int) -> str:
        """
        Ajoute un sous-transfert à un transfert principal
        
        Returns:
            ID du sous-transfert créé
        """
        if parent_transfer_id not in self.transfers:
            raise ValueError(f"Transfert parent {parent_transfer_id} introuvable")
        
        sub_transfer_id = str(uuid.uuid4())
        
        sub_transfer = SubTransfer(
            id=sub_transfer_id,
            parent_transfer_id=parent_transfer_id,
            name=name,
            relative_path=relative_path,
            size=size,
            start_time=time.time()
        )
        
        parent_transfer = self.transfers[parent_transfer_id]
        parent_transfer.sub_transfers[sub_transfer_id] = sub_transfer
        parent_transfer.total_sub_transfers += 1
        
        self.sub_transfer_updated.emit(parent_transfer_id, sub_transfer_id)
        
        return sub_transfer_id
    
    def update_sub_transfer_status(self, parent_transfer_id: str, sub_transfer_id: str,
                                  status: TransferStatus, error_message: str = "") -> None:
        """Met à jour le statut d'un sous-transfert"""
        if parent_transfer_id in self.transfers:
            parent_transfer = self.transfers[parent_transfer_id]
            if sub_transfer_id in parent_transfer.sub_transfers:
                sub_transfer = parent_transfer.sub_transfers[sub_transfer_id]
                old_status = sub_transfer.status
                sub_transfer.status = status
                sub_transfer.error_message = error_message
                
                if status in [TransferStatus.COMPLETED, TransferStatus.ERROR, TransferStatus.CANCELLED]:
                    sub_transfer.end_time = time.time()
                
                # Mettre à jour les compteurs du parent
                if old_status != TransferStatus.COMPLETED and status == TransferStatus.COMPLETED:
                    parent_transfer.completed_sub_transfers += 1
                elif old_status != TransferStatus.ERROR and status == TransferStatus.ERROR:
                    parent_transfer.failed_sub_transfers += 1
                
                # Mettre à jour le progrès global du transfert parent
                self._update_parent_progress(parent_transfer_id)
                
                self.sub_transfer_updated.emit(parent_transfer_id, sub_transfer_id)
    
    def update_sub_transfer_progress(self, parent_transfer_id: str, sub_transfer_id: str,
                                   progress: int) -> None:
        """Met à jour le progrès d'un sous-transfert"""
        if parent_transfer_id in self.transfers:
            parent_transfer = self.transfers[parent_transfer_id]
            if sub_transfer_id in parent_transfer.sub_transfers:
                sub_transfer = parent_transfer.sub_transfers[sub_transfer_id]
                sub_transfer.progress = progress
                
                # Mettre à jour le progrès global
                self._update_parent_progress(parent_transfer_id)
                
                self.sub_transfer_updated.emit(parent_transfer_id, sub_transfer_id)
    
    def _update_parent_progress(self, transfer_id: str) -> None:
        """Met à jour le progrès du transfert parent basé sur ses sous-transferts"""
        transfer = self.transfers[transfer_id]
        
        if transfer.total_sub_transfers > 0:
            # Calculer le progrès moyen des sous-transferts
            total_progress = sum(sub.progress for sub in transfer.sub_transfers.values())
            average_progress = total_progress / transfer.total_sub_transfers
            transfer.progress = int(average_progress)
            
            # Mettre à jour le statut si nécessaire
            if transfer.completed_sub_transfers == transfer.total_sub_transfers:
                if transfer.failed_sub_transfers == 0:
                    transfer.status = TransferStatus.COMPLETED
                    transfer.end_time = time.time()
                else:
                    transfer.status = TransferStatus.ERROR
                    transfer.error_message = f"{transfer.failed_sub_transfers} fichier(s) échoué(s)"
        
        self.transfer_updated.emit(transfer_id)
    
    def update_transfer_status(self, transfer_id: str, status: TransferStatus,
                              error_message: str = "") -> None:
        """Met à jour le statut d'un transfert"""
        if transfer_id in self.transfers:
            transfer = self.transfers[transfer_id]
            transfer.status = status
            transfer.error_message = error_message
            
            if status in [TransferStatus.COMPLETED, TransferStatus.ERROR, TransferStatus.CANCELLED]:
                transfer.end_time = time.time()
            
            self.transfer_updated.emit(transfer_id)
    
    def update_transfer_progress(self, transfer_id: str, progress: int,
                               transferred_bytes: int = 0, speed: float = 0.0) -> None:
        """Met à jour le progrès d'un transfert"""
        if transfer_id in self.transfers:
            transfer = self.transfers[transfer_id]
            transfer.progress = progress
            transfer.transferred_bytes = transferred_bytes
            transfer.speed = speed
            
            self.transfer_updated.emit(transfer_id)
    
    def get_transfer(self, transfer_id: str) -> Optional[Transfer]:
        """Récupère un transfert par son ID"""
        return self.transfers.get(transfer_id)
    
    def get_sub_transfer(self, parent_transfer_id: str, sub_transfer_id: str) -> Optional[SubTransfer]:
        """Récupère un sous-transfert"""
        if parent_transfer_id in self.transfers:
            parent_transfer = self.transfers[parent_transfer_id]
            return parent_transfer.sub_transfers.get(sub_transfer_id)
        return None
    
    def get_all_transfers(self) -> Dict[str, Transfer]:
        """Récupère tous les transferts"""
        return self.transfers.copy()
    
    def get_active_transfers(self) -> Dict[str, Transfer]:
        """Récupère les transferts actifs"""
        return {
            tid: transfer for tid, transfer in self.transfers.items()
            if transfer.status in [TransferStatus.PENDING, TransferStatus.IN_PROGRESS, TransferStatus.PAUSED]
        }
    
    def get_completed_transfers(self) -> Dict[str, Transfer]:
        """Récupère les transferts terminés"""
        return {
            tid: transfer for tid, transfer in self.transfers.items()
            if transfer.status in [TransferStatus.COMPLETED, TransferStatus.ERROR, TransferStatus.CANCELLED]
        }
    
    def get_failed_sub_transfers(self, transfer_id: str) -> List[SubTransfer]:
        """Récupère les sous-transferts échoués d'un transfert"""
        if transfer_id in self.transfers:
            transfer = self.transfers[transfer_id]
            return [sub for sub in transfer.sub_transfers.values() 
                   if sub.status == TransferStatus.ERROR]
        return []
    
    def retry_failed_sub_transfers(self, transfer_id: str) -> List[str]:
        """Remet les sous-transferts échoués en attente pour retry"""
        failed_sub_transfers = []
        if transfer_id in self.transfers:
            transfer = self.transfers[transfer_id]
            for sub_transfer in transfer.sub_transfers.values():
                if sub_transfer.status == TransferStatus.ERROR:
                    sub_transfer.status = TransferStatus.PENDING
                    sub_transfer.error_message = ""
                    sub_transfer.progress = 0
                    failed_sub_transfers.append(sub_transfer.id)
            
            # Recalculer les compteurs
            transfer.failed_sub_transfers = 0
            transfer.completed_sub_transfers = sum(
                1 for sub in transfer.sub_transfers.values() 
                if sub.status == TransferStatus.COMPLETED
            )
            
            if failed_sub_transfers:
                transfer.status = TransferStatus.PENDING
                self.transfer_updated.emit(transfer_id)
        
        return failed_sub_transfers
    
    def remove_transfer(self, transfer_id: str) -> None:
        """Supprime un transfert"""
        if transfer_id in self.transfers:
            del self.transfers[transfer_id]
            self.transfer_removed.emit(transfer_id)
    
    def clear_completed_transfers(self) -> None:
        """Supprime tous les transferts terminés"""
        completed_ids = list(self.get_completed_transfers().keys())
        for transfer_id in completed_ids:
            self.remove_transfer(transfer_id)
    
    def cancel_transfer(self, transfer_id: str) -> None:
        """Annule un transfert"""
        self.update_transfer_status(transfer_id, TransferStatus.CANCELLED)
    
    def pause_transfer(self, transfer_id: str) -> None:
        """Suspend un transfert"""
        self.update_transfer_status(transfer_id, TransferStatus.PAUSED)
    
    def resume_transfer(self, transfer_id: str) -> None:
        """Reprend un transfert"""
        self.update_transfer_status(transfer_id, TransferStatus.IN_PROGRESS)


class TransferListModel(QAbstractItemModel):
    """Modèle pour afficher les transferts dans une vue arborescente avec sous-transferts"""
    
    def __init__(self, transfer_manager: TransferManager):
        super().__init__()
        self.transfer_manager = transfer_manager
        self.headers = ["Nom", "Type", "Statut", "Progrès", "Taille", "Vitesse", "Temps"]
        
        # Connecter les signaux
        self.transfer_manager.transfer_added.connect(self.on_transfer_added)
        self.transfer_manager.transfer_updated.connect(self.on_transfer_updated)
        self.transfer_manager.transfer_removed.connect(self.on_transfer_removed)
        self.transfer_manager.sub_transfer_updated.connect(self.on_sub_transfer_updated)
    
    def rowCount(self, parent=QModelIndex()):
        if not parent.isValid():
            # Niveau racine : nombre de transferts
            return len(self.transfer_manager.transfers)
        else:
            # Niveau enfant : nombre de sous-transferts
            transfer_id = self.get_transfer_id_from_index(parent)
            if transfer_id:
                transfer = self.transfer_manager.get_transfer(transfer_id)
                if transfer:
                    return len(transfer.sub_transfers)
        return 0
    
    def columnCount(self, parent=QModelIndex()):
        return len(self.headers)
    
    def hasChildren(self, parent=QModelIndex()):
        if not parent.isValid():
            return len(self.transfer_manager.transfers) > 0
        else:
            # Un transfert a des enfants s'il a des sous-transferts
            transfer_id = self.get_transfer_id_from_index(parent)
            if transfer_id:
                transfer = self.transfer_manager.get_transfer(transfer_id)
                return transfer and len(transfer.sub_transfers) > 0
        return False
    
    def index(self, row, column, parent=QModelIndex()):
        if not parent.isValid():
            # Index pour un transfert principal
            transfer_ids = list(self.transfer_manager.transfers.keys())
            if 0 <= row < len(transfer_ids):
                return self.createIndex(row, column, transfer_ids[row])
        else:
            # Index pour un sous-transfert
            transfer_id = self.get_transfer_id_from_index(parent)
            if transfer_id:
                transfer = self.transfer_manager.get_transfer(transfer_id)
                if transfer:
                    sub_transfer_ids = list(transfer.sub_transfers.keys())
                    if 0 <= row < len(sub_transfer_ids):
                        return self.createIndex(row, column, f"{transfer_id}:{sub_transfer_ids[row]}")
        
        return QModelIndex()
    
    def parent(self, index):
        if not index.isValid():
            return QModelIndex()
        
        # Si l'ID contient ':', c'est un sous-transfert
        node_id = index.internalPointer()
        if isinstance(node_id, str) and ':' in node_id:
            transfer_id = node_id.split(':')[0]
            transfer_ids = list(self.transfer_manager.transfers.keys())
            if transfer_id in transfer_ids:
                row = transfer_ids.index(transfer_id)
                return self.createIndex(row, 0, transfer_id)
        
        return QModelIndex()
    
    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        
        node_id = index.internalPointer()
        column = index.column()
        
        if isinstance(node_id, str) and ':' in node_id:
            # C'est un sous-transfert
            transfer_id, sub_transfer_id = node_id.split(':', 1)
            sub_transfer = self.transfer_manager.get_sub_transfer(transfer_id, sub_transfer_id)
            if sub_transfer:
                return self._get_sub_transfer_data(sub_transfer, column, role)
        else:
            # C'est un transfert principal
            transfer = self.transfer_manager.get_transfer(node_id)
            if transfer:
                return self._get_transfer_data(transfer, column, role)
        
        return None
    
    def _get_transfer_data(self, transfer: Transfer, column: int, role: int):
        """Récupère les données d'affichage pour un transfert principal"""
        if role == Qt.DisplayRole:
            if column == 0:  # Nom
                return transfer.name
            elif column == 1:  # Type
                type_icons = {
                    TransferType.UPLOAD_FILE: "📤 Fichier",
                    TransferType.UPLOAD_FOLDER: "📁 Dossier",
                    TransferType.DOWNLOAD_FILE: "📥 Fichier",
                    TransferType.DOWNLOAD_FOLDER: "📁 Dossier"
                }
                return type_icons.get(transfer.transfer_type, "❓")
            elif column == 2:  # Statut
                status_icons = {
                    TransferStatus.PENDING: "⏳ En attente",
                    TransferStatus.IN_PROGRESS: "🔄 En cours",
                    TransferStatus.COMPLETED: "✅ Terminé",
                    TransferStatus.ERROR: "❌ Erreur",
                    TransferStatus.CANCELLED: "🚫 Annulé",
                    TransferStatus.PAUSED: "⏸️ Suspendu"
                }
                status_text = status_icons.get(transfer.status, "❓")
                if transfer.total_sub_transfers > 0:
                    status_text += f" ({transfer.completed_sub_transfers}/{transfer.total_sub_transfers})"
                return status_text
            elif column == 3:  # Progrès
                return f"{transfer.progress}%"
            elif column == 4:  # Taille
                return self._format_size(transfer.total_size)
            elif column == 5:  # Vitesse
                return self._format_speed(transfer.speed)
            elif column == 6:  # Temps
                return self._format_duration(transfer.start_time, transfer.end_time)
        
        return None
    
    def _get_sub_transfer_data(self, sub_transfer: SubTransfer, column: int, role: int):
        """Récupère les données d'affichage pour un sous-transfert"""
        if role == Qt.DisplayRole:
            if column == 0:  # Nom
                return f"  📄 {sub_transfer.relative_path}"
            elif column == 1:  # Type
                return "Fichier"
            elif column == 2:  # Statut
                status_icons = {
                    TransferStatus.PENDING: "⏳ En attente",
                    TransferStatus.IN_PROGRESS: "🔄 En cours",
                    TransferStatus.COMPLETED: "✅ Terminé",
                    TransferStatus.ERROR: "❌ Erreur",
                    TransferStatus.CANCELLED: "🚫 Annulé",
                    TransferStatus.PAUSED: "⏸️ Suspendu"
                }
                status_text = status_icons.get(sub_transfer.status, "❓")
                if sub_transfer.error_message:
                    status_text += f" - {sub_transfer.error_message[:50]}..."
                return status_text
            elif column == 3:  # Progrès
                return f"{sub_transfer.progress}%"
            elif column == 4:  # Taille
                return self._format_size(sub_transfer.size)
            elif column == 5:  # Vitesse
                return ""  # Pas de vitesse individuelle pour les sous-transferts
            elif column == 6:  # Temps
                return self._format_duration(sub_transfer.start_time, sub_transfer.end_time)
        
        return None
    
    def headerData(self, section, orientation, role):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.headers[section]
        return None
    
    def get_transfer_id_from_index(self, index):
        """Récupère l'ID du transfert depuis un index"""
        if index.isValid():
            node_id = index.internalPointer()
            if isinstance(node_id, str):
                if ':' in node_id:
                    return node_id.split(':')[0]
                else:
                    return node_id
        return None
    
    def get_transfer_id_from_row(self, row):
        """Récupère l'ID du transfert depuis un numéro de ligne"""
        transfer_ids = list(self.transfer_manager.transfers.keys())
        if 0 <= row < len(transfer_ids):
            return transfer_ids[row]
        return None
    
    def _format_size(self, size: int) -> str:
        """Formate la taille en bytes"""
        if size < 1024:
            return f"{size} B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        elif size < 1024 * 1024 * 1024:
            return f"{size / (1024 * 1024):.1f} MB"
        else:
            return f"{size / (1024 * 1024 * 1024):.1f} GB"
    
    def _format_speed(self, speed: float) -> str:
        """Formate la vitesse"""
        if speed == 0:
            return ""
        return self._format_size(int(speed)) + "/s"
    
    def _format_duration(self, start_time: Optional[float], end_time: Optional[float]) -> str:
        """Formate la durée"""
        if not start_time:
            return ""
        
        if end_time:
            duration = end_time - start_time
        else:
            duration = time.time() - start_time
        
        if duration < 60:
            return f"{duration:.0f}s"
        elif duration < 3600:
            return f"{duration // 60:.0f}m {duration % 60:.0f}s"
        else:
            return f"{duration // 3600:.0f}h {(duration % 3600) // 60:.0f}m"
    
    def on_transfer_added(self, transfer_id: str):
        """Gère l'ajout d'un transfert"""
        self.beginInsertRows(QModelIndex(), self.rowCount(), self.rowCount())
        self.endInsertRows()
    
    def on_transfer_updated(self, transfer_id: str):
        """Gère la mise à jour d'un transfert"""
        transfer_ids = list(self.transfer_manager.transfers.keys())
        if transfer_id in transfer_ids:
            row = transfer_ids.index(transfer_id)
            top_left = self.index(row, 0)
            bottom_right = self.index(row, self.columnCount() - 1)
            self.dataChanged.emit(top_left, bottom_right)
    
    def on_transfer_removed(self, transfer_id: str):
        """Gère la suppression d'un transfert"""
        self.beginResetModel()
        self.endResetModel()
    
    def on_sub_transfer_updated(self, transfer_id: str, sub_transfer_id: str):
        """Gère la mise à jour d'un sous-transfert"""
        # Mettre à jour l'affichage du transfert parent et de ses enfants
        transfer_ids = list(self.transfer_manager.transfers.keys())
        if transfer_id in transfer_ids:
            row = transfer_ids.index(transfer_id)
            parent_index = self.index(row, 0)
            
            # Mettre à jour le parent
            top_left = self.index(row, 0)
            bottom_right = self.index(row, self.columnCount() - 1)
            self.dataChanged.emit(top_left, bottom_right)
            
            # Mettre à jour les enfants
            transfer = self.transfer_manager.get_transfer(transfer_id)
            if transfer and transfer.sub_transfers:
                sub_transfer_ids = list(transfer.sub_transfers.keys())
                if sub_transfer_id in sub_transfer_ids:
                    sub_row = sub_transfer_ids.index(sub_transfer_id)
                    child_top_left = self.index(sub_row, 0, parent_index)
                    child_bottom_right = self.index(sub_row, self.columnCount() - 1, parent_index)
                    self.dataChanged.emit(child_top_left, child_bottom_right)

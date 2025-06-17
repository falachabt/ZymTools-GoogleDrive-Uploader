"""
Modèles de données pour la gestion des transferts - VERSION OPTIMISÉE HAUTE PERFORMANCE
"""

import os
import sqlite3
import threading
import queue
from datetime import datetime
from enum import Enum
from typing import Dict, Any, Optional, List
from PyQt5.QtCore import QObject, pyqtSignal, QTimer, QMutex, QMutexLocker
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
    # Type pour les fichiers individuels dans un dossier
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
        self.parent_transfer_id = parent_transfer_id
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
    """Gestionnaire de transferts OPTIMISÉ pour gros volumes - VERSION HAUTE PERFORMANCE"""

    # Signaux existants (gardés)
    transfer_added = pyqtSignal(str)
    transfer_updated = pyqtSignal(str)
    transfer_removed = pyqtSignal(str)
    transfer_status_changed = pyqtSignal(str, TransferStatus)

    # NOUVEAUX signaux pour batch (plus efficaces)
    batch_transfers_updated = pyqtSignal(list)  # [transfer_ids] - groupé
    stats_updated = pyqtSignal(dict)  # {status: count} - compteurs rapides

    def __init__(self):
        """Initialise le gestionnaire de transferts HAUTE PERFORMANCE"""
        super().__init__()

        # Storage hybride : SQLite + cache mémoire
        self.db_path = ":memory:"  # Base en mémoire = ultra rapide
        self.db_lock = threading.RLock()
        self._init_database()

        # Cache mémoire pour les transferts actifs uniquement
        self.transfers: Dict[str, TransferItem] = {}  # Garde le nom existant
        self.cache_lock = QMutex()

        # OPTIMISATION : Queue pour les mises à jour batch
        self.update_queue = queue.Queue()
        self.batch_timer = QTimer()
        self.batch_timer.timeout.connect(self._process_batch_updates)
        self.batch_timer.start(200)  # Traiter toutes les 200ms

        # Compteurs rapides (évite les requêtes COUNT coûteuses)
        self.fast_counts = {
            TransferStatus.PENDING: 0,
            TransferStatus.IN_PROGRESS: 0,
            TransferStatus.COMPLETED: 0,
            TransferStatus.ERROR: 0,
            TransferStatus.CANCELLED: 0,
            TransferStatus.PAUSED: 0
        }

        # Auto-nettoyage pour éviter l'accumulation
        self.cleanup_timer = QTimer()
        self.cleanup_timer.timeout.connect(self._auto_cleanup_completed)
        self.cleanup_timer.start(60000)  # Nettoyer toutes les minutes

        self._next_id = 1

    def _init_database(self):
        """Initialise SQLite avec index optimisés"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS transfers (
                    transfer_id TEXT PRIMARY KEY,
                    transfer_type TEXT NOT NULL,
                    source_path TEXT NOT NULL,
                    destination_path TEXT NOT NULL,
                    file_name TEXT NOT NULL,
                    file_size INTEGER DEFAULT 0,
                    parent_transfer_id TEXT,
                    status TEXT DEFAULT 'PENDING',
                    progress INTEGER DEFAULT 0,
                    speed REAL DEFAULT 0,
                    error_message TEXT DEFAULT '',
                    start_time REAL,
                    end_time REAL,
                    bytes_transferred INTEGER DEFAULT 0,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
            """)

            # Index pour les requêtes fréquentes
            conn.execute("CREATE INDEX IF NOT EXISTS idx_status ON transfers(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_parent ON transfers(parent_transfer_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_type ON transfers(transfer_type)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_updated ON transfers(updated_at)")
            conn.commit()

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
        self.fast_counts[TransferStatus.PENDING] += 1
        self.transfer_added.emit(transfer_id)
        return transfer_id

    def add_folder_transfer_with_files(self, folder_path: str, destination_path: str,
                                       folder_name: str) -> tuple:
        """VERSION OPTIMISÉE - Ajoute dossier + fichiers en BULK ultra-rapide"""

        # 1. Créer le transfert principal du dossier (en mémoire)
        total_size = self._calculate_folder_size(folder_path)
        folder_transfer_id = self.generate_transfer_id()

        folder_transfer = TransferItem(
            folder_transfer_id, TransferType.UPLOAD_FOLDER,
            folder_path, destination_path, folder_name, total_size
        )

        # Ajouter en cache mémoire
        self.transfers[folder_transfer_id] = folder_transfer

        # 2. BULK INSERT - Collecter tous les fichiers d'un coup
        file_transfers_data = []
        file_transfer_ids = []

        try:
            for root, dirs, files in os.walk(folder_path):
                for file in files:
                    if not file.lower().endswith('.tif'):
                        file_path = os.path.join(root, file)
                        rel_path = os.path.relpath(file_path, folder_path)

                        try:
                            file_size = os.path.getsize(file_path)
                            file_transfer_id = self.generate_transfer_id()

                            # Préparer pour bulk insert
                            now = datetime.now().timestamp()
                            file_transfers_data.append((
                                file_transfer_id, 'UPLOAD_FILE_IN_FOLDER',
                                file_path, destination_path, rel_path, file_size,
                                folder_transfer_id, 'PENDING', 0, 0, '', None, None, 0, now, now
                            ))

                            file_transfer_ids.append(file_transfer_id)

                        except OSError:
                            continue
        except OSError:
            pass

        # 3. BULK INSERT en base (1 seule requête pour tous les fichiers)
        if file_transfers_data:
            with sqlite3.connect(self.db_path) as conn:
                conn.executemany("""
                    INSERT INTO transfers 
                    (transfer_id, transfer_type, source_path, destination_path, file_name, 
                     file_size, parent_transfer_id, status, progress, speed, error_message, 
                     start_time, end_time, bytes_transferred, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, file_transfers_data)
                conn.commit()

        # 4. Mettre à jour les compteurs rapidement
        self.fast_counts[TransferStatus.PENDING] += len(file_transfer_ids) + 1

        # 5. Émettre signaux
        self.transfer_added.emit(folder_transfer_id)
        if len(file_transfer_ids) > 100:
            # Pour gros volumes, émettre signal batch
            self.batch_transfers_updated.emit(file_transfer_ids)
        else:
            # Pour petits volumes, émettre signaux individuels
            for fid in file_transfer_ids:
                self.transfer_added.emit(fid)

        self.stats_updated.emit(self.fast_counts.copy())

        print(f"✅ Dossier ajouté: {folder_name} ({len(file_transfer_ids)} fichiers en bulk)")
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
        """VERSION OPTIMISÉE - Queue les mises à jour pour traitement batch"""

        # Mettre en queue pour traitement batch (évite les mises à jour individuelles coûteuses)
        update_data = {
            'progress': progress,
            'bytes_transferred': bytes_transferred,
            'speed': speed,
            'updated_at': datetime.now().timestamp()
        }

        self.update_queue.put(('progress', transfer_id, update_data))

    def update_transfer_status(self, transfer_id: str, status: TransferStatus,
                               error_message: str = "") -> None:
        """VERSION OPTIMISÉE - Queue les changements de statut"""

        update_data = {
            'status': status.value,
            'error_message': error_message,
            'updated_at': datetime.now().timestamp()
        }

        if status == TransferStatus.IN_PROGRESS:
            update_data['start_time'] = datetime.now().timestamp()
        elif status in [TransferStatus.COMPLETED, TransferStatus.ERROR, TransferStatus.CANCELLED]:
            update_data['end_time'] = datetime.now().timestamp()
            if status == TransferStatus.COMPLETED:
                update_data['progress'] = 100

        self.update_queue.put(('status', transfer_id, update_data))

    def _process_batch_updates(self) -> None:
        """Traite toutes les mises à jour en batch - HAUTE PERFORMANCE"""
        updates = []
        status_changes = []

        # Collecter toutes les mises à jour en attente
        try:
            while True:
                update_type, transfer_id, data = self.update_queue.get_nowait()
                updates.append((update_type, transfer_id, data))

                if update_type == 'status' and 'status' in data:
                    status_changes.append((transfer_id, data['status']))

        except queue.Empty:
            pass

        if not updates:
            return

        # Traitement par batch en mémoire
        updated_ids = []
        db_updates = []

        for update_type, transfer_id, data in updates:
            updated_ids.append(transfer_id)

            # Mettre à jour le cache mémoire si présent
            if transfer_id in self.transfers:
                transfer = self.transfers[transfer_id]
                old_status = transfer.status

                # Appliquer les changements
                for key, value in data.items():
                    if key == 'status':
                        transfer.status = TransferStatus(value)
                    elif hasattr(transfer, key):
                        setattr(transfer, key, value)

                # Mettre à jour les compteurs rapides
                if 'status' in data:
                    new_status = TransferStatus(data['status'])
                    if old_status != new_status:
                        self.fast_counts[old_status] = max(0, self.fast_counts[old_status] - 1)
                        self.fast_counts[new_status] = self.fast_counts.get(new_status, 0) + 1
                        self.transfer_status_changed.emit(transfer_id, new_status)

            # Préparer mise à jour base de données
            set_clauses = []
            values = []
            for key, value in data.items():
                set_clauses.append(f"{key} = ?")
                values.append(value)

            if set_clauses:
                values.append(transfer_id)
                db_updates.append((set_clauses, values))

        # Mise à jour DB par batch (1 transaction pour tout)
        if db_updates:
            self._batch_update_database(db_updates)

        # Émettre signaux groupés
        if updated_ids:
            if len(updated_ids) > 50:
                self.batch_transfers_updated.emit(updated_ids)
            else:
                for uid in updated_ids:
                    self.transfer_updated.emit(uid)

            self.stats_updated.emit(self.fast_counts.copy())

        # Si c'est un fichier individuel, mettre à jour le parent
        for update_type, transfer_id, data in updates:
            if transfer_id in self.transfers:
                transfer = self.transfers[transfer_id]
                if transfer.parent_transfer_id:
                    self._update_parent_folder_progress(transfer.parent_transfer_id)

    def _batch_update_database(self, updates: List[tuple]) -> None:
        """Met à jour la base par batch (1 transaction)"""
        with sqlite3.connect(self.db_path) as conn:
            for set_clauses, values in updates:
                sql = f"UPDATE transfers SET {', '.join(set_clauses)} WHERE transfer_id = ?"
                conn.execute(sql, values)
            conn.commit()

    def _update_parent_folder_progress(self, folder_transfer_id: str) -> None:
        """Met à jour le progrès d'un dossier basé sur ses fichiers individuels"""
        if folder_transfer_id not in self.transfers:
            return

        # Récupérer tous les fichiers de ce dossier depuis la DB
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

    def get_child_transfers(self, parent_transfer_id: str) -> Dict[str, TransferItem]:
        """Retourne tous les transferts enfants d'un transfert parent"""
        child_transfers = {}

        # D'abord chercher en cache
        for tid, transfer in self.transfers.items():
            if transfer.parent_transfer_id == parent_transfer_id:
                child_transfers[tid] = transfer

        # Compléter avec la DB si nécessaire
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT transfer_id, transfer_type, source_path, destination_path, file_name, 
                       file_size, parent_transfer_id, status, progress, speed, error_message
                FROM transfers 
                WHERE parent_transfer_id = ?
            """, (parent_transfer_id,))

            for row in cursor.fetchall():
                transfer_id = row[0]
                if transfer_id not in child_transfers:
                    # Créer TransferItem depuis DB
                    transfer = TransferItem(
                        transfer_id, TransferType(row[1]), row[2], row[3], row[4],
                        row[5], row[6]
                    )
                    transfer.status = TransferStatus(row[7])
                    transfer.progress = row[8]
                    transfer.speed = row[9]
                    transfer.error_message = row[10]
                    child_transfers[transfer_id] = transfer

        return child_transfers

    def get_individual_file_transfers(self) -> Dict[str, TransferItem]:
        """VERSION OPTIMISÉE - Charge depuis DB seulement si nécessaire"""

        # Si peu de transferts, utiliser le cache mémoire
        if len(self.transfers) < 1000:
            return {tid: t for tid, t in self.transfers.items() if t.is_individual_file()}

        # Pour gros volumes, requête optimisée depuis DB
        individual_files = {}

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT transfer_id, transfer_type, source_path, destination_path, file_name, 
                       file_size, parent_transfer_id, status, progress, speed, error_message
                FROM transfers 
                WHERE parent_transfer_id IS NOT NULL
                ORDER BY updated_at DESC
                LIMIT 2000
            """)

            for row in cursor.fetchall():
                transfer_id = row[0]
                # Créer TransferItem léger depuis DB
                transfer = TransferItem(
                    transfer_id, TransferType(row[1]), row[2], row[3], row[4],
                    row[5], row[6]
                )
                transfer.status = TransferStatus(row[7])
                transfer.progress = row[8]
                transfer.speed = row[9]
                transfer.error_message = row[10]

                individual_files[transfer_id] = transfer

        return individual_files

    def get_transfers_by_status_fast(self, status: TransferStatus, limit: int = 1000) -> List[str]:
        """Récupère rapidement les IDs par statut (pour l'affichage)"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT transfer_id FROM transfers 
                WHERE status = ? AND parent_transfer_id IS NOT NULL
                ORDER BY updated_at DESC 
                LIMIT ?
            """, (status.value, limit))

            return [row[0] for row in cursor.fetchall()]

    def _auto_cleanup_completed(self) -> None:
        """Nettoyage automatique intelligent"""
        total_transfers = self.fast_counts[TransferStatus.COMPLETED]

        # Si plus de 2000 fichiers terminés, nettoyer automatiquement
        if total_transfers > 2000:
            with sqlite3.connect(self.db_path) as conn:
                # Garder seulement les 500 plus récents
                cursor = conn.execute("""
                    DELETE FROM transfers 
                    WHERE status = 'COMPLETED' AND parent_transfer_id IS NOT NULL
                    AND transfer_id NOT IN (
                        SELECT transfer_id FROM transfers 
                        WHERE status = 'COMPLETED' AND parent_transfer_id IS NOT NULL
                        ORDER BY updated_at DESC 
                        LIMIT 500
                    )
                """)

                deleted = cursor.rowcount
                conn.commit()

                if deleted > 0:
                    self.fast_counts[TransferStatus.COMPLETED] = 500
                    self.stats_updated.emit(self.fast_counts.copy())
                    print(f"🧹 Auto-nettoyage: {deleted} transferts terminés supprimés")

    def get_fast_stats(self) -> Dict[TransferStatus, int]:
        """Retourne les statistiques rapidement (sans requête DB)"""
        return self.fast_counts.copy()

    def get_main_transfers(self) -> Dict[str, TransferItem]:
        """Retourne seulement les transferts principaux (pas les fichiers individuels)"""
        return {
            tid: transfer for tid, transfer in self.transfers.items()
            if transfer.parent_transfer_id is None
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
                        old_status = self.transfers[child_id].status
                        self.fast_counts[old_status] = max(0, self.fast_counts[old_status] - 1)
                        del self.transfers[child_id]
                        self.transfer_removed.emit(child_id)

                # Supprimer aussi de la DB
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute("DELETE FROM transfers WHERE parent_transfer_id = ?", (transfer_id,))
                    conn.commit()

            # Supprimer le transfert principal
            old_status = transfer.status
            self.fast_counts[old_status] = max(0, self.fast_counts[old_status] - 1)
            del self.transfers[transfer_id]

            # Supprimer de la DB
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("DELETE FROM transfers WHERE transfer_id = ?", (transfer_id,))
                conn.commit()

            self.transfer_removed.emit(transfer_id)
            self.stats_updated.emit(self.fast_counts.copy())

    def get_transfer(self, transfer_id: str) -> Optional[TransferItem]:
        """Récupère un transfert (cache d'abord, puis DB si nécessaire)"""
        # D'abord chercher en cache
        if transfer_id in self.transfers:
            return self.transfers[transfer_id]

        # Sinon chercher en DB et charger en cache
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT transfer_type, source_path, destination_path, file_name, 
                       file_size, parent_transfer_id, status, progress
                FROM transfers WHERE transfer_id = ?
            """, (transfer_id,))

            row = cursor.fetchone()
            if row:
                transfer = TransferItem(
                    transfer_id, TransferType(row[0]), row[1], row[2], row[3],
                    row[4], row[5]
                )
                transfer.status = TransferStatus(row[6])
                transfer.progress = row[7]

                # Mettre en cache pour prochaine fois
                self.transfers[transfer_id] = transfer
                return transfer

        return None

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
    """Modèle pour afficher la liste des transferts - GARDE POUR COMPATIBILITÉ"""

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
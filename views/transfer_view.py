"""
Vue pour afficher et gérer la liste des transferts
"""

import os
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTreeView,
                             QPushButton, QToolBar, QAction, QLabel,
                             QProgressBar, QSplitter, QGroupBox, QMenu,
                             QHeaderView, QAbstractItemView, QTabWidget,
                             QTableWidget, QTableWidgetItem, QCheckBox)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QSize
from PyQt5.QtGui import QFont, QStandardItemModel, QStandardItem

from models.transfer_models import TransferManager, TransferListModel, TransferStatus, TransferType, FileTransferItem


class TransferTreeView(QTreeView):
    """Vue personnalisée pour la liste des transferts avec support hiérarchique"""

    def __init__(self):
        """Initialise la vue"""
        super().__init__()
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setSortingEnabled(True)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.setExpandsOnDoubleClick(True)
        self.setItemsExpandable(True)
        self.setRootIsDecorated(True)

        # Ajuster les colonnes
        header = self.header()
        header.setStretchLastSection(True)


class ErrorFilesWidget(QWidget):
    """Widget pour afficher et gérer les fichiers en erreur"""
    
    retry_files_requested = pyqtSignal(str)  # transfer_id
    
    def __init__(self, transfer_manager: TransferManager):
        """
        Initialise le widget des fichiers en erreur
        
        Args:
            transfer_manager: Gestionnaire de transferts
        """
        super().__init__()
        self.transfer_manager = transfer_manager
        self.setup_ui()
        
        # Connecter aux signaux pour mettre à jour la liste
        self.transfer_manager.transfer_updated.connect(self.update_error_list)
        
        # Timer pour refresh périodique de la liste d'erreurs
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(lambda: self.update_error_list())
        self.refresh_timer.start(3000)  # Refresh toutes les 3 secondes
        
    def setup_ui(self) -> None:
        """Configure l'interface utilisateur"""
        layout = QVBoxLayout()
        
        # Titre
        title_layout = QHBoxLayout()
        title_label = QLabel("❌ Fichiers en erreur")
        title_font = QFont()
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_layout.addWidget(title_label)
        
        # Bouton pour réessayer tous les fichiers en erreur
        self.retry_all_button = QPushButton("🔄 Réessayer tout")
        self.retry_all_button.clicked.connect(self.retry_all_failed_files)
        self.retry_all_button.setEnabled(False)
        title_layout.addWidget(self.retry_all_button)
        
        title_layout.addStretch()
        layout.addLayout(title_layout)
        
        # Liste des fichiers en erreur
        self.error_tree = QTreeView()
        self.error_tree.setAlternatingRowColors(True)
        self.error_tree.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.error_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.error_tree.customContextMenuRequested.connect(self.show_error_context_menu)
        
        # Modèle pour les erreurs
        self.error_model = QStandardItemModel()
        self.error_model.setHorizontalHeaderLabels([
            "Fichier", "Dossier parent", "Erreur", "Tentatives", "Action"
        ])
        self.error_tree.setModel(self.error_model)
        
        layout.addWidget(self.error_tree)
        self.setLayout(layout)
        
    def update_error_list(self, transfer_id: str = None) -> None:
        """Met à jour la liste des fichiers en erreur"""
        # Effacer le modèle existant
        self.error_model.clear()
        self.error_model.setHorizontalHeaderLabels([
            "Fichier", "Dossier parent", "Erreur", "Tentatives", "Action"
        ])
        
        # Parcourir tous les transferts pour trouver les fichiers en erreur
        all_transfers = self.transfer_manager.get_all_transfers()
        has_errors = False
        
        for tid, transfer in all_transfers.items():
            if transfer.is_folder_transfer and transfer.child_files:
                failed_files = transfer.get_failed_files()
                for file_path, file_item in failed_files.items():
                    # Vérifier que le fichier est vraiment en erreur (pas en retry)
                    if file_item.status == TransferStatus.ERROR:
                        has_errors = True
                        
                        # Nom du fichier
                        name_item = QStandardItem(file_item.file_name)
                        name_item.setData(tid, Qt.UserRole)  # Stocker l'ID du transfert
                        name_item.setData(file_path, Qt.UserRole + 1)  # Stocker le chemin du fichier
                        
                        # Dossier parent
                        parent_item = QStandardItem(transfer.file_name)
                        
                        # Message d'erreur
                        error_text = file_item.error_message[:100] + "..." if len(file_item.error_message) > 100 else file_item.error_message
                        error_item = QStandardItem(error_text)
                        error_item.setToolTip(file_item.error_message)  # Message complet en tooltip
                        
                        # Nombre de tentatives
                        retry_item = QStandardItem(str(file_item.retry_count))
                        
                        # Action (bouton retry sera ajouté via delegate si nécessaire)
                        action_item = QStandardItem("Clic droit pour options")
                        
                        row = [name_item, parent_item, error_item, retry_item, action_item]
                        self.error_model.appendRow(row)
        
        # Activer/désactiver le bouton retry all
        self.retry_all_button.setEnabled(has_errors)
        
        # Mettre à jour le texte du bouton selon l'état
        if has_errors:
            error_count = self.error_model.rowCount()
            self.retry_all_button.setText(f"🔄 Réessayer tout ({error_count})")
        else:
            self.retry_all_button.setText("🔄 Réessayer tout")
        
        # Ajuster les colonnes
        self.error_tree.resizeColumnToContents(0)
        self.error_tree.resizeColumnToContents(1)
        self.error_tree.resizeColumnToContents(3)
    
    def show_error_context_menu(self, position) -> None:
        """Affiche le menu contextuel pour les fichiers en erreur"""
        index = self.error_tree.indexAt(position)
        if not index.isValid():
            return
            
        # Récupérer les informations du fichier
        name_item = self.error_model.item(index.row(), 0)
        if not name_item:
            return
            
        transfer_id = name_item.data(Qt.UserRole)
        file_path = name_item.data(Qt.UserRole + 1)
        
        menu = QMenu(self)
        
        # Action pour réessayer ce fichier spécifique
        retry_action = QAction("🔄 Réessayer ce fichier", self)
        retry_action.triggered.connect(lambda: self.retry_single_file(transfer_id, file_path))
        menu.addAction(retry_action)
        
        # Action pour ignorer ce fichier
        ignore_action = QAction("🚫 Ignorer ce fichier", self)
        ignore_action.triggered.connect(lambda: self.ignore_file(transfer_id, file_path))
        menu.addAction(ignore_action)
        
        menu.addSeparator()
        
        # Action pour voir les détails de l'erreur
        details_action = QAction("📄 Détails de l'erreur", self)
        details_action.triggered.connect(lambda: self.show_error_details(transfer_id, file_path))
        menu.addAction(details_action)
        
        menu.exec_(self.error_tree.viewport().mapToGlobal(position))
    
    def retry_single_file(self, transfer_id: str, file_path: str) -> None:
        """Réessaie un seul fichier"""
        transfer = self.transfer_manager.get_transfer(transfer_id)
        if transfer and file_path in transfer.child_files:
            file_item = transfer.child_files[file_path]
            file_item.status = TransferStatus.PENDING
            file_item.retry_count += 1
            file_item.error_message = ""
            file_item.start_time = None
            file_item.end_time = None
            
            # Remettre le transfert en cours
            transfer.status = TransferStatus.IN_PROGRESS
            
            # Émettre le signal pour déclencher le retry
            self.retry_files_requested.emit(transfer_id)
            
            self.transfer_manager.transfer_updated.emit(transfer_id)
    
    def ignore_file(self, transfer_id: str, file_path: str) -> None:
        """Ignore un fichier en erreur (le marque comme annulé)"""
        transfer = self.transfer_manager.get_transfer(transfer_id)
        if transfer and file_path in transfer.child_files:
            transfer.child_files[file_path].status = TransferStatus.CANCELLED
            self.transfer_manager.transfer_updated.emit(transfer_id)
    
    def show_error_details(self, transfer_id: str, file_path: str) -> None:
        """Affiche les détails d'une erreur"""
        transfer = self.transfer_manager.get_transfer(transfer_id)
        if transfer and file_path in transfer.child_files:
            file_item = transfer.child_files[file_path]
            
            from views.dialogs import ErrorDialog
            ErrorDialog.show_error(
                "Détails de l'erreur",
                f"Fichier: {file_item.file_name}\n"
                f"Chemin: {file_path}\n"
                f"Tentatives: {file_item.retry_count}\n"
                f"Erreur: {file_item.error_message}",
                self
            )
    
    def retry_all_failed_files(self) -> None:
        """Réessaie tous les fichiers en erreur"""
        all_transfers = self.transfer_manager.get_all_transfers()
        transfers_to_retry = []
        
        for transfer_id, transfer in all_transfers.items():
            if transfer.is_folder_transfer and transfer.get_failed_files():
                failed_files = self.transfer_manager.retry_failed_files(transfer_id)
                if failed_files:
                    transfers_to_retry.append(transfer_id)
        
        # Émettre les signaux pour tous les transferts à réessayer
        for transfer_id in transfers_to_retry:
            self.retry_files_requested.emit(transfer_id)


class AllFilesListWidget(QWidget):
    """Widget pour afficher tous les fichiers individuels en cours de transfert"""
    
    def __init__(self, transfer_manager: TransferManager):
        """
        Initialise le widget de liste exhaustive des fichiers
        
        Args:
            transfer_manager: Gestionnaire de transferts
        """
        super().__init__()
        self.transfer_manager = transfer_manager
        self.setup_ui()
        self.setup_timer()
        
        # Connecter aux signaux du gestionnaire de transferts
        transfer_manager.transfer_updated.connect(self.update_files_list)
        transfer_manager.transfer_added.connect(self.update_files_list)
        transfer_manager.transfer_removed.connect(self.update_files_list)
    
    def setup_ui(self) -> None:
        """Configure l'interface utilisateur"""
        layout = QVBoxLayout()
        
        # Titre et contrôles
        header_layout = QHBoxLayout()
        title_label = QLabel("📋 Liste exhaustive des fichiers")
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(11)
        title_label.setFont(title_font)
        header_layout.addWidget(title_label)
        
        header_layout.addStretch()
        
        # Filtres
        self.show_pending_checkbox = QCheckBox("⏳ En attente")
        self.show_pending_checkbox.setChecked(True)
        self.show_pending_checkbox.stateChanged.connect(self.update_files_list)
        header_layout.addWidget(self.show_pending_checkbox)
        
        self.show_in_progress_checkbox = QCheckBox("🔄 En cours")
        self.show_in_progress_checkbox.setChecked(True)
        self.show_in_progress_checkbox.stateChanged.connect(self.update_files_list)
        header_layout.addWidget(self.show_in_progress_checkbox)
        
        self.show_completed_checkbox = QCheckBox("✅ Terminés")
        self.show_completed_checkbox.setChecked(False)
        self.show_completed_checkbox.stateChanged.connect(self.update_files_list)
        header_layout.addWidget(self.show_completed_checkbox)
        
        self.show_error_checkbox = QCheckBox("❌ Erreurs")
        self.show_error_checkbox.setChecked(True)
        self.show_error_checkbox.stateChanged.connect(self.update_files_list)
        header_layout.addWidget(self.show_error_checkbox)
        
        layout.addLayout(header_layout)
        
        # Statistiques rapides
        self.stats_label = QLabel("Statistiques: ...")
        layout.addWidget(self.stats_label)
        
        # Table des fichiers
        self.files_table = QTableWidget()
        self.files_table.setColumnCount(7)
        self.files_table.setHorizontalHeaderLabels([
            "Statut", "Nom du fichier", "Dossier parent", "Progrès", 
            "Taille", "Vitesse", "ETA"
        ])
        
        # Configurer la table
        self.files_table.setAlternatingRowColors(True)
        self.files_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.files_table.setSortingEnabled(True)
        
        # Ajuster les colonnes
        header = self.files_table.horizontalHeader()
        header.setStretchLastSection(True)
        header.resizeSection(0, 80)  # Statut
        header.resizeSection(1, 200)  # Nom
        header.resizeSection(2, 150)  # Dossier parent
        header.resizeSection(3, 100)  # Progrès
        header.resizeSection(4, 80)   # Taille
        header.resizeSection(5, 80)   # Vitesse
        
        layout.addWidget(self.files_table)
        self.setLayout(layout)
    
    def setup_timer(self) -> None:
        """Configure le timer pour les mises à jour automatiques"""
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_files_list)
        self.update_timer.start(1000)  # Mise à jour toutes les secondes
    
    def get_status_icon(self, status: TransferStatus) -> str:
        """Retourne l'icône correspondant au statut"""
        status_icons = {
            TransferStatus.PENDING: "⏳",
            TransferStatus.IN_PROGRESS: "🔄",
            TransferStatus.COMPLETED: "✅",
            TransferStatus.ERROR: "❌",
            TransferStatus.CANCELLED: "🚫",
            TransferStatus.PAUSED: "⏸️"
        }
        return status_icons.get(status, "❓")
    
    def should_show_status(self, status: TransferStatus) -> bool:
        """Détermine si un fichier avec ce statut doit être affiché"""
        if status == TransferStatus.PENDING and not self.show_pending_checkbox.isChecked():
            return False
        if status == TransferStatus.IN_PROGRESS and not self.show_in_progress_checkbox.isChecked():
            return False
        if status == TransferStatus.COMPLETED and not self.show_completed_checkbox.isChecked():
            return False
        if status == TransferStatus.ERROR and not self.show_error_checkbox.isChecked():
            return False
        return True
    
    def format_size(self, size_bytes: int) -> str:
        """Formate la taille en bytes"""
        if size_bytes == 0:
            return "0 B"
        elif size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"
    
    def format_speed(self, speed: float) -> str:
        """Formate la vitesse"""
        if speed <= 0:
            return "-"
        elif speed < 1024:
            return f"{speed:.1f} B/s"
        elif speed < 1024 * 1024:
            return f"{speed / 1024:.1f} KB/s"
        elif speed < 1024 * 1024 * 1024:
            return f"{speed / (1024 * 1024):.1f} MB/s"
        else:
            return f"{speed / (1024 * 1024 * 1024):.1f} GB/s"
    
    def calculate_eta(self, file_item: FileTransferItem) -> str:
        """Calcule l'ETA pour un fichier"""
        if file_item.status != TransferStatus.IN_PROGRESS or file_item.speed <= 0:
            return "-"
        
        remaining_bytes = file_item.file_size - (file_item.file_size * file_item.progress / 100)
        if remaining_bytes <= 0:
            return "0s"
        
        eta_seconds = remaining_bytes / file_item.speed
        
        if eta_seconds < 60:
            return f"{int(eta_seconds)}s"
        elif eta_seconds < 3600:
            return f"{int(eta_seconds / 60)}m {int(eta_seconds % 60)}s"
        else:
            hours = int(eta_seconds / 3600)
            minutes = int((eta_seconds % 3600) / 60)
            return f"{hours}h {minutes}m"
    
    def update_files_list(self) -> None:
        """Met à jour la liste des fichiers"""
        try:
            # Collecter tous les fichiers de tous les transferts
            all_files = []
            stats = {"total": 0, "pending": 0, "in_progress": 0, "completed": 0, "error": 0}
            
            all_transfers = self.transfer_manager.get_all_transfers()
            
            for transfer_id, transfer in all_transfers.items():
                # Safeguard: vérifier que l'objet a les attributs requis
                if not hasattr(transfer, 'source_path'):
                    print(f"⚠️  TransferItem {transfer_id} manque l'attribut 'source_path', ignoré")
                    continue
                
                if transfer.is_folder_transfer and transfer.child_files:
                    # Fichiers individuels dans les dossiers
                    for file_path, file_item in transfer.child_files.items():
                        if self.should_show_status(file_item.status):
                            all_files.append({
                                'transfer_id': transfer_id,
                                'file_item': file_item,
                                'parent_folder': transfer.source_path
                            })
                        
                        # Statistiques
                        stats["total"] += 1
                        if file_item.status == TransferStatus.PENDING:
                            stats["pending"] += 1
                        elif file_item.status == TransferStatus.IN_PROGRESS:
                            stats["in_progress"] += 1
                        elif file_item.status == TransferStatus.COMPLETED:
                            stats["completed"] += 1
                        elif file_item.status == TransferStatus.ERROR:
                            stats["error"] += 1
                else:
                    # Fichiers simples
                    if self.should_show_status(transfer.status):
                        # Créer un FileTransferItem virtuel pour les fichiers simples
                        file_item = FileTransferItem(
                            transfer.source_path,
                            os.path.basename(transfer.source_path),
                            transfer.file_size
                        )
                        file_item.status = transfer.status
                        file_item.progress = transfer.progress
                        file_item.speed = transfer.speed
                        file_item.error_message = transfer.error_message
                        
                        all_files.append({
                            'transfer_id': transfer_id,
                            'file_item': file_item,
                            'parent_folder': os.path.dirname(transfer.source_path)
                        })
                    
                    # Statistiques
                    stats["total"] += 1
                    if transfer.status == TransferStatus.PENDING:
                        stats["pending"] += 1
                    elif transfer.status == TransferStatus.IN_PROGRESS:
                        stats["in_progress"] += 1
                    elif transfer.status == TransferStatus.COMPLETED:
                        stats["completed"] += 1
                    elif transfer.status == TransferStatus.ERROR:
                        stats["error"] += 1
            
            # Mettre à jour les statistiques
            self.stats_label.setText(
                f"📊 Total: {stats['total']} | "
                f"⏳ En attente: {stats['pending']} | "
                f"🔄 En cours: {stats['in_progress']} | "
                f"✅ Terminés: {stats['completed']} | "
                f"❌ Erreurs: {stats['error']}"
            )
            
            # Mettre à jour la table (optimisé pour éviter les flashs)
            current_row_count = self.files_table.rowCount()
            new_row_count = len(all_files)
            
            # Ajuster le nombre de lignes si nécessaire
            if current_row_count != new_row_count:
                self.files_table.setRowCount(new_row_count)
            
            # Remplir la table
            for row, file_data in enumerate(all_files):
                file_item = file_data['file_item']
                parent_folder = file_data['parent_folder']
                
                # Statut avec icône
                status_item = QTableWidgetItem(f"{self.get_status_icon(file_item.status)} {file_item.status.value}")
                self.files_table.setItem(row, 0, status_item)
                
                # Nom du fichier
                name_item = QTableWidgetItem(file_item.file_name)
                self.files_table.setItem(row, 1, name_item)
                
                # Dossier parent
                folder_item = QTableWidgetItem(os.path.basename(parent_folder) if parent_folder else "-")
                self.files_table.setItem(row, 2, folder_item)
                
                # Progrès
                if file_item.status == TransferStatus.IN_PROGRESS:
                    progress_text = f"{file_item.progress}%"
                elif file_item.status == TransferStatus.COMPLETED:
                    progress_text = "100%"
                else:
                    progress_text = "0%" if file_item.progress == 0 else f"{file_item.progress}%"
                progress_item = QTableWidgetItem(progress_text)
                self.files_table.setItem(row, 3, progress_item)
                
                # Taille
                size_item = QTableWidgetItem(self.format_size(file_item.file_size))
                self.files_table.setItem(row, 4, size_item)
                
                # Vitesse
                speed_item = QTableWidgetItem(self.format_speed(file_item.speed))
                self.files_table.setItem(row, 5, speed_item)
                
                # ETA
                eta_item = QTableWidgetItem(self.calculate_eta(file_item))
                self.files_table.setItem(row, 6, eta_item)
        
        except Exception as e:
            import traceback
            print(f"Erreur lors de la mise à jour de la liste des fichiers: {e}")
            print(f"Type d'erreur: {type(e).__name__}")
            print(f"Traceback complet:")
            traceback.print_exc()



class TransferStatsWidget(QWidget):
    """Widget d'affichage des statistiques de transfert"""

    def __init__(self, transfer_manager: TransferManager):
        """
        Initialise le widget de statistiques

        Args:
            transfer_manager: Gestionnaire de transferts
        """
        super().__init__()
        self.transfer_manager = transfer_manager
        self.last_update_time = 0  # Pour throttling des updates
        self.update_interval = 0.5  # Seconds entre updates (amélioré pour plus de réactivité)
        self.setup_ui()

        # MODIFICATION : Ne pas démarrer le timer immédiatement
        # Créer le timer mais ne pas le démarrer tout de suite
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_stats)

        # Démarrer le timer avec un délai pour laisser le temps à tout de s'initialiser
        QTimer.singleShot(1000, self.start_updates)  # Démarrer après 1 seconde

    def start_updates(self) -> None:
        """Démarre les mises à jour automatiques"""
        self.update_timer.start(1000)  # Mise à jour toutes les 1 secondes (améliorer la réactivité)
        self.update_stats()  # Première mise à jour immédiate

    def setup_ui(self) -> None:
        """Configure l'interface utilisateur"""
        layout = QHBoxLayout()

        # Stats générales
        self.total_label = QLabel("Total: 0")
        self.active_label = QLabel("Actifs: 0")
        self.completed_label = QLabel("Terminés: 0")
        self.errors_label = QLabel("Erreurs: 0")

        # Style des labels
        font = QFont()
        font.setBold(True)
        for label in [self.total_label, self.active_label, self.completed_label, self.errors_label]:
            label.setFont(font)

        # Barre de progression globale
        self.global_progress = QProgressBar()
        self.global_progress.setMaximumWidth(200)
        self.global_progress.setTextVisible(True)

        # Vitesse globale
        self.speed_label = QLabel("Vitesse: 0 B/s")

        layout.addWidget(self.total_label)
        layout.addWidget(self.active_label)
        layout.addWidget(self.completed_label)
        layout.addWidget(self.errors_label)
        layout.addStretch()
        layout.addWidget(QLabel("Progrès global:"))
        layout.addWidget(self.global_progress)
        layout.addWidget(self.speed_label)

        self.setLayout(layout)

    def update_stats(self) -> None:
        """Met à jour les statistiques affichées"""
        try:
            # Throttling: ne pas mettre à jour trop souvent
            import time
            current_time = time.time()
            if current_time - self.last_update_time < self.update_interval:
                return
            self.last_update_time = current_time
            
            # PROTECTION : Vérifier que le transfer_manager existe
            if not hasattr(self, 'transfer_manager') or self.transfer_manager is None:
                return

            all_transfers = self.transfer_manager.get_all_transfers()
            active_transfers = self.transfer_manager.get_active_transfers()
            completed_transfers = self.transfer_manager.get_completed_transfers()

            # Compter les erreurs
            error_count = sum(1 for t in all_transfers.values() if t.status == TransferStatus.ERROR)

            # Mettre à jour les labels
            self.total_label.setText(f"📊 Total: {len(all_transfers)}")
            self.active_label.setText(f"🔄 Actifs: {len(active_transfers)}")
            self.completed_label.setText(f"✅ Terminés: {len(completed_transfers) - error_count}")
            self.errors_label.setText(f"❌ Erreurs: {error_count}")

            # Calculer le progrès global et la vitesse
            if active_transfers:
                # Améliorer le calcul du progrès global
                total_progress = 0
                total_weight = 0
                total_speed = 0
                
                for transfer in active_transfers.values():
                    if transfer.status == TransferStatus.IN_PROGRESS:
                        # Pondérer par la taille du transfert
                        weight = max(transfer.file_size, 1)  # Éviter division par 0
                        total_progress += transfer.progress * weight
                        total_weight += weight
                        total_speed += transfer.speed

                if total_weight > 0:
                    global_progress = total_progress / total_weight
                    self.global_progress.setValue(int(global_progress))
                    self.speed_label.setText(f"⚡ Vitesse: {self.format_speed(total_speed)}")
                else:
                    self.global_progress.setValue(0)
                    self.speed_label.setText("⚡ Vitesse: 0 B/s")
            else:
                self.global_progress.setValue(0)
                self.speed_label.setText("⚡ Vitesse: 0 B/s")
        except Exception as e:
            # En cas d'erreur, ne pas crasher
            print(f"Erreur dans update_stats: {e}")

    def format_speed(self, speed: float) -> str:
        """Formate la vitesse en bytes/seconde"""
        if speed < 1024:
            return f"{speed:.1f} B/s"
        elif speed < 1024 * 1024:
            return f"{speed / 1024:.1f} KB/s"
        elif speed < 1024 * 1024 * 1024:
            return f"{speed / (1024 * 1024):.1f} MB/s"
        else:
            return f"{speed / (1024 * 1024 * 1024):.1f} GB/s"

class TransferPanel(QWidget):
    """Panneau principal de gestion des transferts avec support des fichiers individuels"""

    # Signaux pour la communication avec la fenêtre principale
    cancel_transfer_requested = pyqtSignal(str)  # transfer_id
    pause_transfer_requested = pyqtSignal(str)  # transfer_id
    resume_transfer_requested = pyqtSignal(str)  # transfer_id
    retry_files_requested = pyqtSignal(str)  # transfer_id

    def __init__(self, transfer_manager: TransferManager):
        """
        Initialise le panneau de transferts

        Args:
            transfer_manager: Gestionnaire de transferts
        """
        super().__init__()
        self.transfer_manager = transfer_manager

        self.setup_ui()
        self.connect_signals()

    def setup_ui(self) -> None:
        """Configure l'interface utilisateur avec onglets"""
        layout = QVBoxLayout()

        # Titre du panneau
        title_layout = QHBoxLayout()
        title_label = QLabel("📋 Gestionnaire de transferts")
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(12)
        title_label.setFont(title_font)
        title_layout.addWidget(title_label)
        title_layout.addStretch()

        # Bouton pour réduire/agrandir
        self.toggle_button = QPushButton("🔽")
        self.toggle_button.setFixedSize(25, 25)
        self.toggle_button.clicked.connect(self.toggle_panel)
        title_layout.addWidget(self.toggle_button)

        layout.addLayout(title_layout)

        # Contenu principal avec onglets
        self.main_content = QWidget()
        content_layout = QVBoxLayout(self.main_content)

        # Barre d'outils commune
        self.create_toolbar()
        content_layout.addWidget(self.toolbar)

        # Widget des statistiques globales (toujours visible)
        self.stats_widget = TransferStatsWidget(self.transfer_manager)
        content_layout.addWidget(self.stats_widget)

        # Créer les onglets
        self.tab_widget = QTabWidget()
        
        # Onglet 1: Vue traditionnelle avec transferts et erreurs
        traditional_tab = QWidget()
        traditional_layout = QVBoxLayout(traditional_tab)
        
        # Splitter pour diviser transferts et erreurs
        traditional_splitter = QSplitter(Qt.Vertical)
        
        # Vue des transferts hiérarchique
        transfers_widget = QWidget()
        transfers_layout = QVBoxLayout(transfers_widget)
        
        self.transfer_model = TransferListModel(self.transfer_manager)
        self.transfer_view = TransferTreeView()
        self.transfer_view.setModel(self.transfer_model)
        transfers_layout.addWidget(self.transfer_view)
        
        traditional_splitter.addWidget(transfers_widget)
        
        # Widget des fichiers en erreur
        self.error_widget = ErrorFilesWidget(self.transfer_manager)
        traditional_splitter.addWidget(self.error_widget)
        
        # Proportions du splitter
        traditional_splitter.setStretchFactor(0, 3)  # Transferts prennent 3/4
        traditional_splitter.setStretchFactor(1, 1)  # Erreurs prennent 1/4
        
        traditional_layout.addWidget(traditional_splitter)
        self.tab_widget.addTab(traditional_tab, "📁 Vue dossiers")
        
        # Onglet 2: Liste exhaustive des fichiers individuels
        self.all_files_widget = AllFilesListWidget(self.transfer_manager)
        self.tab_widget.addTab(self.all_files_widget, "📋 Tous les fichiers")
        
        content_layout.addWidget(self.tab_widget)

        layout.addWidget(self.main_content)
        self.setLayout(layout)

        # État initial
        self.is_collapsed = False

    def create_toolbar(self) -> None:
        """Crée la barre d'outils du panneau"""
        self.toolbar = QToolBar()
        self.toolbar.setIconSize(QSize(16, 16))

        # Actions de contrôle
        self.cancel_action = QAction("🚫 Annuler", self)
        self.cancel_action.setToolTip("Annuler le transfert sélectionné")
        self.cancel_action.triggered.connect(self.cancel_selected_transfer)
        self.toolbar.addAction(self.cancel_action)

        self.toolbar.addSeparator()

        # Actions de nettoyage
        self.clear_completed_action = QAction("🧹 Vider terminés", self)
        self.clear_completed_action.setToolTip("Supprimer tous les transferts terminés")
        self.clear_completed_action.triggered.connect(self.clear_completed_transfers)
        self.toolbar.addAction(self.clear_completed_action)

        self.clear_all_action = QAction("🗑️ Tout vider", self)
        self.clear_all_action.setToolTip("Supprimer tous les transferts")
        self.clear_all_action.triggered.connect(self.clear_all_transfers)
        self.toolbar.addAction(self.clear_all_action)

        # Actions de filtrage
        self.toolbar.addSeparator()
        self.show_active_action = QAction("🔄 Actifs seulement", self)
        self.show_active_action.setCheckable(True)
        self.show_active_action.setToolTip("Afficher seulement les transferts actifs")
        self.show_active_action.triggered.connect(self.toggle_filter_active)
        self.toolbar.addAction(self.show_active_action)

    def connect_signals(self) -> None:
        """Connecte les signaux"""
        # Menu contextuel
        self.transfer_view.customContextMenuRequested.connect(self.show_context_menu)

        # Sélection
        self.transfer_view.selectionModel().selectionChanged.connect(self.update_toolbar_state)
        
        # Signaux du widget d'erreurs
        self.error_widget.retry_files_requested.connect(self.retry_files_requested.emit)

    def show_context_menu(self, position) -> None:
        """Affiche le menu contextuel"""
        if not self.transfer_view.indexAt(position).isValid():
            return

        menu = QMenu(self)

        # Actions selon le statut du transfert sélectionné
        selected_row = self.transfer_view.currentIndex().row()
        if selected_row >= 0:
            transfer_id = self.transfer_model.get_transfer_id_from_row(selected_row)
            if transfer_id:
                transfer = self.transfer_manager.get_transfer(transfer_id)
                if transfer:
                    #if transfer.status == TransferStatus.IN_PROGRESS:
                    #    menu.addAction("⏸️ Suspendre", lambda: self.pause_transfer(transfer_id))
                    #elif transfer.status == TransferStatus.PAUSED:
                    #    menu.addAction("▶️ Reprendre", lambda: self.resume_transfer(transfer_id))

                    if transfer.status in [TransferStatus.PENDING, TransferStatus.IN_PROGRESS, TransferStatus.PAUSED]:
                        menu.addAction("🚫 Annuler", lambda: self.cancel_transfer(transfer_id))

                    menu.addSeparator()
                    menu.addAction("🗑️ Supprimer de la liste", lambda: self.remove_transfer(transfer_id))

                    if transfer.status == TransferStatus.ERROR:
                        menu.addAction("🔄 Réessayer", lambda: self.retry_transfer(transfer_id))

        if menu.actions():
            menu.exec_(self.transfer_view.viewport().mapToGlobal(position))

    def toggle_panel(self) -> None:
        """Bascule l'affichage du panneau (réduit/étendu)"""
        self.is_collapsed = not self.is_collapsed
        self.main_content.setVisible(not self.is_collapsed)
        self.toggle_button.setText("🔼" if self.is_collapsed else "🔽")

    def pause_selected_transfer(self) -> None:
        """Suspend le transfert sélectionné"""
        selected_row = self.transfer_view.currentIndex().row()
        if selected_row >= 0:
            transfer_id = self.transfer_model.get_transfer_id_from_row(selected_row)
            if transfer_id:
                self.pause_transfer(transfer_id)

    def resume_selected_transfer(self) -> None:
        """Reprend le transfert sélectionné"""
        selected_row = self.transfer_view.currentIndex().row()
        if selected_row >= 0:
            transfer_id = self.transfer_model.get_transfer_id_from_row(selected_row)
            if transfer_id:
                self.resume_transfer(transfer_id)

    def cancel_selected_transfer(self) -> None:
        """Annule le transfert sélectionné"""
        selected_row = self.transfer_view.currentIndex().row()
        if selected_row >= 0:
            transfer_id = self.transfer_model.get_transfer_id_from_row(selected_row)
            if transfer_id:
                self.cancel_transfer(transfer_id)

    def pause_transfer(self, transfer_id: str) -> None:
        """Suspend un transfert"""
        self.pause_transfer_requested.emit(transfer_id)
        self.transfer_manager.pause_transfer(transfer_id)

    def resume_transfer(self, transfer_id: str) -> None:
        """Reprend un transfert"""
        self.resume_transfer_requested.emit(transfer_id)
        self.transfer_manager.resume_transfer(transfer_id)

    def cancel_transfer(self, transfer_id: str) -> None:
        """Annule un transfert"""
        self.cancel_transfer_requested.emit(transfer_id)
        self.transfer_manager.cancel_transfer(transfer_id)

    def remove_transfer(self, transfer_id: str) -> None:
        """Supprime un transfert de la liste"""
        self.transfer_manager.remove_transfer(transfer_id)

    def retry_transfer(self, transfer_id: str) -> None:
        """Réessaie un transfert (pour une implémentation future)"""
        # Pour l'instant, on remet juste en attente
        self.transfer_manager.update_transfer_status(transfer_id, TransferStatus.PENDING)

    def clear_completed_transfers(self) -> None:
        """Supprime tous les transferts terminés"""
        self.transfer_manager.clear_completed_transfers()

    def clear_all_transfers(self) -> None:
        """Supprime tous les transferts"""
        # Demander confirmation via un signal si nécessaire
        from views.dialogs import ConfirmationDialog
        if ConfirmationDialog.ask_confirmation(
                "🗑️ Vider la liste",
                "Voulez-vous vraiment supprimer tous les transferts de la liste?",
                self
        ):
            transfer_ids = list(self.transfer_manager.get_all_transfers().keys())
            for transfer_id in transfer_ids:
                self.transfer_manager.remove_transfer(transfer_id)

    def toggle_filter_active(self, checked: bool) -> None:
        """Bascule le filtre pour afficher seulement les transferts actifs"""
        # Cette fonctionnalité peut être implémentée avec un proxy model
        # Pour l'instant, on laisse tel quel
        pass

    def update_toolbar_state(self) -> None:
        """Met à jour l'état des actions de la barre d'outils"""
        selected_row = self.transfer_view.currentIndex().row()
        has_selection = selected_row >= 0

        if has_selection:
            transfer_id = self.transfer_model.get_transfer_id_from_row(selected_row)
            if transfer_id:
                transfer = self.transfer_manager.get_transfer(transfer_id)
                if transfer:
                    # Activer/désactiver selon le statut
                    #self.pause_action.setEnabled(transfer.status == TransferStatus.IN_PROGRESS)
                    #self.resume_action.setEnabled(transfer.status == TransferStatus.PAUSED)
                    self.cancel_action.setEnabled(transfer.status in [
                        TransferStatus.PENDING, TransferStatus.IN_PROGRESS, TransferStatus.PAUSED
                    ])
                    return

        # Pas de sélection ou transfert invalide
        #self.pause_action.setEnabled(False)
        #self.resume_action.setEnabled(False)
        self.cancel_action.setEnabled(False)

    def get_transfer_count(self) -> int:
        """Retourne le nombre de transferts"""
        return len(self.transfer_manager.get_all_transfers())

    def get_active_transfer_count(self) -> int:
        """Retourne le nombre de transferts actifs"""
        return len(self.transfer_manager.get_active_transfers())
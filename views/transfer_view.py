"""
Vue pour afficher et gérer la liste des transferts - VERSION CORRIGÉE STABLE
"""

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTreeView,
                             QPushButton, QToolBar, QAction, QLabel,
                             QProgressBar, QSplitter, QGroupBox, QMenu,
                             QHeaderView, QAbstractItemView, QTabWidget,
                             QTableView)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QSize, QSortFilterProxyModel, QModelIndex, QAbstractTableModel
from PyQt5.QtGui import QFont, QStandardItem

from models.transfer_models import TransferManager, TransferListModel, TransferStatus, TransferType


class TransferTreeView(QTreeView):
    """Vue personnalisée pour la liste des transferts"""

    def __init__(self):
        """Initialise la vue"""
        super().__init__()
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setSortingEnabled(True)
        self.setContextMenuPolicy(Qt.CustomContextMenu)

        # Ajuster les colonnes
        header = self.header()
        header.setStretchLastSection(True)


class SimplifiedTransferModel(QAbstractTableModel):
    """Modèle SIMPLIFIÉ et STABLE pour éviter les crashes"""

    def __init__(self, transfer_manager: TransferManager, status_filter: TransferStatus = None):
        super().__init__()
        self.transfer_manager = transfer_manager
        self.status_filter = status_filter

        # Cache simple pour l'affichage
        self.display_data = []  # Liste des transfer_ids visibles
        self.data_cache = {}    # Cache des données pour les lignes visibles

        # Headers
        self.headers = ["Fichier", "Type", "Statut", "Progrès", "Vitesse", "ETA", "Taille", "Destination"]

        # Timer pour les mises à jour BEAUCOUP MOINS fréquentes
        self.update_timer = QTimer()
        self.update_timer.setSingleShot(True)
        self.update_timer.timeout.connect(self._safe_refresh)

        # Connecter aux signaux de base seulement
        self.transfer_manager.transfer_added.connect(self.queue_refresh)
        self.transfer_manager.transfer_removed.connect(self.queue_refresh)

        # Éviter les signaux batch qui peuvent causer des problèmes
        if hasattr(transfer_manager, 'transfer_status_changed'):
            transfer_manager.transfer_status_changed.connect(self.queue_refresh)

        # Charger données initiales de façon sécurisée
        QTimer.singleShot(500, self.refresh_data)

    def rowCount(self, parent=QModelIndex()) -> int:
        """Retourne le nombre total"""
        return len(self.display_data)

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(self.headers)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.headers[section]
        return None

    def data(self, index: QModelIndex, role: int):
        if not index.isValid() or role != Qt.DisplayRole:
            return None

        row = index.row()
        col = index.column()

        if row >= len(self.display_data):
            return None

        transfer_id = self.display_data[row]

        # Chargement paresseux SÉCURISÉ des données
        transfer_data = self._safe_get_transfer_data(transfer_id)
        if not transfer_data:
            return "..."

        # Mapper les colonnes
        if col == 0:    # Fichier
            name = transfer_data.get('file_name', '')
            if transfer_data.get('is_individual_file', False):
                return f"  └─ {name}"
            return name
        elif col == 1:  # Type
            return transfer_data.get('type', '')
        elif col == 2:  # Statut
            return transfer_data.get('status', '')
        elif col == 3:  # Progrès
            progress = transfer_data.get('progress', 0)
            return f"{progress}%"
        elif col == 4:  # Vitesse
            return transfer_data.get('speed_text', '0 B/s')
        elif col == 5:  # ETA
            return transfer_data.get('eta_text', '∞')
        elif col == 6:  # Taille
            return transfer_data.get('size_text', '')
        elif col == 7:  # Destination
            return transfer_data.get('destination', '')

        return None

    def _safe_get_transfer_data(self, transfer_id: str) -> dict:
        """Récupère les données d'un transfert de façon sécurisée"""
        try:
            # Vérifier le cache d'abord
            if transfer_id in self.data_cache:
                return self.data_cache[transfer_id]

            # Sinon charger depuis le transfer_manager
            transfer = self.transfer_manager.get_transfer(transfer_id)
            if not transfer:
                return {}

            # Créer entrée cache avec données formatées
            transfer_data = {
                'file_name': transfer.file_name,
                'type': transfer.transfer_type.value,
                'status': transfer.status.value,
                'progress': transfer.progress,
                'speed_text': self._safe_get_speed_text(transfer),
                'eta_text': self._safe_get_eta_text(transfer),
                'size_text': self._format_size(transfer.file_size),
                'destination': transfer.destination_path,
                'is_individual_file': transfer.is_individual_file()
            }

            self.data_cache[transfer_id] = transfer_data
            return transfer_data

        except Exception as e:
            print(f"❌ Erreur _safe_get_transfer_data: {e}")
            return {}

    def _safe_get_speed_text(self, transfer) -> str:
        """Obtient le texte de vitesse de façon sécurisée"""
        try:
            if hasattr(transfer, 'get_speed_text'):
                return transfer.get_speed_text()
            elif hasattr(transfer, 'speed'):
                return f"{self._format_size(int(transfer.speed))}/s" if transfer.speed > 0 else "0 B/s"
            else:
                return "0 B/s"
        except:
            return "0 B/s"

    def _safe_get_eta_text(self, transfer) -> str:
        """Obtient le texte ETA de façon sécurisée"""
        try:
            if hasattr(transfer, 'get_eta_text'):
                return transfer.get_eta_text()
            else:
                return "∞"
        except:
            return "∞"

    def _format_size(self, size_bytes: int) -> str:
        """Formate la taille rapidement et de façon sécurisée"""
        try:
            if size_bytes == 0:
                return ""

            for unit in ['B', 'KB', 'MB', 'GB']:
                if size_bytes < 1024:
                    return f"{size_bytes:.1f} {unit}"
                size_bytes /= 1024
            return f"{size_bytes:.1f} TB"
        except:
            return ""

    def refresh_data(self) -> None:
        """Rafraîchit les données de façon SÉCURISÉE"""
        try:
            self.beginResetModel()

            # Vider les caches
            old_data = self.display_data.copy()
            self.display_data.clear()
            self.data_cache.clear()

            if self.status_filter:
                # Récupérer les transferts d'un statut spécifique
                try:
                    if hasattr(self.transfer_manager, 'get_transfers_by_status_fast'):
                        transfer_ids = self.transfer_manager.get_transfers_by_status_fast(
                            self.status_filter, limit=500  # Limiter pour éviter le lag
                        )
                        self.display_data.extend(transfer_ids)
                    else:
                        # Fallback : méthode classique et sécurisée
                        individual_files = self.transfer_manager.get_individual_file_transfers()
                        filtered_ids = [tid for tid, t in individual_files.items()
                                      if t.status == self.status_filter]
                        self.display_data.extend(filtered_ids[:500])  # Limiter à 500
                except Exception as e:
                    print(f"❌ Erreur filtrage par statut: {e}")
                    # Utiliser les anciennes données en cas d'erreur
                    self.display_data = old_data
            else:
                # Tous les fichiers individuels (avec limite)
                try:
                    individual_files = self.transfer_manager.get_individual_file_transfers()
                    self.display_data.extend(list(individual_files.keys())[:500])
                except Exception as e:
                    print(f"❌ Erreur récupération transferts: {e}")
                    # Utiliser les anciennes données en cas d'erreur
                    self.display_data = old_data

            self.endResetModel()
            print(f"✅ Refresh modèle: {len(self.display_data)} transferts affichés")

        except Exception as e:
            print(f"❌ Erreur critique refresh_data: {e}")
            self.endResetModel()

    def queue_refresh(self) -> None:
        """Queue un refresh pour éviter le spam - VERSION SÉCURISÉE"""
        try:
            if not self.update_timer.isActive():
                self.update_timer.start(1000)  # Attendre 1 seconde au lieu de 300ms
        except Exception as e:
            print(f"❌ Erreur queue_refresh: {e}")

    def _safe_refresh(self) -> None:
        """Refresh différé et sécurisé"""
        try:
            self.refresh_data()
        except Exception as e:
            print(f"❌ Erreur _safe_refresh: {e}")

    def get_transfer_id_from_row(self, row: int) -> str:
        """Récupère l'ID du transfert à partir d'une ligne"""
        try:
            if 0 <= row < len(self.display_data):
                return self.display_data[row]
        except Exception as e:
            print(f"❌ Erreur get_transfer_id_from_row: {e}")
        return None


class TransferStatsWidget(QWidget):
    """Widget d'affichage des statistiques - VERSION SIMPLIFIÉE"""

    def __init__(self, transfer_manager: TransferManager):
        super().__init__()
        self.transfer_manager = transfer_manager
        self.setup_ui()

        # Timer moins fréquent et plus sécurisé
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.safe_update_stats)
        self.update_timer.start(3000)  # 3 secondes au lieu de 2

        # Utiliser signaux optimisés si disponibles, sinon timer classique
        if hasattr(transfer_manager, 'stats_updated'):
            transfer_manager.stats_updated.connect(self.update_stats_fast)

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

    def update_stats_fast(self, stats: dict) -> None:
        """Mise à jour rapide avec les compteurs pré-calculés - VERSION SÉCURISÉE"""
        try:
            total = sum(stats.values())
            active = stats.get(TransferStatus.IN_PROGRESS, 0) + stats.get(TransferStatus.PENDING, 0)
            completed = stats.get(TransferStatus.COMPLETED, 0)
            errors = stats.get(TransferStatus.ERROR, 0)

            self.total_label.setText(f"📊 Total: {total}")
            self.active_label.setText(f"🔄 Actifs: {active}")
            self.completed_label.setText(f"✅ Terminés: {completed}")
            self.errors_label.setText(f"❌ Erreurs: {errors}")

            # Calculer progrès global (approximatif pour les performances)
            if active > 0:
                # Estimation basée sur les ratios
                estimated_progress = (completed / max(total, 1)) * 100
                self.global_progress.setValue(int(estimated_progress))

                # Vitesse globale approximative (limitée pour éviter les erreurs)
                try:
                    active_transfers = self.transfer_manager.get_active_transfers()
                    if active_transfers:
                        # Échantillonner seulement quelques transferts pour éviter la surcharge
                        sample = list(active_transfers.values())[:20]
                        total_speed = sum(getattr(t, 'speed', 0) for t in sample)
                        self.speed_label.setText(f"⚡ Vitesse: {self.format_speed(total_speed)}")
                    else:
                        self.speed_label.setText("⚡ Vitesse: 0 B/s")
                except Exception as e:
                    print(f"❌ Erreur calcul vitesse: {e}")
                    self.speed_label.setText("⚡ Vitesse: N/A")
            else:
                self.global_progress.setValue(100 if completed > 0 else 0)
                self.speed_label.setText("⚡ Vitesse: 0 B/s")

        except Exception as e:
            print(f"❌ Erreur update_stats_fast: {e}")

    def safe_update_stats(self) -> None:
        """Mise à jour sécurisée (fallback)"""
        try:
            if hasattr(self.transfer_manager, 'get_fast_stats'):
                stats = self.transfer_manager.get_fast_stats()
                self.update_stats_fast(stats)
            else:
                # Fallback vers calcul manuel (moins optimal mais sûr)
                all_transfers = self.transfer_manager.get_all_transfers()
                individual_files = {tid: t for tid, t in all_transfers.items() if t.is_individual_file()}

                counts = {
                    TransferStatus.PENDING: 0,
                    TransferStatus.IN_PROGRESS: 0,
                    TransferStatus.COMPLETED: 0,
                    TransferStatus.ERROR: 0
                }

                for transfer in individual_files.values():
                    if transfer.status in counts:
                        counts[transfer.status] += 1

                self.update_stats_fast(counts)

        except Exception as e:
            print(f"❌ Erreur safe_update_stats: {e}")

    def format_speed(self, speed: float) -> str:
        """Formate la vitesse de façon sécurisée"""
        try:
            if speed < 1024:
                return f"{speed:.1f} B/s"
            elif speed < 1024 * 1024:
                return f"{speed / 1024:.1f} KB/s"
            elif speed < 1024 * 1024 * 1024:
                return f"{speed / (1024 * 1024):.1f} MB/s"
            else:
                return f"{speed / (1024 * 1024 * 1024):.1f} GB/s"
        except:
            return "0 B/s"


class TransferPanel(QWidget):
    """Panneau principal de gestion des transferts - VERSION SIMPLIFIÉE"""

    # Signaux pour la communication avec la fenêtre principale
    cancel_transfer_requested = pyqtSignal(str)  # transfer_id
    pause_transfer_requested = pyqtSignal(str)  # transfer_id
    resume_transfer_requested = pyqtSignal(str)  # transfer_id

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
        """Configure l'interface utilisateur - VERSION SIMPLIFIÉE"""
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

        # Contenu principal (peut être masqué)
        self.main_content = QWidget()
        content_layout = QVBoxLayout(self.main_content)

        # Barre d'outils
        self.create_toolbar()
        content_layout.addWidget(self.toolbar)

        # Créer le widget d'onglets - VERSION SIMPLIFIÉE
        self.tab_widget = QTabWidget()

        # Onglet 1: Vue complète des transferts (transferts principaux)
        self.list_tab = QWidget()
        list_layout = QVBoxLayout(self.list_tab)

        # Vue des transferts principaux seulement
        self.transfer_model = TransferListModel(self.transfer_manager, show_individual_files=False)
        self.transfer_view = TransferTreeView()
        self.transfer_view.setModel(self.transfer_model)
        list_layout.addWidget(self.transfer_view)

        # Ajouter l'onglet de liste
        self.tab_widget.addTab(self.list_tab, "📋 Liste complète")

        # Onglet 2: Vue simplifiée de la queue
        self.queue_panel = TransferQueuePanel(self.transfer_manager)
        self.tab_widget.addTab(self.queue_panel, "🔄 Queue de transferts")

        # Ajouter le widget d'onglets au contenu principal
        content_layout.addWidget(self.tab_widget)

        # Widget des statistiques
        self.stats_widget = TransferStatsWidget(self.transfer_manager)
        content_layout.addWidget(self.stats_widget)

        layout.addWidget(self.main_content)
        self.setLayout(layout)

        # État initial
        self.is_collapsed = False

        # Initialiser les largeurs de colonnes
        QTimer.singleShot(500, self.initialize_column_widths)

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

    def connect_signals(self) -> None:
        """Connecte les signaux"""
        # Menu contextuel
        self.transfer_view.customContextMenuRequested.connect(self.show_context_menu)

        # Sélection
        self.transfer_view.selectionModel().selectionChanged.connect(self.update_toolbar_state)

    def show_context_menu(self, position) -> None:
        """Affiche le menu contextuel"""
        try:
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
                        if transfer.status in [TransferStatus.PENDING, TransferStatus.IN_PROGRESS, TransferStatus.PAUSED]:
                            menu.addAction("🚫 Annuler", lambda: self.cancel_transfer(transfer_id))

                        menu.addSeparator()
                        menu.addAction("🗑️ Supprimer de la liste", lambda: self.remove_transfer(transfer_id))

                        if transfer.status == TransferStatus.ERROR:
                            menu.addAction("🔄 Réessayer", lambda: self.retry_transfer(transfer_id))

            if menu.actions():
                menu.exec_(self.transfer_view.viewport().mapToGlobal(position))
        except Exception as e:
            print(f"❌ Erreur menu contextuel: {e}")

    def toggle_panel(self) -> None:
        """Bascule l'affichage du panneau (réduit/étendu)"""
        self.is_collapsed = not self.is_collapsed
        self.main_content.setVisible(not self.is_collapsed)
        self.toggle_button.setText("🔼" if self.is_collapsed else "🔽")

    def cancel_selected_transfer(self) -> None:
        """Annule le transfert sélectionné"""
        try:
            selected_row = self.transfer_view.currentIndex().row()
            if selected_row >= 0:
                transfer_id = self.transfer_model.get_transfer_id_from_row(selected_row)
                if transfer_id:
                    self.cancel_transfer(transfer_id)
        except Exception as e:
            print(f"❌ Erreur cancel_selected_transfer: {e}")

    def cancel_transfer(self, transfer_id: str) -> None:
        """Annule un transfert"""
        try:
            self.cancel_transfer_requested.emit(transfer_id)
            self.transfer_manager.cancel_transfer(transfer_id)
        except Exception as e:
            print(f"❌ Erreur cancel_transfer: {e}")

    def remove_transfer(self, transfer_id: str) -> None:
        """Supprime un transfert de la liste"""
        try:
            self.transfer_manager.remove_transfer(transfer_id)
        except Exception as e:
            print(f"❌ Erreur remove_transfer: {e}")

    def retry_transfer(self, transfer_id: str) -> None:
        """Réessaie un transfert"""
        try:
            self.transfer_manager.update_transfer_status(transfer_id, TransferStatus.PENDING)
        except Exception as e:
            print(f"❌ Erreur retry_transfer: {e}")

    def clear_completed_transfers(self) -> None:
        """Supprime tous les transferts terminés"""
        try:
            self.transfer_manager.clear_completed_transfers()
        except Exception as e:
            print(f"❌ Erreur clear_completed_transfers: {e}")

    def clear_all_transfers(self) -> None:
        """Supprime tous les transferts"""
        try:
            from views.dialogs import ConfirmationDialog
            if ConfirmationDialog.ask_confirmation(
                    "🗑️ Vider la liste",
                    "Voulez-vous vraiment supprimer tous les transferts de la liste?",
                    self
            ):
                transfer_ids = list(self.transfer_manager.get_all_transfers().keys())
                for transfer_id in transfer_ids:
                    self.transfer_manager.remove_transfer(transfer_id)
        except Exception as e:
            print(f"❌ Erreur clear_all_transfers: {e}")

    def update_toolbar_state(self) -> None:
        """Met à jour l'état des actions de la barre d'outils"""
        try:
            selected_row = self.transfer_view.currentIndex().row()
            has_selection = selected_row >= 0

            if has_selection:
                transfer_id = self.transfer_model.get_transfer_id_from_row(selected_row)
                if transfer_id:
                    transfer = self.transfer_manager.get_transfer(transfer_id)
                    if transfer:
                        self.cancel_action.setEnabled(transfer.status in [
                            TransferStatus.PENDING, TransferStatus.IN_PROGRESS, TransferStatus.PAUSED
                        ])
                        return

            self.cancel_action.setEnabled(False)
        except Exception as e:
            print(f"❌ Erreur update_toolbar_state: {e}")

    def get_transfer_count(self) -> int:
        """Retourne le nombre de transferts"""
        try:
            return len(self.transfer_manager.get_all_transfers())
        except:
            return 0

    def get_active_transfer_count(self) -> int:
        """Retourne le nombre de transferts actifs"""
        try:
            return len(self.transfer_manager.get_active_transfers())
        except:
            return 0

    def initialize_column_widths(self) -> None:
        """Initialise la largeur des colonnes pour la vue principale"""
        try:
            header = self.transfer_view.header()
            if header:
                header.setSectionResizeMode(0, QHeaderView.Stretch)  # Nom du fichier
                header.setSectionResizeMode(1, QHeaderView.ResizeToContents)  # Type
                header.setSectionResizeMode(2, QHeaderView.ResizeToContents)  # Statut
                header.setSectionResizeMode(3, QHeaderView.ResizeToContents)  # Progrès
                header.setSectionResizeMode(4, QHeaderView.ResizeToContents)  # Vitesse
                header.setSectionResizeMode(5, QHeaderView.ResizeToContents)  # ETA
                header.setSectionResizeMode(6, QHeaderView.ResizeToContents)  # Taille

            # Initialiser aussi les largeurs de colonnes dans le panneau de queue
            if hasattr(self, 'queue_panel'):
                self.queue_panel.update_column_widths()
        except Exception as e:
            print(f"❌ Erreur initialize_column_widths: {e}")


class TransferQueuePanel(QWidget):
    """Panneau de queue SIMPLIFIÉ et STABLE"""

    def __init__(self, transfer_manager: TransferManager):
        super().__init__()
        self.transfer_manager = transfer_manager
        self.setup_ui()
        self.connect_signals()

        # Timer optimisé pour rafraîchissement MOINS fréquent
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self.refresh_current_model)
        self.refresh_timer.start(2000)  # 2 secondes au lieu de 1

    def setup_ui(self) -> None:
        """Configure l'interface avec modèles simplifiés"""
        layout = QVBoxLayout(self)

        title_label = QLabel("📋 Queue de transferts (Fichiers individuels)")
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(12)
        title_label.setFont(title_font)
        layout.addWidget(title_label)

        # Créer les modèles simplifiés pour chaque statut
        self.status_tabs = QTabWidget()
        self.models = {}
        self.views = {}

        # Créer un modèle par statut pour optimiser
        statuses = [
            (TransferStatus.IN_PROGRESS, "🔄 En cours"),
            (TransferStatus.PENDING, "⏳ En attente"),
            (TransferStatus.ERROR, "❌ Erreurs"),
            (TransferStatus.COMPLETED, "✅ Terminés"),
            (TransferStatus.CANCELLED, "🚫 Annulés"),
            (TransferStatus.PAUSED, "⏸️ Suspendus")
        ]

        for i, (status, tab_name) in enumerate(statuses):
            # Créer modèle simplifié et sécurisé pour ce statut
            model = SimplifiedTransferModel(self.transfer_manager, status)
            self.models[status] = model

            # Créer vue simplifiée
            view = QTableView()  # Plus rapide que TreeView pour de gros volumes
            view.setModel(model)
            view.setAlternatingRowColors(True)
            view.setSelectionBehavior(QAbstractItemView.SelectRows)
            view.setSelectionMode(QAbstractItemView.ExtendedSelection)
            view.setSortingEnabled(False)  # Désactiver le tri pour éviter les problèmes
            self.views[status] = view

            # Créer onglet
            tab_widget = QWidget()
            tab_layout = QVBoxLayout(tab_widget)
            tab_layout.addWidget(view)

            self.status_tabs.addTab(tab_widget, f"{tab_name} (0)")

        layout.addWidget(self.status_tabs)

    def connect_signals(self) -> None:
        """Connecte aux signaux simplifiés"""
        try:
            if hasattr(self.transfer_manager, 'stats_updated'):
                self.transfer_manager.stats_updated.connect(self.update_tab_titles_fast)
        except Exception as e:
            print(f"❌ Erreur connect_signals: {e}")

    def refresh_current_model(self) -> None:
        """Rafraîchit seulement le modèle de l'onglet visible (optimisation)"""
        try:
            # Refresh seulement l'onglet visible pour économiser les ressources
            current_index = self.status_tabs.currentIndex()
            if current_index >= 0:
                statuses = list(self.models.keys())
                if current_index < len(statuses):
                    current_status = statuses[current_index]
                    if current_status in self.models:
                        self.models[current_status].queue_refresh()
        except Exception as e:
            print(f"❌ Erreur refresh_current_model: {e}")

    def update_tab_titles_fast(self, stats: dict) -> None:
        """Met à jour les titres avec les stats pré-calculées"""
        try:
            titles = [
                (TransferStatus.IN_PROGRESS, "🔄 En cours"),
                (TransferStatus.PENDING, "⏳ En attente"),
                (TransferStatus.ERROR, "❌ Erreurs"),
                (TransferStatus.COMPLETED, "✅ Terminés"),
                (TransferStatus.CANCELLED, "🚫 Annulés"),
                (TransferStatus.PAUSED, "⏸️ Suspendus")
            ]

            for i, (status, base_title) in enumerate(titles):
                count = stats.get(status, 0)
                # Limiter l'affichage pour éviter les nombres trop grands
                display_count = f"{count}" if count < 1000 else f"{count//1000}k+"
                self.status_tabs.setTabText(i, f"{base_title} ({display_count})")

        except Exception as e:
            print(f"❌ Erreur update_tab_titles_fast: {e}")

    def update_column_widths(self) -> None:
        """Ajuste la largeur des colonnes pour toutes les vues"""
        try:
            for view in self.views.values():
                if hasattr(view, 'horizontalHeader'):
                    header = view.horizontalHeader()
                    header.setSectionResizeMode(0, QHeaderView.Stretch)  # Nom du fichier
                    header.setSectionResizeMode(1, QHeaderView.ResizeToContents)  # Type
                    header.setSectionResizeMode(2, QHeaderView.ResizeToContents)  # Statut
                    header.setSectionResizeMode(3, QHeaderView.ResizeToContents)  # Progrès
                    header.setSectionResizeMode(4, QHeaderView.ResizeToContents)  # Vitesse
                    header.setSectionResizeMode(5, QHeaderView.ResizeToContents)  # ETA
                    header.setSectionResizeMode(6, QHeaderView.ResizeToContents)  # Taille
        except Exception as e:
            print(f"❌ Erreur update_column_widths: {e}")
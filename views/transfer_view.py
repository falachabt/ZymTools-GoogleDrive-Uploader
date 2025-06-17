"""
Vue pour afficher et gérer la liste des transferts - VERSION OPTIMISÉE HAUTE PERFORMANCE
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


class OptimizedTransferModel(QAbstractTableModel):
    """Modèle OPTIMISÉ pour afficher des milliers de transferts - VERSION HAUTE PERFORMANCE"""

    def __init__(self, transfer_manager: TransferManager, status_filter: TransferStatus = None):
        super().__init__()
        self.transfer_manager = transfer_manager
        self.status_filter = status_filter

        # Cache virtuel pour l'affichage (seulement ce qui est visible)
        self.display_data = []  # Liste des transfer_ids visibles
        self.data_cache = {}    # Cache des données pour les lignes visibles

        # Headers
        self.headers = ["Fichier", "Type", "Statut", "Progrès", "Vitesse", "ETA", "Taille", "Destination"]

        # Pagination virtuelle pour gros volumes
        self.page_size = 100
        self.current_page = 0
        self.total_count = 0

        # Timer pour les mises à jour différées (évite le spam)
        self.update_timer = QTimer()
        self.update_timer.setSingleShot(True)
        self.update_timer.timeout.connect(self._delayed_refresh)

        # Batch updates pour éviter les refresh constants
        self.pending_updates = set()
        self.batch_timer = QTimer()
        self.batch_timer.timeout.connect(self._process_batch_updates)
        self.batch_timer.start(500)  # Traiter toutes les 500ms

        # Connecter aux signaux OPTIMISÉS
        self.transfer_manager.transfer_added.connect(self.queue_refresh)
        self.transfer_manager.transfer_removed.connect(self.queue_refresh)

        # Utiliser les nouveaux signaux batch si disponibles
        if hasattr(transfer_manager, 'batch_transfers_updated'):
            transfer_manager.batch_transfers_updated.connect(self.on_batch_updated)
        if hasattr(transfer_manager, 'stats_updated'):
            transfer_manager.stats_updated.connect(self.on_stats_updated)

        # Charger données initiales
        self.refresh_data()

    def rowCount(self, parent=QModelIndex()) -> int:
        """Retourne le nombre total (peut être virtualisé)"""
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

        # Chargement paresseux des données
        if transfer_id not in self.data_cache:
            self._load_transfer_data(transfer_id)

        transfer_data = self.data_cache.get(transfer_id)
        if not transfer_data:
            return None

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

    def _load_transfer_data(self, transfer_id: str) -> None:
        """Charge les données d'un transfert spécifique (paresseux)"""
        transfer = self.transfer_manager.get_transfer(transfer_id)
        if not transfer:
            return

        # Créer entrée cache avec données formatées
        self.data_cache[transfer_id] = {
            'file_name': transfer.file_name,
            'type': transfer.transfer_type.value,
            'status': transfer.status.value,
            'progress': transfer.progress,
            'speed_text': transfer.get_speed_text() if hasattr(transfer, 'get_speed_text') else '0 B/s',
            'eta_text': transfer.get_eta_text() if hasattr(transfer, 'get_eta_text') else '∞',
            'size_text': self._format_size(transfer.file_size),
            'destination': transfer.destination_path,
            'is_individual_file': transfer.is_individual_file()
        }

    def _format_size(self, size_bytes: int) -> str:
        """Formate la taille rapidement"""
        if size_bytes == 0:
            return ""

        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f} TB"

    def refresh_data(self) -> None:
        """Rafraîchit les données avec optimisation pour gros volumes"""
        self.beginResetModel()

        # Vider les caches
        self.display_data.clear()
        self.data_cache.clear()

        try:
            if self.status_filter:
                # Utiliser la méthode optimisée si disponible
                if hasattr(self.transfer_manager, 'get_transfers_by_status_fast'):
                    transfer_ids = self.transfer_manager.get_transfers_by_status_fast(
                        self.status_filter, limit=1000  # Limiter pour éviter le lag
                    )
                    self.display_data.extend(transfer_ids)
                else:
                    # Fallback vers méthode classique
                    individual_files = self.transfer_manager.get_individual_file_transfers()
                    filtered_ids = [tid for tid, t in individual_files.items()
                                  if t.status == self.status_filter]
                    self.display_data.extend(filtered_ids[:1000])  # Limiter à 1000
            else:
                # Tous les fichiers individuels (avec limite)
                individual_files = self.transfer_manager.get_individual_file_transfers()
                self.display_data.extend(list(individual_files.keys())[:1000])

        except Exception as e:
            print(f"Erreur refresh_data: {e}")

        self.endResetModel()

    def queue_refresh(self) -> None:
        """Queue un refresh pour éviter le spam"""
        if not self.update_timer.isActive():
            self.update_timer.start(300)  # Attendre 300ms

    def _delayed_refresh(self) -> None:
        """Refresh différé"""
        self.refresh_data()

    def on_batch_updated(self, transfer_ids: list) -> None:
        """Traite les mises à jour par batch"""
        # Marquer ces transferts pour mise à jour
        for transfer_id in transfer_ids:
            if transfer_id in self.data_cache:
                # Invalider le cache pour forcer le rechargement
                del self.data_cache[transfer_id]

        # Invalider les lignes affichées
        self.queue_refresh()

    def on_stats_updated(self, stats: dict) -> None:
        """Mise à jour des statistiques (peut déclencher refresh si nécessaire)"""
        # Pour les gros volumes, on évite les refresh constants
        pass

    def _process_batch_updates(self) -> None:
        """Traite les mises à jour en attente par batch"""
        if self.pending_updates:
            # Invalider les caches des transferts mis à jour
            for transfer_id in self.pending_updates:
                if transfer_id in self.data_cache:
                    del self.data_cache[transfer_id]

            self.pending_updates.clear()

            # Émettre signal de changement de données pour la plage visible
            if self.display_data:
                top_left = self.index(0, 0)
                bottom_right = self.index(min(len(self.display_data) - 1, 100), self.columnCount() - 1)
                self.dataChanged.emit(top_left, bottom_right)

    def get_transfer_id_from_row(self, row: int) -> str:
        """Récupère l'ID du transfert à partir d'une ligne"""
        if 0 <= row < len(self.display_data):
            return self.display_data[row]
        return None


class TransferStatsWidget(QWidget):
    """Widget d'affichage des statistiques - VERSION OPTIMISÉE"""

    def __init__(self, transfer_manager: TransferManager):
        super().__init__()
        self.transfer_manager = transfer_manager
        self.setup_ui()

        # Utiliser les signaux optimisés si disponibles
        if hasattr(transfer_manager, 'stats_updated'):
            transfer_manager.stats_updated.connect(self.update_stats_fast)
        else:
            # Fallback vers timer classique
            self.update_timer = QTimer()
            self.update_timer.timeout.connect(self.update_stats)
            QTimer.singleShot(2000, self.start_updates)

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
        """Mise à jour rapide avec les compteurs pré-calculés"""
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

                # Vitesse globale approximative
                active_transfers = self.transfer_manager.get_active_transfers()
                total_speed = sum(t.speed for t in list(active_transfers.values())[:50])  # Échantillon
                self.speed_label.setText(f"⚡ Vitesse: {self.format_speed(total_speed)}")
            else:
                self.global_progress.setValue(100 if completed > 0 else 0)
                self.speed_label.setText("⚡ Vitesse: 0 B/s")

        except Exception as e:
            print(f"Erreur update_stats_fast: {e}")

    def start_updates(self) -> None:
        """Démarre les mises à jour classiques (fallback)"""
        self.update_timer.start(2000)  # Moins fréquent pour éviter la charge
        self.update_stats()

    def update_stats(self) -> None:
        """Mise à jour classique (fallback)"""
        try:
            if hasattr(self.transfer_manager, 'get_fast_stats'):
                stats = self.transfer_manager.get_fast_stats()
                self.update_stats_fast(stats)
            else:
                # Fallback vers calcul manuel (moins optimal)
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
            print(f"Erreur update_stats: {e}")

    def format_speed(self, speed: float) -> str:
        """Formate la vitesse"""
        if speed < 1024:
            return f"{speed:.1f} B/s"
        elif speed < 1024 * 1024:
            return f"{speed / 1024:.1f} KB/s"
        elif speed < 1024 * 1024 * 1024:
            return f"{speed / (1024 * 1024):.1f} MB/s"
        else:
            return f"{speed / (1024 * 1024 * 1024):.1f} GB/s"


class TransferPanel(QWidget):
    """Panneau principal de gestion des transferts - VERSION OPTIMISÉE"""

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
        """Configure l'interface utilisateur"""
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

        # Créer le widget d'onglets
        self.tab_widget = QTabWidget()

        # Onglet 1: Vue complète des transferts (MODIFIÉ : ne montre que les transferts principaux)
        self.list_tab = QWidget()
        list_layout = QVBoxLayout(self.list_tab)

        # Vue des transferts principaux seulement
        self.transfer_model = TransferListModel(self.transfer_manager, show_individual_files=False)
        self.transfer_view = TransferTreeView()
        self.transfer_view.setModel(self.transfer_model)
        list_layout.addWidget(self.transfer_view)

        # Ajouter l'onglet de liste
        self.tab_widget.addTab(self.list_tab, "📋 Liste complète")

        # Onglet 2: Vue de la queue de transferts (MODIFIÉ : montre les fichiers individuels)
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
        QTimer.singleShot(100, self.initialize_column_widths)

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

    def cancel_selected_transfer(self) -> None:
        """Annule le transfert sélectionné"""
        selected_row = self.transfer_view.currentIndex().row()
        if selected_row >= 0:
            transfer_id = self.transfer_model.get_transfer_id_from_row(selected_row)
            if transfer_id:
                self.cancel_transfer(transfer_id)

    def cancel_transfer(self, transfer_id: str) -> None:
        """Annule un transfert"""
        self.cancel_transfer_requested.emit(transfer_id)
        self.transfer_manager.cancel_transfer(transfer_id)

    def remove_transfer(self, transfer_id: str) -> None:
        """Supprime un transfert de la liste"""
        self.transfer_manager.remove_transfer(transfer_id)

    def retry_transfer(self, transfer_id: str) -> None:
        """Réessaie un transfert (pour une implémentation future)"""
        self.transfer_manager.update_transfer_status(transfer_id, TransferStatus.PENDING)

    def clear_completed_transfers(self) -> None:
        """Supprime tous les transferts terminés"""
        self.transfer_manager.clear_completed_transfers()

    def clear_all_transfers(self) -> None:
        """Supprime tous les transferts"""
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
                    self.cancel_action.setEnabled(transfer.status in [
                        TransferStatus.PENDING, TransferStatus.IN_PROGRESS, TransferStatus.PAUSED
                    ])
                    return

        self.cancel_action.setEnabled(False)

    def get_transfer_count(self) -> int:
        """Retourne le nombre de transferts"""
        return len(self.transfer_manager.get_all_transfers())

    def get_active_transfer_count(self) -> int:
        """Retourne le nombre de transferts actifs"""
        return len(self.transfer_manager.get_active_transfers())

    def initialize_column_widths(self) -> None:
        """Initialise la largeur des colonnes pour la vue principale"""
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


class TransferQueuePanel(QWidget):
    """Panneau de queue OPTIMISÉ pour gros volumes"""

    def __init__(self, transfer_manager: TransferManager):
        super().__init__()
        self.transfer_manager = transfer_manager
        self.setup_ui()
        self.connect_signals()

        # Timer optimisé pour rafraîchissement
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self.refresh_current_model)
        self.refresh_timer.start(1000)  # 1 seconde

    def setup_ui(self) -> None:
        """Configure l'interface avec modèles optimisés"""
        layout = QVBoxLayout(self)

        title_label = QLabel("📋 Queue de transferts (Fichiers individuels)")
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(12)
        title_label.setFont(title_font)
        layout.addWidget(title_label)

        # Créer les modèles optimisés pour chaque statut
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
            # Créer modèle dédié pour ce statut avec optimisation
            model = OptimizedTransferModel(self.transfer_manager, status)
            self.models[status] = model

            # Créer vue optimisée
            view = QTableView()  # Plus rapide que TreeView pour de gros volumes
            view.setModel(model)
            view.setAlternatingRowColors(True)
            view.setSelectionBehavior(QAbstractItemView.SelectRows)
            view.setSelectionMode(QAbstractItemView.ExtendedSelection)
            view.setSortingEnabled(True)
            self.views[status] = view

            # Créer onglet
            tab_widget = QWidget()
            tab_layout = QVBoxLayout(tab_widget)
            tab_layout.addWidget(view)

            self.status_tabs.addTab(tab_widget, f"{tab_name} (0)")

        layout.addWidget(self.status_tabs)

    def connect_signals(self) -> None:
        """Connecte aux signaux optimisés"""
        if hasattr(self.transfer_manager, 'stats_updated'):
            self.transfer_manager.stats_updated.connect(self.update_tab_titles_fast)

    def refresh_current_model(self) -> None:
        """Rafraîchit seulement le modèle de l'onglet visible (optimisation)"""
        try:
            # Refresh seulement l'onglet visible pour économiser les ressources
            current_index = self.status_tabs.currentIndex()
            if current_index >= 0:
                statuses = list(self.models.keys())
                if current_index < len(statuses):
                    current_status = statuses[current_index]
                    self.models[current_status].queue_refresh()
        except Exception as e:
            print(f"Erreur refresh_current_model: {e}")

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
            print(f"Erreur update_tab_titles_fast: {e}")

    def update_column_widths(self) -> None:
        """Ajuste la largeur des colonnes pour toutes les vues"""
        for view in self.views.values():
            if hasattr(view, 'header'):
                header = view.header()
                header.setSectionResizeMode(0, QHeaderView.Stretch)  # Nom du fichier
                header.setSectionResizeMode(1, QHeaderView.ResizeToContents)  # Type
                header.setSectionResizeMode(2, QHeaderView.ResizeToContents)  # Statut
                header.setSectionResizeMode(3, QHeaderView.ResizeToContents)  # Progrès
                header.setSectionResizeMode(4, QHeaderView.ResizeToContents)  # Vitesse
                header.setSectionResizeMode(5, QHeaderView.ResizeToContents)  # ETA
                header.setSectionResizeMode(6, QHeaderView.ResizeToContents)  # Taille


class CustomTransferProxyModel(QSortFilterProxyModel):
    """Proxy model personnalisé pour les transferts avec meilleur rafraîchissement"""

    MAX_ROWS = 1000  # Maximum 1000 lignes affichées pour éviter le lag

    def __init__(self):
        super().__init__()
        # Actualiser automatiquement quand le modèle source change
        self.setDynamicSortFilter(True)

    def rowCount(self, parent=None):
        """Limite le nombre de lignes affichées"""
        original_count = super().rowCount(parent)
        return min(original_count, self.MAX_ROWS)

    def filterAcceptsRow(self, source_row, source_parent):
        """Accepte seulement les N premières lignes + filtre normal"""
        if source_row >= self.MAX_ROWS:
            return False
        return super().filterAcceptsRow(source_row, source_parent)
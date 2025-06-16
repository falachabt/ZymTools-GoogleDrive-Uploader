"""
Vue pour afficher et gérer la liste des transferts
"""

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTreeView,
                             QPushButton, QToolBar, QAction, QLabel,
                             QProgressBar, QSplitter, QGroupBox, QMenu,
                             QHeaderView, QAbstractItemView, QTabWidget)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QSize, QSortFilterProxyModel
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
        self.setup_ui()

        # MODIFICATION : Ne pas démarrer le timer immédiatement
        # Créer le timer mais ne pas le démarrer tout de suite
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_stats)

        # Démarrer le timer avec un délai pour laisser le temps à tout de s'initialiser
        QTimer.singleShot(2000, self.start_updates)  # Démarrer après 2 secondes

    def start_updates(self) -> None:
        """Démarre les mises à jour automatiques"""
        self.update_timer.start(1000)  # Mise à jour chaque seconde
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
                total_progress = sum(t.progress for t in active_transfers.values())
                global_progress = total_progress / len(active_transfers)

                total_speed = sum(t.speed for t in active_transfers.values())

                self.global_progress.setValue(int(global_progress))
                self.speed_label.setText(f"⚡ Vitesse: {self.format_speed(total_speed)}")
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
    """Panneau principal de gestion des transferts"""

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

        # Onglet 1: Vue complète des transferts
        self.list_tab = QWidget()
        list_layout = QVBoxLayout(self.list_tab)

        # Vue des transferts
        self.transfer_model = TransferListModel(self.transfer_manager)
        self.transfer_view = TransferTreeView()
        self.transfer_view.setModel(self.transfer_model)
        list_layout.addWidget(self.transfer_view)

        # Ajouter l'onglet de liste
        self.tab_widget.addTab(self.list_tab, "📋 Liste complète")

        # Onglet 2: Vue de la queue de transferts
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
    """Panneau affichant la queue des transferts avec des onglets séparés pour les différents états"""

    def __init__(self, transfer_manager: TransferManager):
        """
        Initialise le panneau de queue de transferts

        Args:
            transfer_manager: Gestionnaire de transferts
        """
        super().__init__()
        self.transfer_manager = transfer_manager
        self.setup_ui()
        self.connect_signals()

    def setup_ui(self) -> None:
        """Configure l'interface utilisateur"""
        layout = QVBoxLayout(self)

        # Titre du panneau
        title_label = QLabel("📋 Queue de transferts")
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(12)
        title_label.setFont(title_font)
        layout.addWidget(title_label)

        # Créer les modèles filtrés pour chaque état
        self.main_model = TransferListModel(self.transfer_manager)

        # Créer le widget d'onglets pour les différents statuts
        self.status_tabs = QTabWidget()
        self.create_queue_views()
        layout.addWidget(self.status_tabs)

    def create_queue_views(self) -> None:
        """Crée les vues pour chaque état de transfert sous forme d'onglets"""
        # Onglet pour les transferts en cours
        in_progress_tab = QWidget()
        in_progress_layout = QVBoxLayout(in_progress_tab)

        self.in_progress_proxy = QSortFilterProxyModel()
        self.in_progress_proxy.setSourceModel(self.main_model)
        self.in_progress_proxy.setFilterKeyColumn(2)  # Colonne de statut
        self.in_progress_proxy.setFilterFixedString(TransferStatus.IN_PROGRESS.value)

        self.in_progress_view = TransferTreeView()
        self.in_progress_view.setModel(self.in_progress_proxy)
        in_progress_layout.addWidget(self.in_progress_view)

        # Onglet pour les transferts en attente
        pending_tab = QWidget()
        pending_layout = QVBoxLayout(pending_tab)

        self.pending_proxy = QSortFilterProxyModel()
        self.pending_proxy.setSourceModel(self.main_model)
        self.pending_proxy.setFilterKeyColumn(2)  # Colonne de statut
        self.pending_proxy.setFilterFixedString(TransferStatus.PENDING.value)

        self.pending_view = TransferTreeView()
        self.pending_view.setModel(self.pending_proxy)
        pending_layout.addWidget(self.pending_view)

        # Onglet pour les transferts en erreur
        error_tab = QWidget()
        error_layout = QVBoxLayout(error_tab)

        self.error_proxy = QSortFilterProxyModel()
        self.error_proxy.setSourceModel(self.main_model)
        self.error_proxy.setFilterKeyColumn(2)  # Colonne de statut
        self.error_proxy.setFilterFixedString(TransferStatus.ERROR.value)

        self.error_view = TransferTreeView()
        self.error_view.setModel(self.error_proxy)
        error_layout.addWidget(self.error_view)

        # Onglet pour les transferts terminés
        completed_tab = QWidget()
        completed_layout = QVBoxLayout(completed_tab)

        self.completed_proxy = QSortFilterProxyModel()
        self.completed_proxy.setSourceModel(self.main_model)
        self.completed_proxy.setFilterKeyColumn(2)  # Colonne de statut
        self.completed_proxy.setFilterFixedString(TransferStatus.COMPLETED.value)

        self.completed_view = TransferTreeView()
        self.completed_view.setModel(self.completed_proxy)
        completed_layout.addWidget(self.completed_view)

        # Onglet pour les transferts annulés
        cancelled_tab = QWidget()
        cancelled_layout = QVBoxLayout(cancelled_tab)

        self.cancelled_proxy = QSortFilterProxyModel()
        self.cancelled_proxy.setSourceModel(self.main_model)
        self.cancelled_proxy.setFilterKeyColumn(2)  # Colonne de statut
        self.cancelled_proxy.setFilterFixedString(TransferStatus.CANCELLED.value)

        self.cancelled_view = TransferTreeView()
        self.cancelled_view.setModel(self.cancelled_proxy)
        cancelled_layout.addWidget(self.cancelled_view)

        # Onglet pour les transferts suspendus
        paused_tab = QWidget()
        paused_layout = QVBoxLayout(paused_tab)

        self.paused_proxy = QSortFilterProxyModel()
        self.paused_proxy.setSourceModel(self.main_model)
        self.paused_proxy.setFilterKeyColumn(2)  # Colonne de statut
        self.paused_proxy.setFilterFixedString(TransferStatus.PAUSED.value)

        self.paused_view = TransferTreeView()
        self.paused_view.setModel(self.paused_proxy)
        paused_layout.addWidget(self.paused_view)

        # Ajouter les onglets au widget d'onglets
        self.status_tabs.addTab(in_progress_tab, "🔄 En cours")
        self.status_tabs.addTab(pending_tab, "⏳ En attente")
        self.status_tabs.addTab(error_tab, "❌ Erreurs")
        self.status_tabs.addTab(completed_tab, "✅ Terminés")
        self.status_tabs.addTab(cancelled_tab, "🚫 Annulés")
        self.status_tabs.addTab(paused_tab, "⏸️ Suspendus")

    def connect_signals(self) -> None:
        """Connecte les signaux"""
        # Les signaux sont déjà connectés dans le modèle principal
        pass

    def update_column_widths(self) -> None:
        """Ajuste la largeur des colonnes pour toutes les vues"""
        for view in [self.in_progress_view, self.pending_view, self.error_view, 
                    self.completed_view, self.cancelled_view, self.paused_view]:
            header = view.header()
            header.setSectionResizeMode(0, QHeaderView.Stretch)  # Nom du fichier
            header.setSectionResizeMode(1, QHeaderView.ResizeToContents)  # Type
            header.setSectionResizeMode(2, QHeaderView.ResizeToContents)  # Statut
            header.setSectionResizeMode(3, QHeaderView.ResizeToContents)  # Progrès
            header.setSectionResizeMode(4, QHeaderView.ResizeToContents)  # Vitesse
            header.setSectionResizeMode(5, QHeaderView.ResizeToContents)  # ETA
            header.setSectionResizeMode(6, QHeaderView.ResizeToContents)  # Taille

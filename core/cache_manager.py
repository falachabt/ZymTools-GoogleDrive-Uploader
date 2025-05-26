"""
Gestionnaire de cache pour les données locales et Google Drive
"""

from datetime import datetime, timedelta
from typing import Dict, Tuple, Any, Optional


class CacheManager:
    """Gestionnaire de cache pour les données locales et Google Drive"""

    def __init__(self, max_age_minutes: int = 5):
        """
        Initialise le gestionnaire de cache

        Args:
            max_age_minutes: Durée de vie maximale du cache en minutes
        """
        self.local_cache: Dict[str, Tuple[Any, datetime]] = {}  # Clé: chemin local
        self.drive_cache: Dict[str, Tuple[Any, datetime]] = {}  # Clé: folder_id
        self.max_age = timedelta(minutes=max_age_minutes)

    def get_local_cache(self, path: str) -> Optional[Any]:
        """
        Récupère le cache local pour un chemin donné

        Args:
            path: Chemin local du dossier

        Returns:
            Données du cache si valides, None sinon
        """
        if path in self.local_cache:
            data, timestamp = self.local_cache[path]
            if datetime.now() - timestamp < self.max_age:
                return data
        return None

    def set_local_cache(self, path: str, data: Any) -> None:
        """
        Stocke les données locales dans le cache

        Args:
            path: Chemin local du dossier
            data: Données à stocker
        """
        self.local_cache[path] = (data, datetime.now())

    def get_drive_cache(self, folder_id: str) -> Optional[Any]:
        """
        Récupère le cache Google Drive pour un dossier donné

        Args:
            folder_id: ID du dossier Google Drive

        Returns:
            Données du cache si valides, None sinon
        """
        if folder_id in self.drive_cache:
            data, timestamp = self.drive_cache[folder_id]
            if datetime.now() - timestamp < self.max_age:
                return data
        return None

    def set_drive_cache(self, folder_id: str, data: Any) -> None:
        """
        Stocke les données Google Drive dans le cache

        Args:
            folder_id: ID du dossier Google Drive
            data: Données à stocker
        """
        self.drive_cache[folder_id] = (data, datetime.now())

    def invalidate_local_cache(self, path: str) -> None:
        """
        Invalide le cache local pour un chemin spécifique

        Args:
            path: Chemin local à invalider
        """
        self.local_cache.pop(path, None)

    def invalidate_drive_cache(self, folder_id: str) -> None:
        """
        Invalide le cache Google Drive pour un dossier spécifique

        Args:
            folder_id: ID du dossier à invalider
        """
        self.drive_cache.pop(folder_id, None)

    def clear_cache(self) -> None:
        """Vide tout le cache"""
        self.local_cache.clear()
        self.drive_cache.clear()

    def clear_old_cache(self) -> None:
        """Supprime les entrées de cache trop anciennes"""
        now = datetime.now()

        # Cache local
        expired_local = [
            path for path, (data, timestamp) in self.local_cache.items()
            if now - timestamp >= self.max_age
        ]
        for path in expired_local:
            del self.local_cache[path]

        # Cache Google Drive
        expired_drive = [
            folder_id for folder_id, (data, timestamp) in self.drive_cache.items()
            if now - timestamp >= self.max_age
        ]
        for folder_id in expired_drive:
            del self.drive_cache[folder_id]

    def get_cache_stats(self) -> Dict[str, int]:
        """
        Retourne les statistiques du cache

        Returns:
            Dictionnaire avec les statistiques
        """
        return {
            'local_entries': len(self.local_cache),
            'drive_entries': len(self.drive_cache),
            'total_entries': len(self.local_cache) + len(self.drive_cache)
        }

    def is_cache_valid(self, timestamp: datetime) -> bool:
        """
        Vérifie si un timestamp de cache est encore valide

        Args:
            timestamp: Timestamp à vérifier

        Returns:
            True si le cache est valide, False sinon
        """
        return datetime.now() - timestamp < self.max_age

"""
Utilitaires Google Drive avec détection de doublons corrigée
"""

import time
import threading
from typing import Dict, Set, Optional, Tuple
from core.google_drive_client import GoogleDriveClient


class DuplicateTracker:
    """
    Tracker global pour éviter les doublons pendant les uploads concurrents
    """

    def __init__(self):
        self._lock = threading.RLock()
        # Track files being uploaded: (folder_id, filename) -> worker_id
        self._uploading_files: Dict[Tuple[str, str], str] = {}
        # Track completed uploads in THIS SESSION: (folder_id, filename) -> file_id
        self._uploaded_files: Dict[Tuple[str, str], str] = {}

    def claim_file(self, folder_id: str, filename: str, worker_id: str) -> bool:
        """
        Revendique un fichier pour upload. Retourne True si le claim réussit.
        """
        with self._lock:
            key = (folder_id, filename)

            # Vérifier si déjà uploadé DANS CETTE SESSION
            if key in self._uploaded_files:
                print(f"🔍 File {filename} already uploaded in this session")
                return False

            # Vérifier si déjà en cours d'upload
            if key in self._uploading_files:
                print(f"🔍 File {filename} already being uploaded by {self._uploading_files[key]}")
                return False

            # Revendiquer le fichier
            self._uploading_files[key] = worker_id
            print(f"✅ File {filename} claimed by {worker_id}")
            return True

    def mark_uploaded(self, folder_id: str, filename: str, file_id: str, worker_id: str):
        """
        Marque un fichier comme uploadé avec succès
        """
        with self._lock:
            key = (folder_id, filename)

            # Vérifier que c'est bien le worker qui a claim le fichier
            if self._uploading_files.get(key) == worker_id:
                # Déplacer vers les fichiers uploadés
                del self._uploading_files[key]
                self._uploaded_files[key] = file_id
                print(f"📝 File {filename} marked as uploaded by {worker_id}")

    def release_file(self, folder_id: str, filename: str, worker_id: str):
        """
        Libère un fichier en cas d'échec d'upload
        """
        with self._lock:
            key = (folder_id, filename)

            # Vérifier que c'est bien le worker qui a claim le fichier
            if self._uploading_files.get(key) == worker_id:
                del self._uploading_files[key]
                print(f"🔓 File {filename} released by {worker_id}")

    def is_uploaded_in_session(self, folder_id: str, filename: str) -> bool:
        """
        Vérifie si un fichier a déjà été uploadé dans cette session
        """
        with self._lock:
            return (folder_id, filename) in self._uploaded_files

    def is_being_uploaded(self, folder_id: str, filename: str) -> bool:
        """
        Vérifie si un fichier est en cours d'upload
        """
        with self._lock:
            return (folder_id, filename) in self._uploading_files

    def clear_all(self):
        """
        Nettoie tout le tracking
        """
        with self._lock:
            self._uploaded_files.clear()
            self._uploading_files.clear()
            print("🧹 All duplicate tracking cleared")

    def get_stats(self) -> Dict[str, int]:
        """Retourne les statistiques"""
        with self._lock:
            return {
                'uploaded_files': len(self._uploaded_files),
                'uploading_files': len(self._uploading_files)
            }


# Instance globale du tracker
_global_duplicate_tracker = DuplicateTracker()

def get_duplicate_tracker() -> DuplicateTracker:
    """Retourne l'instance globale du tracker de doublons"""
    return _global_duplicate_tracker


def already_exists_in_folder(drive_client: GoogleDriveClient, parent_id: str, name: str,
                           mime_type: Optional[str] = None, size: Optional[int] = None,
                           max_retries: int = 2, retry_delay: float = 0.5) -> bool:
    """
    Vérifie si un fichier/dossier avec le même nom existe dans le dossier cible.
    Version corrigée qui ne pollue pas le tracker.

    Args:
        drive_client: Client Google Drive
        parent_id: ID du dossier parent
        name: Nom du fichier à vérifier
        mime_type: Type MIME (optionnel, pour compatibilité)
        size: Taille (optionnelle, pour compatibilité)
        max_retries: Nombre maximum de tentatives
        retry_delay: Délai entre les tentatives

    Returns:
        True si le fichier existe déjà SUR GOOGLE DRIVE (pas dans le tracker)
    """

    print(f"🔍 Checking if '{name}' exists in folder {parent_id}")

    # Vérifier sur Google Drive avec retry
    for attempt in range(max_retries):
        try:
            # Utiliser une requête de recherche précise
            query = f"'{parent_id}' in parents and name = '{name}' and trashed = false"

            try:
                results = drive_client.service.files().list(
                    q=query,
                    pageSize=5,  # On a juste besoin de savoir si ça existe
                    fields="files(id, name)",
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True
                ).execute()

                files = results.get('files', [])

                if files:
                    # Fichier trouvé, vérifier plus précisément
                    for file in files:
                        if file['name'] == name:  # Double vérification
                            print(f"✅ File '{name}' already exists on Drive (ID: {file['id']})")
                            return True

                print(f"❌ File '{name}' does not exist on Drive")
                return False

            except Exception as api_error:
                print(f"⚠️ API error checking file existence (attempt {attempt + 1}): {api_error}")

                # Si c'est la dernière tentative, faire un fallback avec list_files
                if attempt == max_retries - 1:
                    print(f"🔄 Fallback: Using list_files for folder {parent_id}")
                    try:
                        files = drive_client.list_files(parent_id)
                        for file in files:
                            if file['name'] == name:
                                print(f"✅ File '{name}' found via fallback")
                                return True
                        print(f"❌ File '{name}' not found via fallback")
                        return False
                    except Exception as fallback_error:
                        print(f"❌ Fallback also failed: {fallback_error}")
                        # En cas d'échec total, on assume que le fichier n'existe pas
                        # (mieux vaut un doublon qu'un fichier non uploadé)
                        return False
                else:
                    # Attendre avant la prochaine tentative
                    time.sleep(retry_delay)

        except Exception as e:
            print(f"⚠️ Unexpected error checking file existence: {e}")
            if attempt == max_retries - 1:
                return False
            time.sleep(retry_delay)

    return False


def clear_duplicate_tracking():
    """
    Clears all duplicate tracking data from the global tracker.

    This function should be called at the start of a new upload session to reset
    the tracking state. It removes all records of files currently being uploaded
    and files that have been uploaded in the current session.

    Side Effects:
        - Resets the global duplicate tracker, `_global_duplicate_tracker`.
        - Any ongoing or completed upload tracking will be lost.
        - Should not be called during an active upload process, as it may lead
          to inconsistent states or duplicate uploads.
    """
    global _global_duplicate_tracker
    _global_duplicate_tracker.clear_all()


def get_duplicate_stats() -> Dict[str, int]:
    """
    Retourne les statistiques du tracking des doublons
    """
    tracker = get_duplicate_tracker()
    return tracker.get_stats()
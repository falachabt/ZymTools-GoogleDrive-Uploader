"""
Client pour interagir avec l'API Google Drive
"""

import os
import pickle
from typing import List, Dict, Any, Optional
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
from PyQt5.QtCore import pyqtSignal

from config.settings import SCOPES, get_credentials_path, get_token_path, UPLOAD_CHUNK_SIZE


class GoogleDriveClient:
    """Client pour gérer les interactions avec l'API Google Drive"""

    def __init__(self):
        """Initialise le client Google Drive"""
        self.service = self._get_drive_service()
        self.shared_drives_cache: Dict[str, bool] = {}

    def _get_drive_service(self):
        """
        Authentifie et retourne le service Google Drive

        Returns:
            Service Google Drive authentifié
        """
        creds = None
        token_path = get_token_path()

        # Charger les credentials existants
        if os.path.exists(token_path):
            with open(token_path, 'rb') as token:
                creds = pickle.load(token)

        # Vérifier la validité et rafraîchir si nécessaire
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                credentials_path = get_credentials_path()
                flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
                creds = flow.run_local_server(port=0)

            # Sauvegarder les credentials
            with open(token_path, 'wb') as token:
                pickle.dump(creds, token)

        return build('drive', 'v3', credentials=creds)

    def disconnect(self) -> None:
        """Se déconnecte de Google Drive en supprimant les tokens"""
        token_files = [get_token_path(), 'token.pickle']
        for token_file in token_files:
            if os.path.exists(token_file):
                try:
                    os.remove(token_file)
                except Exception:
                    pass

    def is_shared_drive(self, drive_id: str) -> bool:
        """
        Vérifie si un drive ID correspond à un Shared Drive

        Args:
            drive_id: ID du drive à vérifier

        Returns:
            True si c'est un Shared Drive, False sinon
        """
        if drive_id == 'root':
            return False

        if drive_id in self.shared_drives_cache:
            return self.shared_drives_cache[drive_id]

        shared_drives = self.list_shared_drives()
        shared_drive_ids = [drive['id'] for drive in shared_drives]

        for sid in shared_drive_ids:
            self.shared_drives_cache[sid] = True

        is_shared = drive_id in shared_drive_ids
        if not is_shared:
            self.shared_drives_cache[drive_id] = False

        return is_shared

    def get_drive_id_from_folder(self, folder_id: str) -> str:
        """
        Obtient l'ID du drive parent d'un dossier

        Args:
            folder_id: ID du dossier

        Returns:
            ID du drive parent
        """
        if folder_id == 'root':
            return 'root'

        try:
            metadata = self.service.files().get(
                fileId=folder_id,
                fields="driveId",
                supportsAllDrives=True
            ).execute()
            return metadata.get('driveId', 'root')
        except Exception:
            return 'root'

    def list_files(self, parent_id: str = 'root') -> List[Dict[str, Any]]:
        """
        Liste les fichiers d'un dossier

        Args:
            parent_id: ID du dossier parent

        Returns:
            Liste des fichiers et dossiers
        """
        query = f"'{parent_id}' in parents and trashed=false"
        drive_id = self.get_drive_id_from_folder(parent_id)
        is_shared = self.is_shared_drive(drive_id) if drive_id != 'root' else False

        try:
            if is_shared:
                results = self.service.files().list(
                    q=query,
                    pageSize=100,
                    fields="nextPageToken, files(id, name, mimeType, size, modifiedTime, driveId)",
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True,
                    corpora='drive',
                    driveId=drive_id
                ).execute()
            else:
                results = self.service.files().list(
                    q=query,
                    pageSize=100,
                    fields="nextPageToken, files(id, name, mimeType, size, modifiedTime)",
                    supportsAllDrives=True
                ).execute()
        except Exception as e:
            print(f"Erreur lors du listage des fichiers: {str(e)}")
            results = self.service.files().list(
                q=query,
                pageSize=100,
                fields="nextPageToken, files(id, name, mimeType, size, modifiedTime)",
                supportsAllDrives=True
            ).execute()

        return results.get('files', [])

    def list_shared_drives(self) -> List[Dict[str, Any]]:
        """
        Liste les Shared Drives disponibles

        Returns:
            Liste des Shared Drives
        """
        try:
            results = self.service.drives().list(
                pageSize=50,
                fields="nextPageToken, drives(id, name, createdTime)"
            ).execute()
            return results.get('drives', [])
        except Exception as e:
            print(f"Erreur lors du listage des Shared Drives: {str(e)}")
            return []

    def search_files(self, query_string: str) -> List[Dict[str, Any]]:
        """
        Recherche des fichiers par nom

        Args:
            query_string: Chaîne de recherche

        Returns:
            Liste des fichiers trouvés
        """
        query = f"name contains '{query_string}' and trashed=false"

        try:
            results = self.service.files().list(
                q=query,
                pageSize=100,
                fields="nextPageToken, files(id, name, mimeType, size, modifiedTime, parents, driveId)",
                supportsAllDrives=True,
                includeItemsFromAllDrives=True
            ).execute()
        except Exception as e:
            print(f"Erreur lors de la recherche: {str(e)}")
            results = self.service.files().list(
                q=query,
                pageSize=100,
                fields="nextPageToken, files(id, name, mimeType, size, modifiedTime, parents)"
            ).execute()

        return results.get('files', [])

    def get_file_metadata(self, file_id: str) -> Dict[str, Any]:
        """
        Récupère les métadonnées d'un fichier

        Args:
            file_id: ID du fichier

        Returns:
            Métadonnées du fichier
        """
        try:
            return self.service.files().get(
                fileId=file_id,
                fields="id, name, mimeType, size, modifiedTime, parents, description, driveId",
                supportsAllDrives=True
            ).execute()
        except Exception as e:
            print(f"Erreur lors de la récupération des métadonnées: {str(e)}")
            return self.service.files().get(
                fileId=file_id,
                fields="id, name, mimeType, size, modifiedTime, parents, description"
            ).execute()

    def download_file(self, file_id: str, file_name: str, local_dir: str,
                      progress_callback: Optional[pyqtSignal] = None) -> str:
        """
        Télécharge un fichier depuis Google Drive

        Args:
            file_id: ID du fichier à télécharger
            file_name: Nom du fichier
            local_dir: Dossier de destination
            progress_callback: Callback pour le progrès

        Returns:
            Chemin du fichier téléchargé
        """
        request = self.service.files().get_media(fileId=file_id)
        file_path = os.path.join(local_dir, file_name)

        with open(file_path, 'wb') as f:
            downloader = MediaIoBaseDownload(f, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()
                if progress_callback:
                    progress_callback.emit(int(status.progress() * 100))

        return file_path

    def upload_file(self, file_path: str, parent_id: str = 'root',
                    progress_callback: Optional[pyqtSignal] = None,
                    status_callback: Optional[pyqtSignal] = None,
                    is_shared_drive: bool = False) -> str:
        """
        Upload un fichier vers Google Drive

        Args:
            file_path: Chemin du fichier local
            parent_id: ID du dossier parent
            progress_callback: Callback pour le progrès
            status_callback: Callback pour le statut
            is_shared_drive: True si c'est un Shared Drive

        Returns:
            ID du fichier uploadé
        """
        file_name = os.path.basename(file_path)
        file_metadata = {
            'name': file_name,
            'parents': [parent_id]
        }

        if status_callback:
            status_callback.emit(f"⬆️ Upload: {file_name}")

        media = MediaFileUpload(file_path, resumable=True, chunksize=UPLOAD_CHUNK_SIZE)

        try:
            request = self.service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id',
                supportsAllDrives=True
            )
        except Exception as e:
            print(f"Erreur lors de la création de la requête d'upload: {str(e)}")
            request = self.service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id'
            )

        response = None
        file_size = os.path.getsize(file_path)
        uploaded = 0

        while response is None:
            status, response = request.next_chunk()
            if status:
                uploaded += UPLOAD_CHUNK_SIZE
                progress = min(int((uploaded / file_size) * 100), 100)
                if progress_callback:
                    progress_callback.emit(progress)

        return response.get('id')

    def create_folder(self, folder_name: str, parent_id: str = 'root',
                      is_shared_drive: bool = False) -> str:
        """
        Crée un dossier dans Google Drive

        Args:
            folder_name: Nom du dossier
            parent_id: ID du dossier parent
            is_shared_drive: True si c'est un Shared Drive

        Returns:
            ID du dossier créé
        """
        file_metadata = {
            'name': folder_name,
            'mimeType': 'application/vnd.google-apps.folder',
            'parents': [parent_id]
        }

        try:
            folder = self.service.files().create(
                body=file_metadata,
                fields='id',
                supportsAllDrives=True
            ).execute()
        except Exception as e:
            print(f"Erreur lors de la création du dossier: {str(e)}")
            folder = self.service.files().create(
                body=file_metadata,
                fields='id'
            ).execute()

        return folder.get('id')

    def rename_item(self, file_id: str, new_name: str) -> Dict[str, Any]:
        """
        Renomme un fichier ou dossier

        Args:
            file_id: ID du fichier/dossier
            new_name: Nouveau nom

        Returns:
            Métadonnées mises à jour
        """
        file_metadata = {'name': new_name}

        try:
            updated_file = self.service.files().update(
                fileId=file_id,
                body=file_metadata,
                fields='id, name',
                supportsAllDrives=True
            ).execute()
        except Exception as e:
            print(f"Erreur lors du renommage: {str(e)}")
            updated_file = self.service.files().update(
                fileId=file_id,
                body=file_metadata,
                fields='id, name'
            ).execute()

        return updated_file

    def delete_item(self, file_id: str) -> None:
        """
        Met un fichier/dossier à la corbeille

        Args:
            file_id: ID du fichier/dossier
        """
        try:
            self.service.files().update(
                fileId=file_id,
                body={'trashed': True},
                supportsAllDrives=True
            ).execute()
        except Exception as e:
            print(f"Erreur lors de la suppression: {str(e)}")
            self.service.files().update(
                fileId=file_id,
                body={'trashed': True}
            ).execute()

    def permanently_delete_item(self, file_id: str) -> None:
        """
        Supprime définitivement un fichier/dossier

        Args:
            file_id: ID du fichier/dossier
        """
        try:
            self.service.files().delete(
                fileId=file_id,
                supportsAllDrives=True
            ).execute()
        except Exception as e:
            print(f"Erreur lors de la suppression permanente: {str(e)}")
            self.service.files().delete(fileId=file_id).execute()

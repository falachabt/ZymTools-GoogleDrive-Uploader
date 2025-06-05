
"""
Threads spécialisés pour les opérations de fichiers avec gestion d'erreurs améliorée
"""

import os
import time
from typing import Optional, List, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
from PyQt5.QtCore import QMutex, QMutexLocker

from core.google_drive_client import GoogleDriveClient
from models.transfer_models import TransferManager, TransferType, TransferStatus
from .base_thread import BaseOperationThread


class FileUploadThread(BaseOperationThread):
    """Thread amélioré pour l'upload de fichiers individuels"""
    
    def __init__(self, drive_client: GoogleDriveClient, file_path: str,
                 parent_id: str = 'root', is_shared_drive: bool = False,
                 transfer_manager: Optional[TransferManager] = None):
        super().__init__(transfer_manager)
        self.drive_client = drive_client
        self.file_path = file_path
        self.parent_id = parent_id
        self.is_shared_drive = is_shared_drive
        self.file_size = os.path.getsize(file_path) if os.path.isfile(file_path) else 0
        self.bytes_transferred = 0
    
    def create_transfer_entry(self) -> str:
        """Crée l'entrée de transfert pour l'upload de fichier"""
        file_name = os.path.basename(self.file_path)
        return self.transfer_manager.add_transfer(
            TransferType.UPLOAD_FILE,
            self.file_path,
            f"Google Drive/{self.parent_id}",
            file_name,
            self.file_size
        )
    
    def execute_operation(self) -> str:
        """Exécute l'upload du fichier"""
        file_name = os.path.basename(self.file_path)
        
        def progress_callback(progress: int) -> None:
            if self.is_operation_cancelled():
                return
            self.bytes_transferred = int((progress / 100.0) * self.file_size)
            self.update_progress(progress, self.bytes_transferred, self.file_size)
        
        def status_callback(status: str) -> None:
            if not self.is_operation_cancelled():
                self.update_status(f"📤 {file_name}: {status}")
        
        try:
            self.update_status(f"🚀 Début upload: {file_name}")
            
            file_id = self.drive_client.upload_file(
                self.file_path,
                self.parent_id,
                progress_callback,
                status_callback,
                self.is_shared_drive
            )
            
            if not self.is_operation_cancelled():
                self.update_status(f"✅ Upload terminé: {file_name}")
                return file_id
            else:
                return "Annulé"
                
        except Exception as e:
            error_msg = f"❌ Erreur upload {file_name}: {str(e)}"
            self.update_status(error_msg)
            raise Exception(error_msg)


class FolderUploadThread(BaseOperationThread):
    """Thread amélioré pour l'upload de dossiers avec traçabilité détaillée"""
    
    def __init__(self, drive_client: GoogleDriveClient, folder_path: str,
                 parent_id: str = 'root', is_shared_drive: bool = False,
                 transfer_manager: Optional[TransferManager] = None,
                 max_workers: int = 2):
        super().__init__(transfer_manager)
        self.drive_client = drive_client
        self.folder_path = folder_path
        self.parent_id = parent_id
        self.is_shared_drive = is_shared_drive
        self.max_workers = max_workers
        
        # Statistiques détaillées
        self.total_files = 0
        self.completed_files = 0
        self.failed_files = 0
        self.total_size = 0
        self.transferred_size = 0
        
        # Suivi détaillé des fichiers
        self.file_results: List[Dict[str, Any]] = []
        self.failed_files_list: List[Dict[str, Any]] = []
        
        # Mutex pour la protection des accès concurrents
        self.stats_mutex = QMutex()
    
    def create_transfer_entry(self) -> str:
        """Crée l'entrée de transfert pour l'upload de dossier"""
        folder_name = os.path.basename(self.folder_path)
        self.total_files, self.total_size = self._analyze_folder()
        
        return self.transfer_manager.add_transfer(
            TransferType.UPLOAD_FOLDER,
            self.folder_path,
            f"Google Drive/{self.parent_id}",
            folder_name,
            self.total_size
        )
    
    def execute_operation(self) -> str:
        """Exécute l'upload du dossier avec traçabilité détaillée"""
        folder_name = os.path.basename(self.folder_path)
        
        try:
            if self.total_files == 0:
                self.update_status("📁 Création du dossier vide...")
                folder_id = self.drive_client.create_folder(
                    folder_name, self.parent_id, self.is_shared_drive
                )
                return folder_id
            
            self.update_status(f"🔍 Analyse: {self.total_files} fichiers ({self._format_size(self.total_size)})")
            
            # Créer le dossier principal
            main_folder_id = self.drive_client.create_folder(
                folder_name, self.parent_id, self.is_shared_drive
            )
            
            # Créer la structure de dossiers
            self.update_status("📁 Création de la structure de dossiers...")
            folder_mapping = self._create_folder_structure(main_folder_id)
            
            # Collecter tous les fichiers
            all_files = self._collect_all_files()
            
            # Upload avec parallélisme contrôlé
            self.update_status(f"⚡ Upload parallèle ({self.max_workers} workers simultanés)...")
            self._upload_files_parallel(all_files, folder_mapping)
            
            # Rapport final
            success_count = self.completed_files
            total_count = self.total_files
            
            if self.failed_files > 0:
                error_summary = f"⚠️ Upload terminé: {success_count}/{total_count} fichiers réussis, {self.failed_files} échecs"
                self._log_failed_files()
                self.update_status(error_summary)
            else:
                self.update_status(f"🎉 Upload réussi: {success_count}/{total_count} fichiers")
            
            return main_folder_id
            
        except Exception as e:
            error_msg = f"❌ Erreur upload dossier {folder_name}: {str(e)}"
            self.update_status(error_msg)
            raise Exception(error_msg)
    
    def _analyze_folder(self) -> tuple:
        """Analyse le dossier pour compter les fichiers et calculer la taille"""
        count = 0
        total_size = 0
        
        try:
            for root, dirs, files in os.walk(self.folder_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    try:
                        if os.path.exists(file_path):
                            count += 1
                            total_size += os.path.getsize(file_path)
                    except (OSError, IOError):
                        pass
        except Exception:
            pass
        
        return count, total_size
    
    def _collect_all_files(self) -> List[Dict[str, Any]]:
        """Collecte tous les fichiers avec leurs informations détaillées"""
        files_to_process = []
        
        for root, dirs, files in os.walk(self.folder_path):
            rel_path = os.path.relpath(root, self.folder_path)
            
            for file in files:
                file_path = os.path.join(root, file)
                try:
                    file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0
                    files_to_process.append({
                        'file_path': file_path,
                        'file_name': file,
                        'relative_dir': rel_path if rel_path != '.' else '',
                        'size': file_size,
                        'relative_path': os.path.join(rel_path, file) if rel_path != '.' else file
                    })
                except (OSError, IOError) as e:
                    # Fichier inaccessible
                    self.update_status(f"⚠️ Fichier inaccessible: {file} - {str(e)}")
        
        return files_to_process
    
    def _create_folder_structure(self, main_folder_id: str) -> Dict[str, str]:
        """Crée la structure de dossiers sur Google Drive"""
        folder_mapping = {'': main_folder_id}
        
        try:
            for root, dirs, files in os.walk(self.folder_path):
                rel_path = os.path.relpath(root, self.folder_path)
                
                if rel_path == '.':
                    continue
                
                parent_rel_path = os.path.dirname(rel_path)
                if parent_rel_path == '.':
                    parent_rel_path = ''
                
                if parent_rel_path in folder_mapping:
                    parent_drive_id = folder_mapping[parent_rel_path]
                    folder_name = os.path.basename(root)
                    
                    self.update_status(f"📁 Création: {rel_path}")
                    folder_id = self.drive_client.create_folder(
                        folder_name, parent_drive_id, self.is_shared_drive
                    )
                    folder_mapping[rel_path] = folder_id
                    
        except Exception as e:
            raise Exception(f"Erreur création dossiers: {str(e)}")
        
        return folder_mapping
    
    def _upload_files_parallel(self, files: List[Dict[str, Any]], folder_mapping: Dict[str, str]) -> None:
        """Upload les fichiers en parallèle avec suivi détaillé"""
        
        def upload_single_file(file_info):
            """Upload un seul fichier avec gestion d'erreur détaillée"""
            try:
                if self.is_operation_cancelled():
                    return {'success': False, 'cancelled': True, 'file_info': file_info}
                
                parent_id = folder_mapping.get(file_info['relative_dir'], self.parent_id)
                relative_path = file_info['relative_path']
                
                self.update_status(f"📤 Upload: {relative_path}")
                
                file_id = self.drive_client.upload_file(
                    file_info['file_path'],
                    parent_id,
                    None,  # Pas de callback de progrès individuel pour éviter le spam
                    None,
                    self.is_shared_drive
                )
                
                # Mettre à jour les statistiques
                with QMutexLocker(self.stats_mutex):
                    self.completed_files += 1
                    self.transferred_size += file_info['size']
                    progress = int((self.completed_files / self.total_files) * 100)
                    self.update_progress(progress, self.transferred_size, self.total_size)
                
                self.update_status(f"✅ Terminé: {relative_path}")
                
                return {
                    'success': True,
                    'file_id': file_id,
                    'file_info': file_info
                }
                
            except Exception as e:
                error_msg = f"❌ Échec: {file_info['relative_path']} - {str(e)}"
                self.update_status(error_msg)
                
                with QMutexLocker(self.stats_mutex):
                    self.failed_files += 1
                
                return {
                    'success': False,
                    'error': str(e),
                    'file_info': file_info
                }
        
        # Utiliser ThreadPoolExecutor pour le parallélisme
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_file = {
                executor.submit(upload_single_file, file_info): file_info
                for file_info in files
            }
            
            for future in as_completed(future_to_file):
                if self.is_operation_cancelled():
                    break
                
                result = future.result()
                self.file_results.append(result)
                
                if not result['success'] and not result.get('cancelled', False):
                    self.failed_files_list.append(result)
    
    def _log_failed_files(self) -> None:
        """Log les fichiers qui ont échoué pour permettre le retry"""
        if self.failed_files_list:
            self.update_status("📋 Fichiers échoués:")
            for failed in self.failed_files_list[:5]:  # Limiter à 5 pour l'affichage
                file_info = failed['file_info']
                error = failed['error']
                self.update_status(f"   ❌ {file_info['relative_path']}: {error}")
            
            if len(self.failed_files_list) > 5:
                remaining = len(self.failed_files_list) - 5
                self.update_status(f"   ... et {remaining} autres fichiers échoués")
    
    def _format_size(self, size: int) -> str:
        """Formate la taille en bytes de manière lisible"""
        if size < 1024:
            return f"{size} B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        elif size < 1024 * 1024 * 1024:
            return f"{size / (1024 * 1024):.1f} MB"
        else:
            return f"{size / (1024 * 1024 * 1024):.1f} GB"
    
    def get_failed_files(self) -> List[Dict[str, Any]]:
        """Retourne la liste des fichiers qui ont échoué"""
        return self.failed_files_list
    
    def retry_failed_files(self) -> None:
        """Permet de réessayer les fichiers échoués (pour implémentation future)"""
        # Cette méthode pourrait être utilisée pour réessayer seulement les fichiers échoués
        pass


class FileDownloadThread(BaseOperationThread):
    """Thread amélioré pour le téléchargement de fichiers"""
    
    def __init__(self, drive_client: GoogleDriveClient, file_id: str,
                 file_name: str, local_dir: str, file_size: int = 0,
                 transfer_manager: Optional[TransferManager] = None):
        super().__init__(transfer_manager)
        self.drive_client = drive_client
        self.file_id = file_id
        self.file_name = file_name
        self.local_dir = local_dir
        self.file_size = file_size
        self.bytes_transferred = 0
    
    def create_transfer_entry(self) -> str:
        """Crée l'entrée de transfert pour le téléchargement"""
        return self.transfer_manager.add_transfer(
            TransferType.DOWNLOAD_FILE,
            f"Google Drive/{self.file_id}",
            self.local_dir,
            self.file_name,
            self.file_size
        )
    
    def execute_operation(self) -> str:
        """Exécute le téléchargement du fichier"""
        def progress_callback(progress: int) -> None:
            if self.is_operation_cancelled():
                return
            if self.file_size > 0:
                self.bytes_transferred = int((progress / 100.0) * self.file_size)
                self.update_progress(progress, self.bytes_transferred, self.file_size)
            else:
                self.update_progress(progress)
        
        try:
            self.update_status(f"📥 Téléchargement: {self.file_name}")
            
            file_path = self.drive_client.download_file(
                self.file_id,
                self.file_name,
                self.local_dir,
                progress_callback
            )
            
            if not self.is_operation_cancelled():
                self.update_status(f"✅ Téléchargé: {self.file_name}")
                return file_path
            else:
                return "Annulé"
                
        except Exception as e:
            error_msg = f"❌ Erreur téléchargement {self.file_name}: {str(e)}"
            self.update_status(error_msg)
            raise Exception(error_msg)

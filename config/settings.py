"""
Configuration globale de l'application
"""

import os
import time
from pathlib import Path

# Configuration de l'application
APP_NAME = "Google Drive Manager"
APP_VERSION = "2.0.0"

# Configuration Google Drive
SCOPES = [
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/drive.file'
]

# Taille des chunks pour l'upload (8MB)
UPLOAD_CHUNK_SIZE = 8 * 1024 * 1024

# Configuration des threads
MAX_CONCURRENT_UPLOADS = 3
MAX_CONCURRENT_DOWNLOADS = 2

# Configuration retry et timeouts
MAX_UPLOAD_RETRIES = 3
MAX_FOLDER_RETRIES = 2
SSL_RETRY_DELAY = 2  # secondes

# Chemins des fichiers de configuration
RESOURCES_DIR = Path(__file__).parent.parent / "resources"
CREDENTIALS_FILENAME = "credentials.json"
TOKEN_FILENAME = "token.pickle"

def get_credentials_path() -> str:
    """Retourne le chemin vers le fichier credentials.json"""
    return str(RESOURCES_DIR / CREDENTIALS_FILENAME)

def get_token_path() -> str:
    """Retourne le chemin vers le fichier token.pickle"""
    return str(RESOURCES_DIR / TOKEN_FILENAME)
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

# === Paramètres de la fenêtre principale ===
WINDOW_TITLE = "Google Drive Explorer"
WINDOW_WIDTH = 1200
WINDOW_HEIGHT = 800

# === Paramètres de l'UI ===
TOOLBAR_ICON_SIZE = 32  # taille des icônes de la toolbar en pixels
CACHE_CLEANUP_INTERVAL_MS = 10 * 60 * 1000  # 10 minutes en millisecondes


# Paramètres de la barre d'outils
TOOLBAR_ICON_SIZE = (24, 24)

# Extensions de fichiers et leurs émojis
FILE_EMOJIS = {
    'application/vnd.google-apps.document': '📝',
    'application/vnd.google-apps.spreadsheet': '📊',
    'application/vnd.google-apps.presentation': '📽️',
    'application/vnd.google-apps.form': '📋',
    'application/vnd.google-apps.drawing': '🎨',
    'application/pdf': '📕',
    'image/jpeg': '🖼️',
    'image/png': '🖼️',
    'image/gif': '🖼️',
    'text/plain': '📄',
    'text/html': '🌐',
    'application/zip': '📦',
    'video/mp4': '🎥',
    'video/': '🎥',
    'audio/mpeg': '🎵',
    'audio/': '🎵',
}

# Types de fichiers et leurs descriptions
FILE_TYPES = {
    'application/vnd.google-apps.document': '📝 Doc Google',
    'application/vnd.google-apps.spreadsheet': '📊 Sheets Google',
    'application/vnd.google-apps.presentation': '📽️ Slides Google',
    'application/vnd.google-apps.form': '📋 Form Google',
    'application/vnd.google-apps.drawing': '🎨 Drawing Google',
    'application/pdf': '📕 PDF',
    'image/jpeg': '🖼️ JPEG',
    'image/png': '🖼️ PNG',
    'image/gif': '🖼️ GIF',
    'text/plain': '📄 Texte',
    'text/html': '🌐 HTML',
    'application/zip': '📦 ZIP',
    'video/mp4': '🎥 MP4',
    'audio/mpeg': '🎵 MP3'
}



def get_credentials_path() -> str:
    """Retourne le chemin vers le fichier credentials.json"""
    return str(RESOURCES_DIR / CREDENTIALS_FILENAME)

def get_token_path() -> str:
    """Retourne le chemin vers le fichier token.pickle"""
    return str(RESOURCES_DIR / TOKEN_FILENAME)
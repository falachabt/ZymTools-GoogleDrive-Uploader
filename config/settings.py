"""
Configuration générale de l'application Google Drive Explorer
"""


import os
import sys

# Configuration de l'API Google Drive
SCOPES = ['https://www.googleapis.com/auth/drive']

# Paramètres de cache
CACHE_MAX_AGE_MINUTES = 10
CACHE_CLEANUP_INTERVAL_MS = 60000  # 1 minute

# Paramètres d'interface
WINDOW_TITLE = "ZymUpload"
APP_VERSION = "1.0.3"
WINDOW_WIDTH = 1400
WINDOW_HEIGHT = 900

# Tailles des chunks pour upload/download
UPLOAD_CHUNK_SIZE = 1024 * 1024  # 1MB
DOWNLOAD_CHUNK_SIZE = 1024 * 1024  # 1MB

# Paramètres d'upload par défaut
DEFAULT_NUM_WORKERS = 2
DEFAULT_FILES_PER_WORKER = 5
MIN_NUM_WORKERS = 1
MAX_NUM_WORKERS = 10
MIN_FILES_PER_WORKER = 1
MAX_FILES_PER_WORKER = 20

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

def get_resource_path(relative_path):
    """
    Obtient le chemin absolu vers une ressource,
    fonctionne pour le développement et PyInstaller
    """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def get_credentials_path():
    """Retourne le chemin vers le fichier credentials.json"""
    return get_resource_path('resources/credentials.json')

def get_token_path():
    """Retourne le chemin vers le fichier token.pickle"""
    return get_resource_path('resources/token.pickle')


def get_appIcon_path():
    """Retourne le chemin vers l'icône de l'application"""
    return get_resource_path('resources/assets/icons/icon.png')
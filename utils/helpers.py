"""
Fonctions utilitaires pour l'application Google Drive Explorer
"""

import os
from datetime import datetime
from typing import Optional

from config.settings import FILE_EMOJIS, FILE_TYPES


def format_file_size(size_bytes: int) -> str:
    """
    Formate la taille en bytes de façon lisible

    Args:
        size_bytes: Taille en bytes

    Returns:
        Taille formatée (ex: "1.5 MB")
    """
    if size_bytes == 0:
        return "0 B"

    size_names = ("B", "KB", "MB", "GB", "TB")
    i = 0
    size = float(size_bytes)

    while size >= 1024 and i < len(size_names) - 1:
        size /= 1024
        i += 1

    return f"{size:.2f} {size_names[i]}"


def get_file_emoji(mime_type: str) -> str:
    """
    Retourne l'émoji approprié pour le type de fichier

    Args:
        mime_type: Type MIME du fichier

    Returns:
        Émoji correspondant au type de fichier
    """
    for mime_key, emoji in FILE_EMOJIS.items():
        if mime_type.startswith(mime_key):
            return emoji
    return '📄'


def get_file_type_description(mime_type: str) -> str:
    """
    Retourne la description du type de fichier

    Args:
        mime_type: Type MIME du fichier

    Returns:
        Description du type de fichier
    """
    return FILE_TYPES.get(mime_type, f"📄 {mime_type.split('/')[-1].upper()}")


def format_date(date_input) -> str:
    """
    Formate une date pour l'affichage

    Args:
        date_input: Date à formater (timestamp ou string)

    Returns:
        Date formatée
    """
    if not date_input:
        return ""

    try:
        if isinstance(date_input, str):
            # Format Google Drive: "2023-12-25T10:30:45.123Z"
            date_obj = datetime.strptime(date_input, "%Y-%m-%dT%H:%M:%S.%fZ")
            return date_obj.strftime("%Y-%m-%d %H:%M")
        elif isinstance(date_input, (int, float)):
            # Timestamp Unix
            date_obj = datetime.fromtimestamp(date_input)
            return date_obj.strftime("%Y-%m-%d %H:%M")
        else:
            return str(date_input)
    except Exception:
        return str(date_input)


def is_image_file(file_name: str) -> bool:
    """
    Vérifie si un fichier est une image

    Args:
        file_name: Nom du fichier

    Returns:
        True si c'est une image, False sinon
    """
    image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg', '.webp', '.ico'}
    return os.path.splitext(file_name.lower())[1] in image_extensions


def is_document_file(file_name: str) -> bool:
    """
    Vérifie si un fichier est un document

    Args:
        file_name: Nom du fichier

    Returns:
        True si c'est un document, False sinon
    """
    document_extensions = {'.doc', '.docx', '.pdf', '.txt', '.rtf', '.odt'}
    return os.path.splitext(file_name.lower())[1] in document_extensions


def is_audio_file(file_name: str) -> bool:
    """
    Vérifie si un fichier est un fichier audio

    Args:
        file_name: Nom du fichier

    Returns:
        True si c'est un fichier audio, False sinon
    """
    audio_extensions = {'.mp3', '.wav', '.flac', '.aac', '.ogg', '.m4a', '.wma'}
    return os.path.splitext(file_name.lower())[1] in audio_extensions


def is_video_file(file_name: str) -> bool:
    """
    Vérifie si un fichier est une vidéo

    Args:
        file_name: Nom du fichier

    Returns:
        True si c'est une vidéo, False sinon
    """
    video_extensions = {'.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v'}
    return os.path.splitext(file_name.lower())[1] in video_extensions


def is_archive_file(file_name: str) -> bool:
    """
    Vérifie si un fichier est une archive

    Args:
        file_name: Nom du fichier

    Returns:
        True si c'est une archive, False sinon
    """
    archive_extensions = {'.zip', '.rar', '.7z', '.tar', '.gz', '.bz2', '.xz'}
    return os.path.splitext(file_name.lower())[1] in archive_extensions


def sanitize_filename(filename: str) -> str:
    """
    Nettoie un nom de fichier pour qu'il soit valide sur le système de fichiers

    Args:
        filename: Nom de fichier original

    Returns:
        Nom de fichier nettoyé
    """
    # Caractères interdits sur Windows et autres systèmes
    forbidden_chars = '<>:"/\\|?*'

    # Remplacer les caractères interdits par des underscores
    for char in forbidden_chars:
        filename = filename.replace(char, '_')

    # Supprimer les espaces en début/fin
    filename = filename.strip()

    # Éviter les noms réservés sur Windows
    reserved_names = {
        'CON', 'PRN', 'AUX', 'NUL',
        'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
        'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9'
    }

    base_name = os.path.splitext(filename)[0].upper()
    if base_name in reserved_names:
        filename = f"_{filename}"

    return filename


def get_file_extension(file_name: str) -> str:
    """
    Récupère l'extension d'un fichier

    Args:
        file_name: Nom du fichier

    Returns:
        Extension du fichier (sans le point)
    """
    ext = os.path.splitext(file_name)[1]
    return ext[1:].upper() if ext else ""


def validate_path(path: str) -> bool:
    """
    Valide qu'un chemin existe et est accessible

    Args:
        path: Chemin à valider

    Returns:
        True si le chemin est valide, False sinon
    """
    try:
        return os.path.exists(path) and os.path.isdir(path)
    except Exception:
        return False


def create_directory_if_not_exists(path: str) -> bool:
    """
    Crée un dossier s'il n'existe pas

    Args:
        path: Chemin du dossier à créer

    Returns:
        True si créé avec succès ou existait déjà, False sinon
    """
    try:
        os.makedirs(path, exist_ok=True)
        return True
    except Exception:
        return False


def get_directory_size(path: str) -> int:
    """
    Calcule la taille totale d'un dossier

    Args:
        path: Chemin du dossier

    Returns:
        Taille totale en bytes
    """
    total_size = 0
    try:
        for dirpath, dirnames, filenames in os.walk(path):
            for filename in filenames:
                file_path = os.path.join(dirpath, filename)
                try:
                    total_size += os.path.getsize(file_path)
                except (OSError, IOError):
                    pass
    except Exception:
        pass
    return total_size


def count_files_in_directory(path: str) -> dict:
    """
    Compte les fichiers et dossiers dans un répertoire

    Args:
        path: Chemin du dossier

    Returns:
        Dictionnaire avec le nombre de fichiers et dossiers
    """
    file_count = 0
    dir_count = 0

    try:
        for item in os.listdir(path):
            item_path = os.path.join(path, item)
            if os.path.isfile(item_path):
                file_count += 1
            elif os.path.isdir(item_path):
                dir_count += 1
    except Exception:
        pass

    return {
        'files': file_count,
        'directories': dir_count,
        'total': file_count + dir_count
    }
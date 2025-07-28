# google_drive_utils.py
def already_exists_in_folder(drive_client, parent_id, name, mime_type=None, size=None):
    """
    Vérifie si un fichier/dossier avec le même nom, type MIME et taille existe dans le dossier cible.
    Les critères sont intégrés dans la fonction.
    """
    files = drive_client.list_files(parent_id)
    for f in files:
        if f['name'] == name:
            if mime_type is not None and f.get('mimeType') != mime_type:
                continue
            if size is not None and str(f.get('size')) != str(size):
                continue
            return True
    return False
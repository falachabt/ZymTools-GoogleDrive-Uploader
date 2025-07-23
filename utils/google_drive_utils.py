# google_drive_utils.py
def already_exists_in_folder(drive_client, parent_id, name):
    """Vérifie si un fichier/dossier du même nom et type existe dans le dossier cible."""
    files = drive_client.list_files(parent_id)
    for f in files:
        if f['name'] == name:
            return True
    return False
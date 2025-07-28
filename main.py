"""
Point d'entrée principal de l'application Google Drive Explorer
"""

import sys
import traceback
import logging
from PyQt5.QtWidgets import QApplication, QMessageBox

from config.styles import apply_dark_theme, get_application_stylesheet
from views.main_window import DriveExplorerMainWindow

# Redirection simple de sys.stdout et sys.stderr vers debug.log (sans passer par logging)
class LoggerWriter:
    def __init__(self, filename):
        self.terminal = sys.__stdout__
        self.log = open(filename, "a", encoding="utf-8")
    def write(self, message):
        if self.terminal:
            self.terminal.write(message)
        if self.log:
            self.log.write(message)
            self.log.flush()
    def flush(self):
        if self.terminal:
            self.terminal.flush()
        if self.log:
            self.log.flush()

sys.stdout = LoggerWriter("debug.log")
sys.stderr = LoggerWriter("debug.log")

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.__stdout__),  # Utiliser sys.__stdout__ pour éviter la boucle
        logging.FileHandler('debug.log', encoding='utf-8')
    ]
)

def setup_application():
    """Configure l'application Qt"""
    app = QApplication(sys.argv)

    # Appliquer le thème sombre
    apply_dark_theme(app)

    # Appliquer les styles CSS
    app.setStyleSheet(get_application_stylesheet())

    return app

def show_error_dialog(error_message: str, details: str = None):
    """Affiche une boîte de dialogue d'erreur critique"""
    error_box = QMessageBox()
    error_box.setIcon(QMessageBox.Critical)
    error_box.setWindowTitle("❌ Erreur critique")
    error_box.setText("Une erreur critique s'est produite:")
    error_box.setInformativeText(error_message)

    if details:
        error_box.setDetailedText(details)

    # Ajouter des conseils de dépannage
    troubleshooting = (
        "🔍 Vérifiez que vous avez:\n"
        "1. 📄 Le fichier credentials.json dans le dossier resources/\n"
        "2. 📦 Les bibliothèques Python nécessaires installées\n"
        "3. 🌐 Une connexion Internet active\n\n"
        "💡 Consultez le README.md pour plus d'aide."
    )
    error_box.setInformativeText(f"{error_message}\n\n{troubleshooting}")

    error_box.exec_()



def main():
    """Fonction principale de l'application"""
    try:
        # Créer l'application Qt
        app = setup_application()

        # Créer et afficher la fenêtre principale
        main_window = DriveExplorerMainWindow()
        main_window.show()

        # Message de bienvenue
        main_window.status_bar.showMessage(
            "🚀 Bienvenue dans ZymTools Google Drive Explorer",
            5000
        )

        # Lancer l'application
        return app.exec_()

    except ImportError as e:
        # Erreur d'import - probablement une dépendance manquante
        error_msg = f"Module manquant: {str(e)}"
        details = (
            "Il semble qu'une bibliothèque Python requise soit manquante.\n"
            "Installez les dépendances avec:\n"
            "pip install -r requirements.txt"
        )

        if 'PyQt5' in str(e):
            logging.error("PyQt5 n'est pas installé. Installez-le avec: pip install PyQt5")
        elif 'google' in str(e):
            logging.error("Google API Client n'est pas installé. Installez-le avec: pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib")
        else:
            logging.error(f"Erreur d'import: {str(e)}")

        # Essayer d'afficher une boîte de dialogue si possible
        try:
            app = QApplication(sys.argv) if not QApplication.instance() else QApplication.instance()
            show_error_dialog(error_msg, details)
        except:
            pass

        return 1

    except FileNotFoundError as e:
        # Fichier manquant (probablement credentials.json)
        error_msg = f"Fichier manquant: {str(e)}"
        details = (
            "Le fichier credentials.json est probablement manquant.\n"
            "1. Créez un projet Google Cloud Console\n"
            "2. Activez l'API Google Drive\n"
            "3. Téléchargez le fichier credentials.json\n"
            "4. Placez-le dans le dossier resources/"
        )

        try:
            app = QApplication(sys.argv) if not QApplication.instance() else QApplication.instance()
            show_error_dialog(error_msg, details)
        except:
            logging.error(f"{error_msg}")
            logging.error(details)

        return 1

    except Exception as e:
        # Autres erreurs
        error_msg = f"Erreur inattendue: {str(e)}"
        details = traceback.format_exc()

        try:
            app = QApplication(sys.argv) if not QApplication.instance() else QApplication.instance()
            show_error_dialog(error_msg, details)
        except:
            logging.error(f"{error_msg}")
            logging.error(f"Détails:\n{details}")

        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)

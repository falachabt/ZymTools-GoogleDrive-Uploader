# 🚀 Google Drive Explorer 

Une application moderne et élégante pour explorer et gérer vos fichiers Google Drive avec une interface intuitive et des fonctionnalités avancées.

## ✨ Fonctionnalités

### 🎯 Fonctionnalités principales
- **Navigation bifurcée** : Fichiers locaux et Google Drive côte à côte
- **Interface moderne** : Thème sombre élégant avec émojis
- **Cache intelligent** : Améliore les performances avec mise en cache
- **Threading avancé** : Opérations non-bloquantes en arrière-plan
- **Drag & Drop** : Glissez-déposez des fichiers entre local et cloud
- **Recherche avancée** : Trouvez rapidement vos fichiers dans Google Drive

### 🔧 Opérations supportées
- ⬆️ Upload de fichiers et dossiers complets
- ⬇️ Téléchargement de fichiers
- 📁 Création et gestion de dossiers
- ✏️ Renommage de fichiers/dossiers
- 🗑️ Suppression (corbeille et définitive)
- 🔍 Recherche dans Google Drive
- 🏢 Support des Shared Drives d'entreprise

### 🎨 Interface utilisateur
- **Thème sombre moderne** avec dégradés
- **Émojis contextuels** pour les types de fichiers
- **Barres de progression** pour les opérations longues
- **Messages de statut** informatifs
- **Raccourcis clavier** pour une utilisation rapide

## 📋 Prérequis

### Système
- Python 3.7 ou plus récent
- Système d'exploitation : Windows, macOS, ou Linux

### API Google Drive
- Compte Google
- Projet Google Cloud Console
- API Google Drive activée
- Fichier `credentials.json`

## 🛠️ Installation

### 1. Cloner le projet
```bash
git clone https://github.com/votre-username/google-drive-explorer.git
cd google-drive-explorer
```

### 2. Installer les dépendances
```bash
pip install -r requirements.txt
```

### 3. Configuration Google Drive API

#### Étape 1 : Créer un projet Google Cloud
1. Allez sur [Google Cloud Console](https://console.cloud.google.com/)
2. Créez un nouveau projet ou sélectionnez un projet existant
3. Activez l'API Google Drive

#### Étape 2 : Créer les credentials
1. Dans Google Cloud Console, allez dans "APIs & Services" > "Credentials"
2. Cliquez sur "Create Credentials" > "OAuth 2.0 Client ID"
3. Choisissez "Desktop Application"
4. Téléchargez le fichier JSON

#### Étape 3 : Configurer l'application
1. Renommez le fichier téléchargé en `credentials.json`
2. Placez-le dans le dossier `resources/` du projet
```
google_drive_explorer/
├── resources/
│   └── credentials.json  ← Placez votre fichier ici
```

### 4. Lancer l'application
```bash
python main.py
```

## 🏗️ Architecture du projet

```
google_drive_explorer/
├── main.py                      # Point d'entrée principal
├── requirements.txt             # Dépendances Python
├── README.md                   # Documentation
├── config/
│   ├── __init__.py
│   ├── settings.py             # Configuration générale
│   └── styles.py               # Styles CSS et thèmes
├── core/
│   ├── __init__.py
│   ├── cache_manager.py        # Gestionnaire de cache
│   └── google_drive_client.py  # Client API Google Drive
├── threads/
│   ├── __init__.py
│   ├── file_load_threads.py    # Threads de chargement
│   └── transfer_threads.py     # Threads d'upload/download
├── models/
│   ├── __init__.py
│   └── file_models.py          # Modèles de données
├── views/
│   ├── __init__.py
│   ├── tree_views.py           # Vues d'arbre personnalisées
│   ├── dialogs.py              # Boîtes de dialogue
│   └── main_window.py          # Fenêtre principale
├── utils/
│   ├── __init__.py
│   └── helpers.py              # Fonctions utilitaires
└── resources/
    ├── credentials.json        # Clés API Google (à créer)
    └── token.pickle           # Token d'authentification (généré)
```

## 🎮 Utilisation

### Navigation
- **F5** : Actualiser les vues
- **F2** : Renommer l'élément sélectionné
- **Delete** : Supprimer l'élément sélectionné
- **Ctrl+F** : Rechercher dans Google Drive

### Opérations de fichiers
1. **Upload vers Google Drive** : 
   - Glissez-déposez depuis l'explorateur local
   - Ou clic droit > "Uploader vers Google Drive"

2. **Téléchargement depuis Google Drive** :
   - Clic droit sur un fichier > "Télécharger"
   - Choisissez le dossier de destination

3. **Gestion des dossiers** :
   - Bouton "Nouveau dossier" dans la barre d'outils
   - Double-clic pour naviguer
   - Bouton "Retour" pour remonter

### Recherche
1. Cliquez sur l'icône de recherche ou appuyez sur Ctrl+F
2. Tapez votre requête
3. Les résultats s'affichent dans la vue Google Drive
4. Cliquez sur "Retour à la navigation" pour revenir

## ⚙️ Configuration

### Paramètres du cache
Modifiez `config/settings.py` pour ajuster :
- `CACHE_MAX_AGE_MINUTES` : Durée de vie du cache (défaut: 10 min)
- `CACHE_CLEANUP_INTERVAL_MS` : Fréquence de nettoyage (défaut: 60 sec)

### Paramètres d'interface
- `WINDOW_WIDTH` / `WINDOW_HEIGHT` : Taille de la fenêtre
- `UPLOAD_CHUNK_SIZE` : Taille des chunks d'upload (défaut: 1MB)

### Personnalisation des émojis
Modifiez les dictionnaires `FILE_EMOJIS` et `FILE_TYPES` dans `config/settings.py`

## 🐛 Dépannage

### Problèmes courants

#### "Module manquant"
```bash
pip install -r requirements.txt
```

#### "credentials.json introuvable"
- Vérifiez que le fichier est dans `resources/credentials.json`
- Recréez le fichier depuis Google Cloud Console

#### "Erreur d'authentification"
- Supprimez le fichier `resources/token.pickle`
- Relancez l'application pour re-authentifier

#### "Impossible de se connecter à Google Drive"
- Vérifiez votre connexion Internet
- Vérifiez que l'API Google Drive est activée
- Vérifiez les permissions du projet Google Cloud

### Debug avancé
Activez les logs détaillés en modifiant `main.py` :
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## 🤝 Contribution

Les contributions sont les bienvenues ! Pour contribuer :

1. Forkez le projet
2. Créez une branche feature (`git checkout -b feature/AmazingFeature`)
3. Committez vos changements (`git commit -m 'Add some AmazingFeature'`)
4. Poussez vers la branche (`git push origin feature/AmazingFeature`)
5. Ouvrez une Pull Request

### Standards de code
- Utilisez les type hints Python
- Documentez les fonctions avec des docstrings
- Suivez PEP 8 pour le style de code
- Ajoutez des tests pour les nouvelles fonctionnalités

## 📄 Licence

Ce projet est sous licence MIT. Voir le fichier `LICENSE` pour plus de détails.

## 🙏 Remerciements

- Google pour l'API Google Drive
- L'équipe PyQt5 pour le framework GUI
- La communauté Python pour les excellentes bibliothèques

## 📞 Support

- 📧 Email : **bennytenezeu@gmail.com**
- 🐛 Issues : [GitHub Issues](https://github.com/votre-username/google-drive-explorer/issues)
- 📖 Wiki : [GitHub Wiki](https://github.com/votre-username/google-drive-explorer/wiki)

---

**Fait avec ❤️ par ZymTools**

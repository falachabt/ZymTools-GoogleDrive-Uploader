@echo off
REM ====== Configuration ======

REM Nom de ton script Python
set SCRIPT_NAME=main.py

REM Chemin vers l'exécutable Python d'Anaconda
set PYTHON_EXE=C:\ProgramData\Anaconda3\python.exe

REM Chemin vers les plugins Qt de PyQt5
set QT_PLUGIN_PATH=C:\ProgramData\Anaconda3\Library\plugins

REM Chemin vers les DLLs d'Anaconda
set ANACONDA_DLLS=C:\ProgramData\Anaconda3\DLLs
set ANACONDA_LIBS=C:\ProgramData\Anaconda3\Library\bin

REM ====== Nettoyage ancien build ======
echo 🔄 Nettoyage des dossiers de build précédents...
rmdir /s /q build >nul 2>&1
rmdir /s /q dist >nul 2>&1
del /q *.spec >nul 2>&1

REM ====== Compilation avec PyInstaller ======
echo 🚀 Compilation de l'application avec PyInstaller...
"%PYTHON_EXE%" -m PyInstaller --onedir --windowed ^
  --paths="%ANACONDA_DLLS%" ^
  --paths="%ANACONDA_LIBS%" ^
  --hidden-import=googleapiclient.discovery ^
  --hidden-import=googleapiclient.http ^
  --hidden-import=google.auth.transport.requests ^
  --hidden-import=google.oauth2.credentials ^
  --hidden-import=charset_normalizer.md__mypyc ^
  --hidden-import=sip ^
  --collect-all PyQt5 ^
  --add-data "credentials.json;." ^
  --add-data "%QT_PLUGIN_PATH%;PyQt5/Qt/plugins" ^
  --add-binary "%ANACONDA_DLLS%\pyexpat.pyd;." ^
  --add-binary "%ANACONDA_LIBS%\libexpat.dll;." ^
  --add-binary "%ANACONDA_DLLS%\_hashlib.pyd;." ^
  --add-binary "%ANACONDA_DLLS%\_lzma.pyd;." ^
  --add-binary "%ANACONDA_DLLS%\_bz2.pyd;." ^
  --add-binary "%ANACONDA_DLLS%\_ssl.pyd;." ^
  --add-binary "%ANACONDA_DLLS%\_ctypes.pyd;." ^
  %SCRIPT_NAME%

REM ====== Copier les DLLs manquantes directement dans le répertoire dist ======
echo 🔄 Copie des bibliothèques manquantes...
if not exist "dist\main" mkdir "dist\main"
copy "%ANACONDA_LIBS%\libexpat.dll" "dist\main\" >nul 2>&1
copy "%ANACONDA_DLLS%\*.dll" "dist\main\" >nul 2>&1
copy "%ANACONDA_LIBS%\*.dll" "dist\main\" >nul 2>&1


REM ====== Création d'un raccourci sur le bureau ======
echo 🔗 Création du raccourci sur le bureau...

set SHORTCUT_NAME=ZymoSync.lnk
set EXE_PATH=%CD%\dist\main\main.exe
set DESKTOP=%USERPROFILE%\Desktop

REM Écrire un script VBS temporaire pour créer le raccourci
echo Set oWS = WScript.CreateObject("WScript.Shell") > create_shortcut.vbs
echo sLinkFile = "%DESKTOP%\%SHORTCUT_NAME%" >> create_shortcut.vbs
echo Set oLink = oWS.CreateShortcut(sLinkFile) >> create_shortcut.vbs
echo oLink.TargetPath = "%EXE_PATH%" >> create_shortcut.vbs
echo oLink.WorkingDirectory = "%CD%\dist\main" >> create_shortcut.vbs
echo oLink.WindowStyle = 1 >> create_shortcut.vbs
echo oLink.Save >> create_shortcut.vbs

REM Exécuter le script VBS
cscript //nologo create_shortcut.vbs

REM Supprimer le script temporaire
del create_shortcut.vbs >nul 2>&1

echo ✅ Raccourci créé sur le bureau.


REM ====== Résultat ======
echo.
echo ✅ Compilation terminée !
echo 📁 L'exécutable est disponible dans le dossier "dist\main"
pause

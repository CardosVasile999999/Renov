@echo off
REM Construieste Renov.exe pentru distributie (ruleaza din folderul proiectului)
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Creeaza mai intai mediul virtual: python -m venv .venv
    exit /b 1
)
call ".venv\Scripts\activate.bat"
pip install -r requirements.txt
pyinstaller --noconfirm renov.spec
echo.
echo Gata: dist\Renov.exe
echo Incarca dist\Renov.exe pe GitHub Release ca asset pentru tag-ul corespunzator.

@echo off
REM Build Renov.exe — combina comanda ta cu fix-urile din renov.spec
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Creeaza mai intai mediul virtual: python -m venv .venv
    exit /b 1
)
call ".venv\Scripts\activate.bat"
pip install -r requirements.txt
pyinstaller --noconfirm --clean renov.spec
echo.
echo Gata: dist\Renov.exe
echo Incarca dist\Renov.exe pe GitHub Release.

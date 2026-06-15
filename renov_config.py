"""
Căi globale pentru Renov: date utilizator, instalare și update .exe.

Datele (SQLite) stau în AppData — nu în folderul aplicației — ca update-urile
să nu poată suprascrie devis-urile și facturile.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from version import __version__

# --- Identitate aplicație ---
APP_NAME = "Dan Renov"
APP_SLUG = "DanRenov"

# --- GitHub / update-uri (.exe) ---
GITHUB_USER = "CardosVasile999999"
GITHUB_REPO = "Renov"
UPDATE_MANIFEST_URL = (
    f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/main/update.json"
)

# Numele fișierului .exe la distribuție (trebuie să coincidă cu Release-ul de pe GitHub)
EXE_FILENAME = "Renov.exe"
UPDATE_STAGING_FILENAME = "Renov-new.exe"
UPDATE_BACKUP_FILENAME = "Renov.exe.bak"

# Versiunea curentă (re-export pentru import unic din renov_config)
APP_VERSION = __version__

# --- Căi calculate la import ---
INSTALL_DIR: Path = (
    Path(sys.executable).resolve().parent
    if getattr(sys, "frozen", False)
    else Path(__file__).resolve().parent
)

if sys.platform == "win32":
    _local_app_data = os.environ.get("LOCALAPPDATA")
    USER_DATA_DIR: Path = (
        Path(_local_app_data) / APP_SLUG
        if _local_app_data
        else Path.home() / "AppData" / "Local" / APP_SLUG
    )
else:
    USER_DATA_DIR = Path.home() / ".local" / "share" / APP_SLUG

DB_FILENAME = "devis.sqlite3"
DB_PATH: Path = USER_DATA_DIR / DB_FILENAME
EXE_PATH: Path = INSTALL_DIR / EXE_FILENAME

# Locația veche (în proiect) — doar pentru migrare la prima pornire
LEGACY_DB_PATH: Path = Path(__file__).resolve().parent / "data" / DB_FILENAME


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def migrate_legacy_database() -> None:
    """Copiază baza veche din proiect în AppData dacă utilizatorul face upgrade."""
    if not LEGACY_DB_PATH.is_file():
        return
    if DB_PATH.is_file():
        return
    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(LEGACY_DB_PATH, DB_PATH)

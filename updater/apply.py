"""Descărcare și aplicare update .exe (Windows)."""
from __future__ import annotations

import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

from renov_config import (
    EXE_FILENAME,
    EXE_PATH,
    INSTALL_DIR,
    UPDATE_BACKUP_FILENAME,
    UPDATE_STAGING_FILENAME,
)
from updater.dialog import show_error, show_info


def download_new_exe(url: str, dest: Path, timeout_s: float = 120.0) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "DanRenov-Updater"})
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            data = resp.read()
        dest.write_bytes(data)
        return dest.is_file() and dest.stat().st_size > 0
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def _batch_script(install_dir: Path) -> str:
    exe = EXE_FILENAME
    staging = UPDATE_STAGING_FILENAME
    backup = UPDATE_BACKUP_FILENAME
    return f"""@echo off
setlocal
cd /d "{install_dir}"
timeout /t 2 /nobreak >nul
:wait
tasklist /FI "IMAGENAME eq {exe}" 2>nul | find /I "{exe}" >nul
if not errorlevel 1 (
    timeout /t 1 /nobreak >nul
    goto wait
)
if exist "{backup}" del /f /q "{backup}"
if exist "{exe}" move /Y "{exe}" "{backup}"
move /Y "{staging}" "{exe}"
start "" "{install_dir}\\{exe}"
del "%~f0"
"""


def apply_exe_update(download_url: str) -> bool:
    """
    Descarcă noul .exe și lansează scriptul care îl înlocuiește după închiderea app-ului.
    Returnează True dacă procesul curent trebuie să se oprească.
    """
    staging = INSTALL_DIR / UPDATE_STAGING_FILENAME
    if staging.exists():
        try:
            staging.unlink()
        except OSError:
            pass

    show_info(
        "Dan Renov — actualizare",
        "Se descarcă versiunea nouă...\nAplicația se va reporni automat.",
    )

    if not download_new_exe(download_url, staging):
        show_error(
            "Dan Renov — actualizare eșuată",
            "Nu s-a putut descărca fișierul de actualizare.\n"
            "Verifică conexiunea la internet și încearcă din nou.",
        )
        return False

    batch_path = INSTALL_DIR / "_renov_apply_update.bat"
    try:
        batch_path.write_text(_batch_script(INSTALL_DIR), encoding="utf-8")
    except OSError:
        show_error(
            "Dan Renov — actualizare eșuată",
            f"Nu s-a putut pregăti actualizarea în:\n{INSTALL_DIR}",
        )
        return False

    try:
        subprocess.Popen(
            ["cmd", "/c", str(batch_path)],
            cwd=str(INSTALL_DIR),
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
            close_fds=True,
        )
    except OSError:
        show_error("Dan Renov — actualizare eșuată", "Nu s-a putut lansa scriptul de actualizare.")
        return False

    return True

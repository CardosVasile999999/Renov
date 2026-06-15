"""Flux complet: verifică GitHub → notificare obligatorie → descarcă .exe nou."""
from __future__ import annotations

import os
import sys

from renov_config import APP_VERSION, is_frozen
from updater.apply import apply_exe_update
from updater.check import fetch_manifest, must_update
from updater.dialog import notify_mandatory_update, show_error


def run_update_check() -> bool:
    """
    Verifică update.json pe GitHub.
    Returnează True dacă procesul curent trebuie să se închidă (update sau blocare).
    """
    if os.environ.get("RENOV_SKIP_UPDATE"):
        return False

    if not is_frozen() and not os.environ.get("RENOV_CHECK_UPDATE"):
        return False

    if sys.platform != "win32":
        return False

    manifest = fetch_manifest()
    if manifest is None:
        return False

    if not must_update(manifest):
        return False

    notify_mandatory_update(APP_VERSION, manifest.version, manifest.release_notes)

    if apply_exe_update(manifest.download_url):
        return True

    show_error(
        "Dan Renov — actualizare obligatorie eșuată",
        "Nu s-a putut instala versiunea nouă.\n"
        "Verifică conexiunea la internet și repornește aplicația.",
    )
    return True

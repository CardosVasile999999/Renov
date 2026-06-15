"""Dialog nativ Windows pentru confirmarea update-ului."""
from __future__ import annotations

import ctypes


def notify_mandatory_update(current: str, remote: str, release_notes: str) -> None:
    """Informează utilizatorul că actualizarea este obligatorie (fără opțiune de refuz)."""
    notes = (release_notes or "").strip()
    if len(notes) > 400:
        notes = notes[:397] + "..."

    body = (
        f"Versiunea instalată: {current}\n"
        f"Versiune necesară: {remote}\n\n"
    )
    if notes:
        body += f"Noutăți:\n{notes}\n\n"
    body += (
        "Actualizarea este obligatorie.\n"
        "Aplicația se va închide și se va instala versiunea nouă automat."
    )
    ctypes.windll.user32.MessageBoxW(
        0,
        body,
        "Dan Renov — actualizare obligatorie",
        0x40,  # MB_ICONINFORMATION + MB_OK
    )


def show_info(title: str, message: str) -> None:
    ctypes.windll.user32.MessageBoxW(0, message, title, 0x40)


def show_error(title: str, message: str) -> None:
    ctypes.windll.user32.MessageBoxW(0, message, title, 0x10)

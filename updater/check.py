"""Verificare versiune pe GitHub (update.json)."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from packaging.version import Version

from renov_config import APP_VERSION, UPDATE_MANIFEST_URL


@dataclass(frozen=True)
class UpdateInfo:
    version: str
    min_version: str
    download_url: str
    release_notes: str


def fetch_manifest(timeout_s: float = 8.0) -> UpdateInfo | None:
    req = urllib.request.Request(
        UPDATE_MANIFEST_URL,
        headers={"User-Agent": "DanRenov-Updater"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            raw = resp.read().decode("utf-8")
    except (urllib.error.URLError, TimeoutError, OSError):
        return None

    try:
        data: dict[str, Any] = json.loads(raw)
        version = str(data.get("version", "")).strip()
        download_url = str(data.get("download_url", "")).strip()
        if not version or not download_url:
            return None
        return UpdateInfo(
            version=version,
            min_version=str(data.get("min_version", version)).strip() or version,
            download_url=download_url,
            release_notes=str(data.get("release_notes", "")).strip(),
        )
    except (json.JSONDecodeError, TypeError, ValueError):
        return None


def must_update(remote: UpdateInfo) -> bool:
    """True dacă utilizatorul trebuie să actualizeze înainte de a folosi aplicația."""
    try:
        local = Version(APP_VERSION)
        return local < Version(remote.version) or local < Version(remote.min_version)
    except Exception:
        return False

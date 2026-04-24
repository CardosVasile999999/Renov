"""Fereastră desktop: UI identic cu variantele din HTML, afișat în fereastră (nu în Chrome).

Mod principal al aplicației: ``python app.py`` (deschide această fereastră).
Alternativ: ``python desktop.py``. Pentru PyInstaller folosește același punct de intrare ca în producție.

Dev în browser opțional: ``RENOV_DEV_BROWSER=1 python app.py`` (Windows PowerShell:
``$env:RENOV_DEV_BROWSER=1; python app.py``).
"""
from __future__ import annotations

import socket
import threading
import time
from pathlib import Path
from typing import Any

import webview
from werkzeug.serving import make_server

from app import app as flask_app


class DevisApi:
    """API expus în JS (doar în pywebview): salvare PDF prin dialog nativ Windows."""

    def save_devis_pdf(self, devis_num: str) -> dict[str, Any]:
        from db import get_devis
        from pdf_devis import build_pdf

        num = str(devis_num).strip()
        if not num:
            return {"ok": False, "error": "Număr devis lipsă."}
        d = get_devis(num)
        if not d:
            return {"ok": False, "error": "Devis negăsit."}
        pdf_bytes = build_pdf(d)
        wins = webview.windows
        if not wins:
            return {"ok": False, "error": "Fereastră indisponibilă."}
        paths = wins[0].create_file_dialog(
            webview.SAVE_DIALOG,
            save_filename=f"DEVIS_{num}.pdf",
            file_types=("PDF (*.pdf)",),
        )
        if paths is None:
            return {"ok": False, "error": "Anulat"}
        target = paths[0] if isinstance(paths, (list, tuple)) else paths
        if not target:
            return {"ok": False, "error": "Anulat"}
        Path(str(target)).write_bytes(pdf_bytes)
        return {"ok": True}


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _wait_port(host: str, port: int, timeout_s: float = 5.0) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.25):
                return
        except OSError:
            time.sleep(0.05)
    raise RuntimeError(f"Server did not become ready on {host}:{port}")


def main() -> None:
    webview.settings["ALLOW_DOWNLOADS"] = True

    port = _free_port()
    server = make_server("127.0.0.1", port, flask_app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        _wait_port("127.0.0.1", port)
        url = f"http://127.0.0.1:{port}/"
        webview.create_window(
            "RENVOV — Devis",
            url,
            js_api=DevisApi(),
            width=1280,
            height=840,
            min_size=(960, 640),
        )
        webview.start()
    finally:
        try:
            server.shutdown()
        except Exception:
            pass


if __name__ == "__main__":
    main()

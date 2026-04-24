from __future__ import annotations

import io
import json
import sqlite3
import zipfile

from flask import Flask, abort, jsonify, render_template, request, send_file

import db
from db import (
    DevisPayload,
    FacturePayload,
    delete_devis,
    delete_facture,
    get_devis,
    get_facture,
    get_many,
    insert_devis,
    insert_facture,
    list_devis,
    list_factures,
    parse_lignes_json,
    update_devis,
    update_facture,
)
from pdf_devis import build_pdf
from utils_fmt import normalize_devis_num, validate_date_ddmmyyyy

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 4 * 1024 * 1024


@app.route("/")
def index():
    q = request.args.get("q", type=str)
    rows = list_devis(q)
    return render_template("index.html", devis_list=rows, q=q or "")


@app.route("/factures")
def factures_index():
    q = request.args.get("q", type=str)
    rows = list_factures(q)
    return render_template("factures_index.html", factures_list=rows, q=q or "")


@app.route("/devis/nouveau")
def devis_new():
    return render_template("devis_form.html", devis=None, mode="create")


@app.route("/devis/<devis_num>/modifier")
def devis_edit(devis_num: str):
    d = get_devis(devis_num)
    if not d:
        abort(404)
    return render_template("devis_form.html", devis=d, mode="edit")


@app.route("/devis/<devis_num>")
def devis_view(devis_num: str):
    d = get_devis(devis_num)
    if not d:
        abort(404)
    return render_template("devis_view.html", devis=d)


@app.get("/api/devis/<devis_num>")
def api_devis(devis_num: str):
    d = get_devis(devis_num)
    if not d:
        return jsonify({"ok": False, "error": "Devis negăsit."}), 404
    return jsonify({"ok": True, "devis": d})


def _payload_from_form(form) -> DevisPayload:
    num = normalize_devis_num(form.get("devis_num", ""))
    raw_lignes = form.get("lignes_json", "[]")
    try:
        lignes = parse_lignes_json(raw_lignes)
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
        raise ValueError("Rândurile devisului nu sunt valide.") from e
    if not lignes:
        raise ValueError("Este obligatoriu cel puțin un rând în devis.")
    return DevisPayload(
        devis_num=num,
        destinataire_nom=form.get("destinataire_nom", "").strip(),
        destinataire_adresse=form.get("destinataire_adresse", "").strip(),
        destinataire_cp=(form.get("destinataire_cp", "") or "").strip() or None,
        destinataire_siret=(form.get("destinataire_siret", "") or "").strip() or None,
        destinataire_telephone=form.get("destinataire_telephone", "").strip(),
        infos_additionnelles=form.get("infos_additionnelles", "").strip() or None,
        date_devis=validate_date_ddmmyyyy(form.get("date_devis", "")),
        date_validite=validate_date_ddmmyyyy(form.get("date_validite", "")),
        include_bank_details=bool((form.get("include_bank_details") or "").strip()),
        lignes=lignes,
    )


def _facture_payload_from_form(form) -> FacturePayload:
    num = normalize_devis_num(form.get("facture_num", ""))
    raw_lignes = form.get("lignes_json", "[]")
    try:
        lignes = parse_lignes_json(raw_lignes)
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
        raise ValueError("Rândurile facturii nu sunt valide.") from e
    if not lignes:
        raise ValueError("Este obligatoriu cel puțin un rând în factură.")
    mode_paiement = (form.get("mode_paiement", "") or "").strip()
    if mode_paiement not in ("Virement", "Chèque", "Espèces"):
        raise ValueError("Mode de paiement invalid.")
    devis_src = (form.get("devis_num_source", "") or "").strip() or None
    return FacturePayload(
        facture_num=num,
        devis_num_source=devis_src,
        destinataire_nom=form.get("destinataire_nom", "").strip(),
        destinataire_adresse=form.get("destinataire_adresse", "").strip(),
        destinataire_cp=(form.get("destinataire_cp", "") or "").strip() or None,
        destinataire_siret=(form.get("destinataire_siret", "") or "").strip() or None,
        destinataire_telephone=form.get("destinataire_telephone", "").strip(),
        infos_additionnelles=form.get("infos_additionnelles", "").strip() or None,
        date_facture=validate_date_ddmmyyyy(form.get("date_facture", "")),
        date_validite=validate_date_ddmmyyyy(form.get("date_validite", "")),
        mode_paiement=mode_paiement,
        is_acompte=bool((form.get("is_acompte") or "").strip()),
        include_bank_details=bool((form.get("include_bank_details") or "").strip()),
        lignes=lignes,
    )


@app.post("/devis")
def devis_create():
    try:
        payload = _payload_from_form(request.form)
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    if not payload.destinataire_nom:
        return jsonify({"ok": False, "error": "Numele destinatarului este obligatoriu."}), 400
    if get_devis(payload.devis_num):
        return jsonify({"ok": False, "error": "Acest număr de devis există deja."}), 400
    try:
        insert_devis(payload)
    except sqlite3.IntegrityError:
        return jsonify({"ok": False, "error": "Acest număr de devis există deja."}), 400
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
    return jsonify({"ok": True, "devis_num": payload.devis_num})


@app.route("/factures/nouvelle")
def facture_new():
    # listă pentru dropdown (copiere din devis)
    devis_rows = list_devis(None)
    return render_template("facture_form.html", facture=None, mode="create", devis_list=devis_rows)


@app.route("/factures/<facture_num>/modifier")
def facture_edit(facture_num: str):
    d = get_facture(facture_num)
    if not d:
        abort(404)
    devis_rows = list_devis(None)
    return render_template("facture_form.html", facture=d, mode="edit", devis_list=devis_rows)


@app.route("/factures/<facture_num>")
def facture_view(facture_num: str):
    d = get_facture(facture_num)
    if not d:
        abort(404)
    return render_template("facture_view.html", facture=d)


@app.post("/factures")
def facture_create():
    try:
        payload = _facture_payload_from_form(request.form)
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    if not payload.destinataire_nom:
        return jsonify({"ok": False, "error": "Numele destinatarului este obligatoriu."}), 400
    if get_facture(payload.facture_num):
        return jsonify({"ok": False, "error": "Acest număr de factură există deja."}), 400
    try:
        insert_facture(payload)
    except sqlite3.IntegrityError:
        return jsonify({"ok": False, "error": "Acest număr de factură există deja."}), 400
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
    return jsonify({"ok": True, "facture_num": payload.facture_num})


@app.put("/factures/<facture_num>")
def facture_update(facture_num: str):
    try:
        payload = _facture_payload_from_form(request.form)
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    if payload.facture_num != facture_num:
        return jsonify({"ok": False, "error": "Numărul de factură nu poate fi modificat."}), 400
    if not update_facture(payload):
        return jsonify({"ok": False, "error": "Factură negăsită."}), 404
    return jsonify({"ok": True})


@app.delete("/factures/<facture_num>")
def facture_delete(facture_num: str):
    if not delete_facture(facture_num):
        return jsonify({"ok": False, "error": "Factură negăsită."}), 404
    return jsonify({"ok": True})


@app.put("/devis/<devis_num>")
def devis_update(devis_num: str):
    try:
        payload = _payload_from_form(request.form)
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    if payload.devis_num != devis_num:
        return jsonify({"ok": False, "error": "Numărul de devis nu poate fi modificat."}), 400
    if not update_devis(payload):
        return jsonify({"ok": False, "error": "Devis negăsit."}), 404
    return jsonify({"ok": True})


@app.delete("/devis/<devis_num>")
def devis_delete(devis_num: str):
    if not delete_devis(devis_num):
        return jsonify({"ok": False, "error": "Devis negăsit."}), 404
    return jsonify({"ok": True})


@app.get("/export/devis/<devis_num>.pdf")
def export_one_pdf(devis_num: str):
    d = get_devis(devis_num)
    if not d:
        abort(404)
    pdf = build_pdf(d)
    bio = io.BytesIO(pdf)
    bio.seek(0)
    return send_file(
        bio,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"DEVIS_{devis_num}.pdf",
    )


@app.get("/export/factures/<facture_num>.pdf")
def export_one_facture_pdf(facture_num: str):
    d = get_facture(facture_num)
    if not d:
        abort(404)
    pdf = build_pdf(d, kind="facture")
    bio = io.BytesIO(pdf)
    bio.seek(0)
    return send_file(
        bio,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"FACTURE_{facture_num}.pdf",
    )


@app.post("/export/factures.zip")
def export_factures_zip():
    raw = request.get_json(silent=True) or {}
    nums = raw.get("nums") or []
    if not isinstance(nums, list) or not nums:
        return jsonify({"ok": False, "error": "Nicio factură selectată."}), 400
    items = [get_facture(str(n)) for n in nums]
    items = [i for i in items if i]
    if not items:
        return jsonify({"ok": False, "error": "Nu s-au găsit facturi."}), 404
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for d in items:
            zf.writestr(f"FACTURE_{d['facture_num']}.pdf", build_pdf(d, kind="facture"))
    buf.seek(0)
    return send_file(buf, mimetype="application/zip", as_attachment=True, download_name="factures_export.zip")


@app.post("/export/devis.zip")
def export_zip():
    raw = request.get_json(silent=True) or {}
    nums = raw.get("nums") or []
    if not isinstance(nums, list) or not nums:
        return jsonify({"ok": False, "error": "Niciun devis selectat."}), 400
    items = get_many(str(n) for n in nums)
    if not items:
        return jsonify({"ok": False, "error": "Nu s-au găsit devisuri."}), 404
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for d in items:
            zf.writestr(f"DEVIS_{d['devis_num']}.pdf", build_pdf(d))
    buf.seek(0)
    return send_file(buf, mimetype="application/zip", as_attachment=True, download_name="devis_export.zip")


db.init_db()

if __name__ == "__main__":
    import os
    import socket
    import threading
    import time
    import webbrowser
    from werkzeug.serving import make_server

    def _free_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            return int(s.getsockname()[1])

    def _wait_port(host: str, port: int, timeout_s: float = 6.0) -> None:
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            try:
                with socket.create_connection((host, port), timeout=0.25):
                    return
            except OSError:
                time.sleep(0.05)
        raise RuntimeError(f"Server did not become ready on {host}:{port}")

    # Implicit: pornește server local și deschide în browser.
    # Mod desktop (pywebview) este opțional: setează RENOV_DESKTOP=1.
    if os.environ.get("RENOV_DESKTOP"):
        import importlib

        importlib.import_module("desktop").main()
    else:
        port = int(os.environ.get("PORT") or 0) or _free_port()
        server = make_server("127.0.0.1", port, app, threaded=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        _wait_port("127.0.0.1", port)
        url = f"http://127.0.0.1:{port}/"
        webbrowser.open(url)
        try:
            thread.join()
        finally:
            try:
                server.shutdown()
            except Exception:
                pass

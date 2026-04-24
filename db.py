"""SQLite persistence for DEVIS (quotes)."""
from __future__ import annotations

import json
import math
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Generator, Iterable

DB_PATH = Path(__file__).resolve().parent / "data" / "devis.sqlite3"


@contextmanager
def get_conn() -> Generator[sqlite3.Connection, None, None]:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _migrate_ligne_prix_unitaire_to_real(conn: sqlite3.Connection) -> None:
    """Ancienne base : prix_unitaire en INTEGER (euros entiers) → REAL (décimales)."""
    rows = list(conn.execute("PRAGMA table_info(devis_lignes)"))
    col = next((r for r in rows if r[1] == "prix_unitaire"), None)
    if not col:
        return
    decl = str(col[2] or "").upper()
    if "INT" not in decl:
        return
    conn.executescript(
        """
        CREATE TABLE devis_lignes__mig (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            devis_num TEXT NOT NULL,
            ordre INTEGER NOT NULL,
            description TEXT NOT NULL,
            quantite INTEGER NOT NULL,
            unite TEXT NOT NULL,
            unite_pow INTEGER,
            prix_unitaire REAL NOT NULL,
            taux_tva INTEGER NOT NULL,
            ligne_total_tva REAL NOT NULL,
            ligne_total_ttc REAL NOT NULL,
            FOREIGN KEY (devis_num) REFERENCES devis(devis_num) ON DELETE CASCADE
        );
        INSERT INTO devis_lignes__mig (
            id, devis_num, ordre, description, quantite, unite, unite_pow,
            prix_unitaire, taux_tva, ligne_total_tva, ligne_total_ttc
        )
        SELECT
            id, devis_num, ordre, description, quantite, unite, NULL,
            CAST(prix_unitaire AS REAL), taux_tva, ligne_total_tva, ligne_total_ttc
        FROM devis_lignes;
        DROP TABLE devis_lignes;
        ALTER TABLE devis_lignes__mig RENAME TO devis_lignes;
        CREATE INDEX IF NOT EXISTS idx_lignes_devis ON devis_lignes(devis_num);
        """
    )

def _ensure_ligne_unite_pow_column(conn: sqlite3.Connection) -> None:
    rows = list(conn.execute("PRAGMA table_info(devis_lignes)"))
    if any(r[1] == "unite_pow" for r in rows):
        return
    conn.execute("ALTER TABLE devis_lignes ADD COLUMN unite_pow INTEGER")


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS devis (
                devis_num TEXT PRIMARY KEY,
                destinataire_nom TEXT NOT NULL,
                destinataire_adresse TEXT NOT NULL,
                destinataire_cp TEXT,
                destinataire_siret TEXT,
                destinataire_telephone TEXT NOT NULL,
                infos_additionnelles TEXT,
                date_devis TEXT NOT NULL,
                date_validite TEXT NOT NULL,
                include_bank_details INTEGER NOT NULL DEFAULT 0,
                total_ht REAL NOT NULL,
                total_tva REAL NOT NULL,
                total_ttc REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS devis_lignes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                devis_num TEXT NOT NULL,
                ordre INTEGER NOT NULL,
                description TEXT NOT NULL,
                quantite INTEGER NOT NULL,
                unite TEXT NOT NULL,
                unite_pow INTEGER,
                prix_unitaire REAL NOT NULL,
                taux_tva INTEGER NOT NULL,
                ligne_total_tva REAL NOT NULL,
                ligne_total_ttc REAL NOT NULL,
                FOREIGN KEY (devis_num) REFERENCES devis(devis_num) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_lignes_devis ON devis_lignes(devis_num);

            CREATE TABLE IF NOT EXISTS factures (
                facture_num TEXT PRIMARY KEY,
                devis_num_source TEXT,
                destinataire_nom TEXT NOT NULL,
                destinataire_adresse TEXT NOT NULL,
                destinataire_cp TEXT,
                destinataire_siret TEXT,
                destinataire_telephone TEXT NOT NULL,
                infos_additionnelles TEXT,
                date_facture TEXT NOT NULL,
                date_validite TEXT NOT NULL,
                mode_paiement TEXT NOT NULL,
                is_acompte INTEGER NOT NULL DEFAULT 0,
                include_bank_details INTEGER NOT NULL DEFAULT 0,
                total_ht REAL NOT NULL,
                total_tva REAL NOT NULL,
                total_ttc REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS facture_lignes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                facture_num TEXT NOT NULL,
                ordre INTEGER NOT NULL,
                description TEXT NOT NULL,
                quantite INTEGER NOT NULL,
                unite TEXT NOT NULL,
                unite_pow INTEGER,
                prix_unitaire REAL NOT NULL,
                taux_tva INTEGER NOT NULL,
                ligne_total_tva REAL NOT NULL,
                ligne_total_ttc REAL NOT NULL,
                FOREIGN KEY (facture_num) REFERENCES factures(facture_num) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_lignes_facture ON facture_lignes(facture_num);
            """
        )
        _migrate_ligne_prix_unitaire_to_real(conn)
        _ensure_ligne_unite_pow_column(conn)
        # Back-compat: dacă factures există fără unele coloane, adaugă-le.
        try:
            rows = list(conn.execute("PRAGMA table_info(factures)"))
            cols = {r[1] for r in rows}
            if "mode_paiement" not in cols and rows:
                conn.execute("ALTER TABLE factures ADD COLUMN mode_paiement TEXT NOT NULL DEFAULT 'Virement'")
            if "devis_num_source" not in cols and rows:
                conn.execute("ALTER TABLE factures ADD COLUMN devis_num_source TEXT")
            if "destinataire_cp" not in cols and rows:
                conn.execute("ALTER TABLE factures ADD COLUMN destinataire_cp TEXT")
            if "destinataire_siret" not in cols and rows:
                conn.execute("ALTER TABLE factures ADD COLUMN destinataire_siret TEXT")
            if "is_acompte" not in cols and rows:
                conn.execute("ALTER TABLE factures ADD COLUMN is_acompte INTEGER NOT NULL DEFAULT 0")
            if "include_bank_details" not in cols and rows:
                conn.execute("ALTER TABLE factures ADD COLUMN include_bank_details INTEGER NOT NULL DEFAULT 0")
        except sqlite3.OperationalError:
            pass
        # Back-compat: devis — coloane noi
        try:
            rows = list(conn.execute("PRAGMA table_info(devis)"))
            cols = {r[1] for r in rows}
            if "destinataire_cp" not in cols and rows:
                conn.execute("ALTER TABLE devis ADD COLUMN destinataire_cp TEXT")
            if "destinataire_siret" not in cols and rows:
                conn.execute("ALTER TABLE devis ADD COLUMN destinataire_siret TEXT")
            if "include_bank_details" not in cols and rows:
                conn.execute("ALTER TABLE devis ADD COLUMN include_bank_details INTEGER NOT NULL DEFAULT 0")
        except sqlite3.OperationalError:
            pass


@dataclass
class LigneInput:
    description: str
    quantite: int
    unite: str
    unite_pow: int | None
    prix_unitaire: float
    taux_tva: int


@dataclass
class DevisPayload:
    devis_num: str
    destinataire_nom: str
    destinataire_adresse: str
    destinataire_cp: str | None
    destinataire_siret: str | None
    destinataire_telephone: str
    infos_additionnelles: str | None
    date_devis: str
    date_validite: str
    include_bank_details: bool
    lignes: list[LigneInput] = field(default_factory=list)


@dataclass
class FacturePayload:
    facture_num: str
    devis_num_source: str | None
    destinataire_nom: str
    destinataire_adresse: str
    destinataire_cp: str | None
    destinataire_siret: str | None
    destinataire_telephone: str
    infos_additionnelles: str | None
    date_facture: str
    date_validite: str
    mode_paiement: str
    is_acompte: bool
    include_bank_details: bool
    lignes: list[LigneInput] = field(default_factory=list)


def _calc_totals(lignes: Iterable[LigneInput]) -> tuple[list[dict[str, Any]], float, float, float]:
    rows_out: list[dict[str, Any]] = []
    total_ht = 0.0
    total_tva = 0.0
    for i, ln in enumerate(lignes):
        ht_ligne = float(ln.quantite) * float(ln.prix_unitaire)
        tva_ligne = ht_ligne * (ln.taux_tva / 100.0)
        ttc_ligne = ht_ligne + tva_ligne
        total_ht += ht_ligne
        total_tva += tva_ligne
        rows_out.append(
            {
                "ordre": i,
                "description": ln.description,
                "quantite": ln.quantite,
                "unite": ln.unite,
                "unite_pow": ln.unite_pow,
                "prix_unitaire": ln.prix_unitaire,
                "taux_tva": ln.taux_tva,
                "ligne_total_tva": tva_ligne,
                "ligne_total_ttc": ttc_ligne,
            }
        )
    total_ttc = total_ht + total_tva
    return rows_out, total_ht, total_tva, total_ttc


def insert_devis(payload: DevisPayload) -> None:
    rows, total_ht, total_tva, total_ttc = _calc_totals(payload.lignes)
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO devis (
                devis_num, destinataire_nom, destinataire_adresse, destinataire_cp, destinataire_siret, destinataire_telephone,
                infos_additionnelles, date_devis, date_validite, include_bank_details, total_ht, total_tva, total_ttc
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                payload.devis_num,
                payload.destinataire_nom,
                payload.destinataire_adresse,
                payload.destinataire_cp or None,
                payload.destinataire_siret or None,
                payload.destinataire_telephone,
                payload.infos_additionnelles or None,
                payload.date_devis,
                payload.date_validite,
                1 if payload.include_bank_details else 0,
                total_ht,
                total_tva,
                total_ttc,
            ),
        )
        for r in rows:
            conn.execute(
                """
                INSERT INTO devis_lignes (
                    devis_num, ordre, description, quantite, unite, unite_pow, prix_unitaire, taux_tva,
                    ligne_total_tva, ligne_total_ttc
                ) VALUES (?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    payload.devis_num,
                    r["ordre"],
                    r["description"],
                    r["quantite"],
                    r["unite"],
                    r.get("unite_pow"),
                    r["prix_unitaire"],
                    r["taux_tva"],
                    r["ligne_total_tva"],
                    r["ligne_total_ttc"],
                ),
            )


def update_devis(payload: DevisPayload) -> bool:
    rows, total_ht, total_tva, total_ttc = _calc_totals(payload.lignes)
    with get_conn() as conn:
        cur = conn.execute(
            """
            UPDATE devis SET
                destinataire_nom=?, destinataire_adresse=?, destinataire_cp=?, destinataire_siret=?, destinataire_telephone=?,
                infos_additionnelles=?, date_devis=?, date_validite=?,
                include_bank_details=?,
                total_ht=?, total_tva=?, total_ttc=?
            WHERE devis_num=?
            """,
            (
                payload.destinataire_nom,
                payload.destinataire_adresse,
                payload.destinataire_cp or None,
                payload.destinataire_siret or None,
                payload.destinataire_telephone,
                payload.infos_additionnelles or None,
                payload.date_devis,
                payload.date_validite,
                1 if payload.include_bank_details else 0,
                total_ht,
                total_tva,
                total_ttc,
                payload.devis_num,
            ),
        )
        if cur.rowcount == 0:
            return False
        conn.execute("DELETE FROM devis_lignes WHERE devis_num=?", (payload.devis_num,))
        for r in rows:
            conn.execute(
                """
                INSERT INTO devis_lignes (
                    devis_num, ordre, description, quantite, unite, unite_pow, prix_unitaire, taux_tva,
                    ligne_total_tva, ligne_total_ttc
                ) VALUES (?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    payload.devis_num,
                    r["ordre"],
                    r["description"],
                    r["quantite"],
                    r["unite"],
                    r.get("unite_pow"),
                    r["prix_unitaire"],
                    r["taux_tva"],
                    r["ligne_total_tva"],
                    r["ligne_total_ttc"],
                ),
            )
    return True


def insert_facture(payload: FacturePayload) -> None:
    rows, total_ht, total_tva, total_ttc = _calc_totals(payload.lignes)
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO factures (
                facture_num, devis_num_source, destinataire_nom, destinataire_adresse, destinataire_cp, destinataire_siret, destinataire_telephone,
                infos_additionnelles, date_facture, date_validite, mode_paiement, is_acompte, include_bank_details, total_ht, total_tva, total_ttc
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                payload.facture_num,
                payload.devis_num_source,
                payload.destinataire_nom,
                payload.destinataire_adresse,
                payload.destinataire_cp or None,
                payload.destinataire_siret or None,
                payload.destinataire_telephone,
                payload.infos_additionnelles or None,
                payload.date_facture,
                payload.date_validite,
                payload.mode_paiement,
                1 if payload.is_acompte else 0,
                1 if payload.include_bank_details else 0,
                total_ht,
                total_tva,
                total_ttc,
            ),
        )
        for r in rows:
            conn.execute(
                """
                INSERT INTO facture_lignes (
                    facture_num, ordre, description, quantite, unite, unite_pow, prix_unitaire, taux_tva,
                    ligne_total_tva, ligne_total_ttc
                ) VALUES (?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    payload.facture_num,
                    r["ordre"],
                    r["description"],
                    r["quantite"],
                    r["unite"],
                    r.get("unite_pow"),
                    r["prix_unitaire"],
                    r["taux_tva"],
                    r["ligne_total_tva"],
                    r["ligne_total_ttc"],
                ),
            )


def update_facture(payload: FacturePayload) -> bool:
    rows, total_ht, total_tva, total_ttc = _calc_totals(payload.lignes)
    with get_conn() as conn:
        cur = conn.execute(
            """
            UPDATE factures SET
                devis_num_source=?, destinataire_nom=?, destinataire_adresse=?, destinataire_cp=?, destinataire_siret=?, destinataire_telephone=?,
                infos_additionnelles=?, date_facture=?, date_validite=?, mode_paiement=?,
                is_acompte=?, include_bank_details=?,
                total_ht=?, total_tva=?, total_ttc=?
            WHERE facture_num=?
            """,
            (
                payload.devis_num_source,
                payload.destinataire_nom,
                payload.destinataire_adresse,
                payload.destinataire_cp or None,
                payload.destinataire_siret or None,
                payload.destinataire_telephone,
                payload.infos_additionnelles or None,
                payload.date_facture,
                payload.date_validite,
                payload.mode_paiement,
                1 if payload.is_acompte else 0,
                1 if payload.include_bank_details else 0,
                total_ht,
                total_tva,
                total_ttc,
                payload.facture_num,
            ),
        )
        if cur.rowcount == 0:
            return False
        conn.execute("DELETE FROM facture_lignes WHERE facture_num=?", (payload.facture_num,))
        for r in rows:
            conn.execute(
                """
                INSERT INTO facture_lignes (
                    facture_num, ordre, description, quantite, unite, unite_pow, prix_unitaire, taux_tva,
                    ligne_total_tva, ligne_total_ttc
                ) VALUES (?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    payload.facture_num,
                    r["ordre"],
                    r["description"],
                    r["quantite"],
                    r["unite"],
                    r.get("unite_pow"),
                    r["prix_unitaire"],
                    r["taux_tva"],
                    r["ligne_total_tva"],
                    r["ligne_total_ttc"],
                ),
            )
    return True


def delete_facture(facture_num: str) -> bool:
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM factures WHERE facture_num=?", (facture_num,))
        return cur.rowcount > 0


def get_facture(facture_num: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM factures WHERE facture_num=?", (facture_num,)).fetchone()
        if not row:
            return None
        lignes = conn.execute(
            "SELECT * FROM facture_lignes WHERE facture_num=? ORDER BY ordre",
            (facture_num,),
        ).fetchall()
        d = dict(row)
        d["lignes"] = [dict(l) for l in lignes]
        return d


def list_factures(q: str | None = None) -> list[dict[str, Any]]:
    sql = "SELECT * FROM factures"
    args: list[Any] = []
    if q:
        like = f"%{q.strip()}%"
        sql += """ WHERE facture_num LIKE ? OR destinataire_nom LIKE ?
            OR destinataire_adresse LIKE ? OR destinataire_telephone LIKE ?
            OR date_facture LIKE ? OR date_validite LIKE ?"""
        args = [like, like, like, like, like, like]
    sql += " ORDER BY facture_num"
    with get_conn() as conn:
        rows = conn.execute(sql, args).fetchall()
        return [dict(r) for r in rows]


def delete_devis(devis_num: str) -> bool:
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM devis WHERE devis_num=?", (devis_num,))
        return cur.rowcount > 0


def get_devis(devis_num: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM devis WHERE devis_num=?", (devis_num,)).fetchone()
        if not row:
            return None
        lignes = conn.execute(
            "SELECT * FROM devis_lignes WHERE devis_num=? ORDER BY ordre",
            (devis_num,),
        ).fetchall()
        d = dict(row)
        d["lignes"] = [dict(l) for l in lignes]
        return d


def list_devis(q: str | None = None) -> list[dict[str, Any]]:
    sql = "SELECT * FROM devis"
    args: list[Any] = []
    if q:
        like = f"%{q.strip()}%"
        sql += """ WHERE devis_num LIKE ? OR destinataire_nom LIKE ?
            OR destinataire_adresse LIKE ? OR destinataire_telephone LIKE ?
            OR date_devis LIKE ? OR date_validite LIKE ?"""
        args = [like, like, like, like, like, like]
    sql += " ORDER BY devis_num"
    with get_conn() as conn:
        rows = conn.execute(sql, args).fetchall()
        return [dict(r) for r in rows]


def get_many(nums: Iterable[str]) -> list[dict[str, Any]]:
    nums = list(nums)
    if not nums:
        return []
    placeholders = ",".join("?" * len(nums))
    with get_conn() as conn:
        devis_rows = conn.execute(
            f"SELECT * FROM devis WHERE devis_num IN ({placeholders}) ORDER BY devis_num",
            nums,
        ).fetchall()
        out: list[dict[str, Any]] = []
        for row in devis_rows:
            d = dict(row)
            lignes = conn.execute(
                "SELECT * FROM devis_lignes WHERE devis_num=? ORDER BY ordre",
                (d["devis_num"],),
            ).fetchall()
            d["lignes"] = [dict(l) for l in lignes]
            out.append(d)
        return out


def _parse_prix_unitaire(raw: Any) -> float:
    if isinstance(raw, bool):
        raise ValueError("Preț unitar invalid.")
    if isinstance(raw, (int, float)):
        p = float(raw)
    else:
        s = str(raw).strip().replace(",", ".")
        if not s:
            raise ValueError("Preț unitar invalid.")
        p = float(s)
    if not math.isfinite(p):
        raise ValueError("Preț unitar invalid.")
    return round(p, 6)

def _parse_unite_pow(raw: Any) -> int | None:
    if raw is None or raw == "":
        return None
    if isinstance(raw, bool):
        raise ValueError("Puterea unității este invalidă.")
    s = str(raw).strip()
    if not s:
        return None
    p = int(s)
    if p < 0 or p > 9:
        raise ValueError("Puterea unității este invalidă.")
    return p


def parse_lignes_json(raw: str) -> list[LigneInput]:
    data = json.loads(raw) if raw else []
    lignes: list[LigneInput] = []
    for item in data:
        description = str(item.get("description", "")).strip()
        if not description:
            continue
        lignes.append(
            LigneInput(
                description=description,
                quantite=int(item["quantite"]),
                unite=str(item.get("unite", "")).strip(),
                unite_pow=_parse_unite_pow(item.get("unite_pow")),
                prix_unitaire=_parse_prix_unitaire(item["prix_unitaire"]),
                taux_tva=int(item["taux_tva"]),
            )
        )
    return lignes

from __future__ import annotations

import re
from datetime import datetime


def normalize_devis_num(raw: str) -> str:
    s = str(raw).strip()
    if not s.isdigit():
        raise ValueError("Numărul devisului trebuie să conțină doar cifre.")
    if len(s) < 4:
        return s.zfill(4)
    return s


def validate_date_ddmmyyyy(s: str) -> str:
    s = str(s).strip()
    m = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", s)
    if not m:
        raise ValueError("Dată invalidă (format ZZ/LL/AAAA).")
    dd, mm, yyyy = int(m.group(1)), int(m.group(2)), int(m.group(3))
    datetime(yyyy, mm, dd)
    return s


def eur(value: float) -> str:
    s = f"{value:.2f}"
    sign = ""
    if s.startswith("-"):
        sign = "-"
        s = s[1:]
    intp, frac = s.split(".")
    intp = intp.replace(",", "")
    parts = []
    while intp:
        parts.insert(0, intp[-3:])
        intp = intp[:-3]
    grouped = " ".join(parts) if parts else "0"
    return f"{sign}{grouped},{frac} €"

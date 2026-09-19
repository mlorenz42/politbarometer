#!/usr/bin/env python3
"""Baut docs/index.html aus src/template.html, data/politbarometer.csv und data/regierungen.json.

Die Seite ist eigenständig (keine Nachladeanfragen): Umfragewerte und Regierungsdaten
werden direkt ins HTML eingebettet. Die Ausgabe ist deterministisch, damit ein Lauf
ohne neue Daten keinen Commit erzeugt.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIRST_DATE = "1998-01-01"  # davor gibt es keine lückenlose Reihe (Wahlergebnis 1994 als einziger Ausreißer)
# Spalten der eingebetteten Zeilen, in der Reihenfolge, die das Template erwartet
PARTIES = ["CDU/CSU", "SPD", "GRÜNE", "FDP", "LINKE", "AfD", "BSW"]


def value(text: str):
    return float(text) if text else None


def load_rows() -> list:
    with (ROOT / "data" / "politbarometer.csv").open(encoding="utf-8", newline="") as fh:
        records = list(csv.DictReader(fh))
    rows = []
    for r in records:
        if r["date"] < FIRST_DATE:
            continue
        rows.append(
            [r["date"], int(r["election"])]
            + [value(r[p]) for p in PARTIES]
            + [int(r["n"]) if r["n"] else None, r["period"] or None]
        )
    rows.sort(key=lambda x: (x[0], x[1]))
    return rows


def embed(obj) -> str:
    # "</" würde ein <script>-Element vorzeitig beenden
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def main() -> int:
    rows = load_rows()
    if len(rows) < 400:
        print("Nur %d Umfragezeilen, das sieht nicht plausibel aus." % len(rows), file=sys.stderr)
        return 1
    gov = json.loads((ROOT / "data" / "regierungen.json").read_text(encoding="utf-8"))
    template = (ROOT / "src" / "template.html").read_text(encoding="utf-8")
    for marker in ("/*DATA*/[]", "/*GOV*/{}"):
        if template.count(marker) != 1:
            print("Platzhalter %s im Template nicht genau einmal vorhanden." % marker, file=sys.stderr)
            return 1
    out = template.replace("/*DATA*/[]", embed(rows)).replace("/*GOV*/{}", embed(gov))
    target = ROOT / "docs" / "index.html"
    target.parent.mkdir(exist_ok=True)
    target.write_text(out, encoding="utf-8")
    print("docs/index.html: %d Umfragezeilen, %d Kabinette, %d KB" % (len(rows), len(gov["kabinette"]), len(out) // 1024))
    return 0


if __name__ == "__main__":
    sys.exit(main())

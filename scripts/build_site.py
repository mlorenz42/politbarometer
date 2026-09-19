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


# ---------- Länderseite ----------
# Reihenfolge der Werte je Umfrage: dargestellte Parteien, dann SSW, NPD, BIW, Sonstige
LAND_PLOTTED = [("cdu", "CDU/CSU"), ("spd", "SPD"), ("gru", "GRÜNE"), ("fdp", "FDP"), ("lin", "LINKE"),
                ("afd", "AfD"), ("bsw", "BSW"), ("fw", "FW"), ("pir", "PIRATEN")]
LAND_EXTRA = ["SSW", "NPD", "BIW", "Sonstige"]
MAX_SERIES = 8  # mehr Farben hält die Palette nicht aus; die kleinste Partei wird dann nur in der Tabelle geführt
MIN_PEAK, MIN_POLLS = 3.5, 5


def load_landtage() -> tuple:
    meta = json.loads((ROOT / "data" / "laender.json").read_text(encoding="utf-8"))
    gov = json.loads((ROOT / "data" / "landesregierungen.json").read_text(encoding="utf-8"))
    with (ROOT / "data" / "landtage.csv").open(encoding="utf-8", newline="") as fh:
        records = list(csv.DictReader(fh))
    out = []
    for land in meta:
        rows = sorted((r for r in records if r["land"] == land["slug"]), key=lambda r: (r["date"], -int(r["election"])))
        if not rows:
            raise ValueError("Keine Umfragen für %s" % land["slug"])
        insts = sorted({r["institut"] for r in rows if r["institut"]})
        embedded, peaks, counts = [], {k: 0.0 for k, _ in LAND_PLOTTED}, {k: 0 for k, _ in LAND_PLOTTED}
        for r in rows:
            values = [value(r[col]) for _, col in LAND_PLOTTED] + [value(r[col]) for col in LAND_EXTRA]
            if r["election"] == "0":
                for (k, _), v in zip(LAND_PLOTTED, values):
                    if v is not None:
                        peaks[k] = max(peaks[k], v)
                        counts[k] += 1
            embedded.append([r["date"], int(r["election"]), insts.index(r["institut"]) if r["institut"] else -1,
                             r["auftraggeber"] or None, int(r["befragte"]) if r["befragte"] else None, r["zeitraum"] or None] + values)
        keys = [k for k, _ in LAND_PLOTTED if peaks[k] >= MIN_PEAK and counts[k] >= MIN_POLLS]
        while len(keys) > MAX_SERIES:
            keys.remove(min(keys, key=lambda k: peaks[k]))
        out.append({"slug": land["slug"], "name": land["name"], "next": land["naechste_wahl"],
                    "union": "CSU" if land["slug"] == "bayern" else "CDU", "wahl": gov["laender"][land["slug"]]["wahl"],
                    "insts": insts, "parties": keys, "rows": embedded})
    return out, gov


def build_laender() -> int:
    laender, gov = load_landtage()
    template = (ROOT / "src" / "laender.html").read_text(encoding="utf-8")
    for marker in ("/*LAENDER*/[]", "/*GOV*/{}", "/*COMMON_CSS*/", "/*COMMON_JS*/"):
        if template.count(marker) != 1:
            print("Platzhalter %s im Länder-Template nicht genau einmal vorhanden." % marker, file=sys.stderr)
            return 1
    out = template.replace("/*LAENDER*/[]", embed(laender)).replace("/*GOV*/{}", embed(gov))
    out = out.replace("/*COMMON_CSS*/", (ROOT / "src" / "common.css").read_text(encoding="utf-8").rstrip("\n"))
    out = out.replace("/*COMMON_JS*/", (ROOT / "src" / "common.js").read_text(encoding="utf-8").rstrip("\n"))
    (ROOT / "docs" / "laender.html").write_text(out, encoding="utf-8")
    print("docs/laender.html: %d Länder, %d Zeilen, %d KB" % (len(laender), sum(len(l["rows"]) for l in laender), len(out) // 1024))
    return 0


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
    out = out.replace("/*COMMON_CSS*/", (ROOT / "src" / "common.css").read_text(encoding="utf-8").rstrip("\n"))
    out = out.replace("/*COMMON_JS*/", (ROOT / "src" / "common.js").read_text(encoding="utf-8").rstrip("\n"))
    target = ROOT / "docs" / "index.html"
    target.parent.mkdir(exist_ok=True)
    target.write_text(out, encoding="utf-8")
    print("docs/index.html: %d Umfragezeilen, %d Kabinette, %d KB" % (len(rows), len(gov["kabinette"]), len(out) // 1024))
    return build_laender()


if __name__ == "__main__":
    sys.exit(main())

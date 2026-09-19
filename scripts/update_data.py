#!/usr/bin/env python3
"""Holt die Politbarometer-Sonntagsfrage von wahlrecht.de und pflegt data/politbarometer.csv.

Standardmäßig wird nur die aktuelle Seite abgerufen (eine Anfrage) und mit der
vorhandenen CSV zusammengeführt. Mit --full werden zusätzlich alle Archivseiten
(1998 bis 2017) geladen, etwa beim ersten Aufbau der CSV.

Bei unplausiblen Ergebnissen (Seite leer, Tabelle umgebaut, neuestes Datum liegt
vor dem bisherigen) bricht das Skript mit Fehlercode 1 ab und lässt die CSV unberührt.
"""
from __future__ import annotations

import argparse
import csv
import html
import re
import sys
import time
import urllib.request
from pathlib import Path

BASE = "https://www.wahlrecht.de/umfragen/"
CURRENT = BASE + "politbarometer.htm"
ARCHIVE = [BASE + "politbarometer/politbarometer-%d.htm" % y for y in (1998, 2002, 2005, 2009, 2013, 2017)]
USER_AGENT = "politbarometer-verlauf (+https://github.com/mlorenz42/politbarometer)"

CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "politbarometer.csv"
PARTIES = ["CDU/CSU", "SPD", "GRÜNE", "FDP", "LINKE", "AfD", "BSW", "FW", "PIRATEN", "Sonstige"]
FIELDS = ["date", "election"] + PARTIES + ["n", "period"]
RENAME = {"PDS": "LINKE", "Linke.PDS": "LINKE"}  # Vorgängernamen der Linken
MIN_ROWS_CURRENT = 100  # die aktuelle Seite hat weit über 100 Zeilen; darunter stimmt etwas nicht


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def table_rows(page: str) -> list[list[str]]:
    rows = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", page, re.S):
        cells = [
            html.unescape(re.sub(r"<[^>]+>", "", td)).replace("\xa0", " ").strip()
            for td in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S)
        ]
        if any(cells):
            rows.append(cells)
    return rows


def number(cell: str):
    m = re.fullmatch(r"(\d+(?:,\d+)?)\s*%", cell.strip())
    return float(m.group(1).replace(",", ".")) if m else None


def parse_page(page: str, source: str) -> list[dict]:
    rows = table_rows(page)
    header = next((r for r in rows if r[:1] == [""] and "CDU/CSU" in r and "Befragte" in r), None)
    if header is None:
        raise ValueError("%s: Tabellenkopf nicht gefunden" % source)
    names = [RENAME.get(p, p) for p in header[2 : header.index("Befragte") - 1]]
    for name in names:
        if name not in PARTIES:
            print("::warning::%s: unbekannte Spalte '%s' wird ignoriert" % (source, name))

    records = []
    for r in rows:
        if not re.fullmatch(r"\d\d\.\d\d\.\d{4}", r[0]):
            continue
        rec = {"date": "%s-%s-%s" % (r[0][6:], r[0][3:5], r[0][:2])}
        cells = r[2 : 2 + len(names)]
        rest = [c for c in r[2 + len(names) :] if c]
        rec["election"] = int(any("wahl" in c.lower() for c in rest))
        for name, cell in zip(names, cells):
            if name not in PARTIES:
                continue
            if name == "Sonstige" and ("PIRATEN" in cell or "Sonst" in cell):
                # 2013: "PIRATEN 3 %Sonst. 3 %" steckt in einer Zelle
                mp = re.search(r"PIRATEN\s*(\d+(?:,\d+)?)\s*%", cell)
                ms = re.search(r"Sonst\.\s*(\d+(?:,\d+)?)\s*%", cell)
                if mp:
                    rec["PIRATEN"] = float(mp.group(1).replace(",", "."))
                if ms:
                    rec["Sonstige"] = float(ms.group(1).replace(",", "."))
                continue
            value = number(cell)
            if value is not None:
                rec[name] = value
        if rest and re.fullmatch(r"[\d.]+", rest[0]):
            rec["n"] = int(rest[0].replace(".", ""))
            rec["period"] = rest[1] if len(rest) > 1 else ""
        records.append(rec)
    if not records:
        raise ValueError("%s: keine Umfragezeilen gefunden" % source)
    return records


def read_csv() -> dict:
    if not CSV_PATH.exists():
        return {}
    with CSV_PATH.open(encoding="utf-8", newline="") as fh:
        return {(r["date"], int(r["election"])): r for r in csv.DictReader(fh)}


def cell_text(rec: dict, field: str) -> str:
    value = rec.get(field, "")
    if isinstance(value, float):
        return "%g" % value
    return "" if value is None else str(value)


def write_csv(data: dict) -> None:
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CSV_PATH.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(FIELDS)
        for key in sorted(data):
            writer.writerow([cell_text(data[key], f) for f in FIELDS])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--full", action="store_true", help="auch alle Archivseiten (1998–2017) laden")
    args = ap.parse_args()

    existing = read_csv()
    urls = (ARCHIVE if args.full else []) + [CURRENT]
    fetched = []
    for i, url in enumerate(urls):
        if i:
            time.sleep(2)  # ehrenamtlich betriebene Seite: nicht hetzen
        try:
            recs = parse_page(fetch(url), url)
        except Exception as exc:  # noqa: BLE001 - jede Störung soll zum Abbruch führen
            print("Fehler beim Abruf von %s: %s" % (url, exc), file=sys.stderr)
            return 1
        print("%s: %d Zeilen" % (url, len(recs)))
        fetched.extend(recs)
        if url == CURRENT and len(recs) < MIN_ROWS_CURRENT:
            print("Nur %d Zeilen auf der aktuellen Seite (erwartet > %d), Abbruch." % (len(recs), MIN_ROWS_CURRENT), file=sys.stderr)
            return 1

    new_latest = max(r["date"] for r in fetched)
    old_latest = max((k[0] for k in existing), default="")
    if new_latest < old_latest:
        print("Neuestes Datum %s liegt vor dem bisherigen %s, Abbruch." % (new_latest, old_latest), file=sys.stderr)
        return 1

    merged = dict(existing)
    added = changed = 0
    for rec in fetched:
        key = (rec["date"], rec["election"])
        cur = merged.get(key)
        if cur is None:
            added += 1
        elif any(cell_text(rec, f) != cell_text(cur, f) for f in FIELDS):
            changed += 1
        merged[key] = rec
    write_csv(merged)
    print("CSV: %d Zeilen (%d neu, %d geändert), neueste Umfrage %s" % (len(merged), added, changed, new_latest))
    return 0


if __name__ == "__main__":
    sys.exit(main())

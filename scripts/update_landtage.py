#!/usr/bin/env python3
"""Holt die Sonntagsfragen zu den Landtagswahlen von wahlrecht.de und pflegt data/landtage.csv.

Jede Landesseite (https://www.wahlrecht.de/umfragen/landtage/<land>.htm) enthält alle Umfragen
mehrerer Institute, aufgeteilt in eine Tabelle je Wahlperiode. Die Spalten (Parteien) unterscheiden
sich je Tabelle. Dazu kommen Zeilen mit dem Ergebnis der jeweiligen Landtagswahl.

Die Seiten enthalten die komplette Historie. Das Skript führt neue und geänderte Zeilen in die
vorhandene CSV ein (nichts wird gelöscht). Zusätzlich entsteht data/laender.json mit Name, Kürzel
und nächstem Wahltermin je Land aus der Übersichtsseite.

Bei unplausiblen Ergebnissen (Seite leer, Tabelle umgebaut, neuestes Datum liegt vor dem
bisherigen) bricht das Skript mit Fehlercode 1 ab und lässt die Dateien unberührt.
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = "https://www.wahlrecht.de/umfragen/landtage/"
USER_AGENT = "politbarometer-verlauf (+https://github.com/mlorenz42/politbarometer)"
CSV_PATH = ROOT / "data" / "landtage.csv"
LAENDER_PATH = ROOT / "data" / "laender.json"

# Spaltenkopf auf der Seite -> Spalte in der CSV. Alles andere landet in "weitere".
COLUMN_OF = {
    "CDU": "CDU/CSU", "CSU": "CDU/CSU", "SPD": "SPD", "GRÜNE": "GRÜNE", "GAL": "GRÜNE", "FDP": "FDP",
    "LINKE": "LINKE", "PDS": "LINKE", "AfD": "AfD", "BSW": "BSW", "FW": "FW", "BVB/FW": "FW",
    "PIRATEN": "PIRATEN", "SSW": "SSW", "NPD": "NPD", "BIW/BD": "BIW",
}
PARTIES = ["CDU/CSU", "SPD", "GRÜNE", "FDP", "LINKE", "AfD", "BSW", "FW", "PIRATEN", "SSW", "NPD", "BIW"]
FIELDS = ["land", "date", "election", "institut", "auftraggeber", "methode", "befragte", "zeitraum"] + PARTIES + ["Sonstige", "weitere"]
MIN_ROWS_PER_STATE = 15


# ---------- Abruf ----------
_last = [0.0]


def fetch(url: str) -> str:
    wait = 1.5 - (time.time() - _last[0])  # ehrenamtlich betriebene Seite: nicht hetzen
    if wait > 0:
        time.sleep(wait)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=45) as resp:
        text = resp.read().decode("utf-8")
    _last[0] = time.time()
    return text


# ---------- Tabellen lesen ----------
def clean(text: str) -> str:
    text = re.sub(r"<br\s*/?>", " ", text)
    text = html.unescape(re.sub(r"<[^>]+>", "", text)).replace("\xa0", " ").replace("\xad", "")
    return re.sub(r"\s+", " ", text).strip()


def tables(page: str) -> list:
    """Alle Tabellen als Zeilen; colspan-Zellen werden auf die überdeckten Spalten verteilt."""
    out = []
    for table in re.findall(r"<table.*?</table>", page, re.S):
        rows = []
        for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", table, re.S):
            cells = []
            for attrs, body in re.findall(r"<t[dh]([^>]*)>(.*?)</t[dh]>", tr, re.S):
                span = re.search(r'colspan="?(\d+)', attrs)
                n = int(span.group(1)) if span else 1
                text = clean(body)
                if n == 1:
                    cells.append(text)
                elif not cells:  # Beschriftung am Zeilenanfang: Text vorn, Rest leer
                    cells.extend([text] + [""] * (n - 1))
                else:  # zusammengefasste Werte (z. B. AfD + Sonstige): Text in der letzten Spalte
                    cells.extend([""] * (n - 1) + [text])
            if any(cells):
                rows.append(cells)
        out.append(rows)
    return out


def number(cell: str):
    m = re.fullmatch(r"(\d+(?:,\d+)?)\s*%\*?", cell.strip())
    return float(m.group(1).replace(",", ".")) if m else None


def fmt(value: float) -> str:
    return "%g" % value


def parse_sonstige(cell: str, out: dict, taken: set) -> None:
    """'BSW 2 %BP 1 %Sonst. 5 %' oder '9 %' -> BSW, weitere, Sonstige."""
    plain_value = number(cell)
    if plain_value is not None:
        out["Sonstige"] = plain_value
        return
    extra = []
    for name, value in re.findall(r"([^\d%]+?)\s*(\d+(?:,\d+)?)\s*%", cell):
        name = name.strip(" ,;")
        val = float(value.replace(",", "."))
        if name.startswith("Sonst"):
            out["Sonstige"] = val
        elif name in COLUMN_OF and COLUMN_OF[name] not in taken:
            out[COLUMN_OF[name]] = val
        else:
            extra.append("%s=%s" % (name, fmt(val)))
    if extra:
        out["weitere"] = ";".join(extra)


def german_date(text: str):
    m = re.fullmatch(r"(\d\d)\.(\d\d)\.(\d{4})", text.strip())
    return "%s-%s-%s" % (m.group(3), m.group(2), m.group(1)) if m else None


def parse_respondents(cell: str) -> tuple:
    """'TOM • 1.00325.02.–03.03.' -> ('TOM', 1003, '25.02.–03.03.')"""
    method, _, rest = cell.partition("•")
    rest = rest.strip()
    period = re.search(r"(\d\d\.\d\d\.\s*–\s*\d\d\.\d\d\.?)$", rest)
    n_part = rest[: period.start()] if period else rest
    digits = re.sub(r"\D", "", n_part)
    return method.strip(), (int(digits) if digits else None), (re.sub(r"\s+", "", period.group(1)) if period else "")


def institute(name: str) -> str:
    name = re.sub(r"<!--|-->", "", name).strip()  # Reste von HTML-Kommentaren im Quelltext
    name = re.sub(r"(\w)- (\w)", r"\1\2", name)  # "Forschungs- gruppe Wahlen" (Silbentrennung im Quelltext)
    return re.sub(r"^Infratest ?dimap$", "Infratest dimap", name)


def parse_state(page: str, slug: str) -> list:
    records = []
    for rows in tables(page):
        header = next((r for r in rows if r[:1] == ["Institut"] and "Datum" in r), None)
        if header is None:
            continue
        # Die Tabellen haben je Seite und Wahlperiode unterschiedlich viele Leerspalten. Deshalb
        # werden die Spalten über ihre Überschriften gefunden, nicht über feste Positionen.
        date_i = header.index("Datum")
        resp_i = header.index("Befragte") if "Befragte" in header else None
        client_i = header.index("Auftraggeber") if "Auftraggeber" in header else None
        cols = [(i, name, "Sonstige" if name == "Sonstige" else COLUMN_OF.get(name)) for i, name in enumerate(header) if i > date_i and name]
        taken = {c for _, _, c in cols if c and c != "Sonstige"}
        for r in rows:
            if r == header or not r or not r[0]:
                continue
            election = re.search(r"wahl am (\d\d\.\d\d\.\d{4})", r[0])
            rec = {"land": slug}
            if election:
                rec.update(date=german_date(election.group(1)), election=1, institut="", auftraggeber="")
            else:
                date = german_date(r[date_i]) if len(r) > date_i else None
                if date is None:  # Zwischenzeilen und unvollständige Datumsangaben ("??.12.1992")
                    continue
                method, n, period = parse_respondents(r[resp_i]) if resp_i is not None and len(r) > resp_i else ("", None, "")
                rec.update(date=date, election=0, institut=institute(r[0]),
                           auftraggeber=r[client_i] if client_i is not None and len(r) > client_i else "",
                           methode=method, befragte=n, zeitraum=period)
            extra = []
            for i, name, column in cols:
                cell = r[i] if len(r) > i else ""
                if not cell or cell in ("–", "-"):
                    continue
                if column == "Sonstige":
                    parse_sonstige(cell, rec, taken)
                else:
                    value = number(cell)
                    if value is None:
                        continue
                    if column:
                        rec[column] = value
                    else:
                        extra.append("%s=%s" % (name, fmt(value)))
            if extra:
                rec["weitere"] = ";".join(filter(None, [rec.get("weitere", "")] + extra))
            if any(rec.get(p) is not None for p in PARTIES):
                records.append(rec)
    if not records:
        raise ValueError("%s: keine Zeilen gelesen" % slug)
    return records


def parse_index(page: str) -> list:
    """Übersichtsseite: Land, Kürzel der Seite und nächster Wahltermin."""
    laender = []
    pattern = (r'<tr id="(\w+)">\s*<th[^>]*><a href="([a-z-]+)\.htm"[^>]*>(.*?)</a></th>\s*'
               r'<td[^>]*><a href="[^"]*termine\.htm[^"]*"[^>]*>(.*?)</a>')
    for m in re.finditer(pattern, page, re.S):
        laender.append({"slug": m.group(2), "kuerzel": m.group(1), "name": clean(m.group(3)), "naechste_wahl": clean(m.group(4))})
    if len(laender) != 16:
        raise ValueError("Übersichtsseite: %d statt 16 Länder gelesen" % len(laender))
    return laender


# ---------- CSV ----------
def cell_text(rec: dict, field: str) -> str:
    value = rec.get(field, "")
    if isinstance(value, float):
        return fmt(value)
    return "" if value is None else str(value)


def key_of(rec: dict) -> tuple:
    return (rec["land"], str(rec["date"]), str(int(rec["election"])), rec.get("institut", "") or "",
            rec.get("auftraggeber", "") or "", rec.get("zeitraum", "") or "")


def richness(rec: dict) -> int:
    return sum(1 for p in PARTIES if rec.get(p) not in (None, ""))


def read_csv() -> dict:
    if not CSV_PATH.exists():
        return {}
    with CSV_PATH.open(encoding="utf-8", newline="") as fh:
        return {key_of(r): r for r in csv.DictReader(fh)}


def write_csv(data: dict) -> None:
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CSV_PATH.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(FIELDS)
        for key in sorted(data):
            writer.writerow([cell_text(data[key], f) for f in FIELDS])


def fail(message: str) -> int:
    print(("::error::" if os.environ.get("GITHUB_ACTIONS") else "") + message, file=sys.stderr)
    return 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from-dir", help="statt zu laden: gespeicherte HTML-Seiten aus diesem Ordner lesen (Entwicklung)")
    args = ap.parse_args()

    def get(name: str) -> str:
        if args.from_dir:
            return (Path(args.from_dir) / name).read_text(encoding="utf-8")
        return fetch(BASE + name)

    try:
        laender = parse_index(get("index.htm") if args.from_dir else fetch(BASE))
        existing = read_csv()
        fetched = []
        for land in laender:
            recs = parse_state(get(land["slug"] + ".htm"), land["slug"])
            if len(recs) < MIN_ROWS_PER_STATE:
                raise ValueError("%s: nur %d Zeilen (erwartet mindestens %d)" % (land["slug"], len(recs), MIN_ROWS_PER_STATE))
            old_latest = max((k[1] for k in existing if k[0] == land["slug"]), default="")
            new_latest = max(r["date"] for r in recs)
            if new_latest < old_latest:
                raise ValueError("%s: neuestes Datum %s liegt vor dem bisherigen %s" % (land["slug"], new_latest, old_latest))
            print("%-24s %4d Zeilen, neueste %s" % (land["slug"], len(recs), new_latest))
            fetched.extend(recs)
    except Exception as exc:  # noqa: BLE001 - jede Störung soll den Lauf sichtbar scheitern lassen
        return fail("Landtagsumfragen nicht aktualisiert (%s): %s" % (type(exc).__name__, exc))

    # Ein Wahlergebnis steht am Ende der einen und am Anfang der nächsten Tabelle, dort mit anderen
    # Spalten (z. B. mit oder ohne PIRATEN). Behalten wird die Zeile mit den meisten einzeln
    # ausgewiesenen Parteien.
    unique = {}
    for rec in fetched:
        key = key_of(rec)
        if key in unique and rec["election"] and richness(unique[key]) > richness(rec):
            continue
        unique[key] = rec

    merged = dict(existing)
    added = changed = 0
    for key, rec in unique.items():
        cur = merged.get(key)
        if cur is None:
            added += 1
        elif any(cell_text(rec, f) != cell_text(cur, f) for f in FIELDS):
            changed += 1
        merged[key] = rec
    write_csv(merged)
    LAENDER_PATH.write_text(json.dumps(laender, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("CSV: %d Zeilen (%d neu, %d geändert)" % (len(merged), added, changed))
    return 0


if __name__ == "__main__":
    sys.exit(main())

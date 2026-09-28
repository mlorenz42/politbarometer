#!/usr/bin/env python3
"""Erzeugt data/sitze.json (Sitzverteilung im Bundestag und in den 16 Landtagen) aus der deutschen Wikipedia.

Bundestag und jeder Landtag haben einen dauerhaften Wikipedia-Artikel („Deutscher Bundestag“,
„Bayerischer Landtag“ …), der nach jeder Wahl aktualisiert wird und in seiner Infobox zwei
zusammenhängende, von den Artikel-Autoren gepflegte Angaben trägt:

  1. Ein Feld „GrafikSitzverteilung“ mit den Sitzen je Fraktion/Partei als einfache Zahlenliste
     (Vorlage {{Sitzverteilung|...}}), inklusive der von der Wikipedia gewählten Reihenfolge
     (links nach rechts im politischen Spektrum) – das ergibt Sitzzahlen und Anordnung.
  2. Ein Feld „Sitzverteilung“ mit einem Link auf das amtierende Kabinett als „Regierung (n)“,
     z. B. „[[Kabinett Merz|Regierung]] (328)“ – das ergibt, welches Kabinett regiert und wie
     viele Sitze die Regierungsparteien zusammen haben.

Das Skript prüft (2) gegen die bereits vorhandenen Regierungsdaten (data/regierungen.json bzw.
data/landesregierungen.json, die deshalb vor diesem Skript aktuell sein müssen): Das verlinkte
Kabinett muss unser jeweils aktuelles Kabinett sein, und die Sitze seiner Koalitionsparteien
müssen sich zu der genannten Zahl aufsummieren. Scheitert das für den Bundestag oder eines der
16 Länder (Widerspruch, fehlender Artikel, unlesbare Sitzverteilung), sammelt das Skript alle
Fehler, bricht danach insgesamt mit Fehlercode 1 ab und lässt die JSON unberührt – wie bei den
übrigen update_*.py-Skripten lieber gar nicht veröffentlichen als eine Datei mit teils veralteten,
teils neuen Ständen.

    python scripts/update_sitze.py             # JSON aktualisieren
    python scripts/update_sitze.py --dry-run   # nur anzeigen, was sich ändern würde
"""
from __future__ import annotations

import argparse
import datetime as dt
import difflib
import json
import os
import re
import sys
import urllib.parse
from pathlib import Path

from wikitext import Mismatch, infobox, party_key, template_body, wikitexts

ROOT = Path(__file__).resolve().parent.parent
JSON_PATH = ROOT / "data" / "sitze.json"
BUND_ARTIKEL = "Deutscher Bundestag"
# Kürzel wie in update_landesregierungen.py, plus der Artikel mit der laufend gepflegten Sitzverteilung
LAND_ARTIKEL = {
    "baden-wuerttemberg": "Landtag von Baden-Württemberg", "bayern": "Bayerischer Landtag",
    "berlin": "Abgeordnetenhaus von Berlin", "brandenburg": "Landtag Brandenburg",
    "bremen": "Bremische Bürgerschaft", "hamburg": "Hamburgische Bürgerschaft",
    "hessen": "Hessischer Landtag", "mecklenburg-vorpommern": "Landtag Mecklenburg-Vorpommern",
    "niedersachsen": "Niedersächsischer Landtag", "nrw": "Landtag Nordrhein-Westfalen",
    "rheinland-pfalz": "Landtag Rheinland-Pfalz", "saarland": "Landtag des Saarlandes",
    "sachsen": "Sächsischer Landtag", "sachsen-anhalt": "Landtag von Sachsen-Anhalt",
    "schleswig-holstein": "Landtag von Schleswig-Holstein", "thueringen": "Thüringer Landtag",
}
warnings: list = []


def warn(message: str) -> None:
    warnings.append(message)
    print(("::warning::" if os.environ.get("GITHUB_ACTIONS") else "Warnung: ") + message, file=sys.stderr)


def parse_grafik(body: str, registry: dict) -> tuple:
    """Wikitext im Feld "GrafikSitzverteilung" -> (Reihenfolge der Kürzel, {Kürzel: Sitze}).

    Zeilen ohne "=" listen die Reihenfolge ("|LINKE|SPD|GRÜNE|..."); Zeilen mit "=" sind entweder
    eine Sitzzahl ("| SPD = 120") oder ein Wikilink-Zusatz ("| SPD Link = [[...]]", übersprungen).
    Metadatenzeilen (Überschrift, Land, Anmerkung, float, …) fallen automatisch heraus, weil ihr
    Wert keine reine Zahl ist.
    """
    order_raw: list = []
    seats: dict = {}
    for raw in body.split("\n"):
        line = raw.strip()
        if line.startswith("|"):
            line = line[1:].strip()
        if not line:
            continue
        if "=" not in line:
            order_raw = [p.strip() for p in line.split("|") if p.strip()]
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        if key.lower().endswith("link"):
            continue
        val = re.sub(r"<[^>]+>", "", val)  # <ref>…</ref> in Anmerkungen
        val = re.sub(r"\s", "", val)
        if re.fullmatch(r"\d+", val):
            seats[key] = seats.get(key, 0) + int(val)
    if not seats:
        raise Mismatch("keine Sitzzahlen in der Sitzverteilung gefunden")
    mapped: dict = {}
    for raw_key, n in seats.items():
        k = party_key(raw_key, registry)
        mapped[k] = mapped.get(k, 0) + n
    order: list = []
    for raw_key in order_raw:
        k = party_key(raw_key, registry)
        if k in mapped and k not in order:
            order.append(k)
    for k in mapped:  # zur Sicherheit: Sitze ohne Eintrag in der Reihenfolge-Zeile hinten anhängen
        if k not in order:
            order.append(k)
    return order, mapped


def current_government(data: dict) -> tuple:
    """Letztes Kabinett aus regierungen.json/landesregierungen.json -> (Name, Koalitions-Kürzel)."""
    cab = data["kabinette"][-1]
    return cab["cab"], cab["ph"][-1]["co"]


def parse_one(title: str, text: str, canonical: str, gov_source: dict) -> dict:
    infobox_body = template_body(text, "Infobox Parlament")
    if infobox_body is None:
        raise Mismatch("%s: Infobox Parlament nicht gefunden" % canonical)
    box = infobox(text, canonical, "Infobox Parlament")
    grafik = template_body(infobox_body, "Sitzverteilung")  # das "{{Sitzverteilung …}}" in "GrafikSitzverteilung ="
    if grafik is None:
        raise Mismatch("%s: Feld 'GrafikSitzverteilung' nicht gefunden" % canonical)
    registry: dict = {}
    order, seats = parse_grafik(grafik, registry)

    gov_field = box.get("Sitzverteilung", "")
    gm = re.search(r"\[\[([^\]|]+)\|Regierung\]\]\s*\((\d+)\)", gov_field)
    if not gm:
        raise Mismatch("%s: keine Regierungsangabe ('[[…|Regierung]] (n)') im Feld 'Sitzverteilung'" % canonical)
    linked_cab, stated_total = gm.group(1).strip(), int(gm.group(2))

    cab_name, coalition = current_government(gov_source)
    if linked_cab != cab_name:
        raise Mismatch("%s: Sitzverteilung verlinkt '%s' als Regierung, unsere Regierungsdaten kennen aber '%s'"
                        % (canonical, linked_cab, cab_name))
    computed_total = sum(seats.get(k, 0) for k in coalition)
    if computed_total != stated_total:
        raise Mismatch("%s: Sitze der Koalitionsparteien ergeben %d, die Sitzverteilung nennt aber %d für '%s'"
                        % (canonical, computed_total, stated_total, cab_name))

    return {
        "quelle": "https://de.wikipedia.org/wiki/" + urllib.parse.quote(canonical.replace(" ", "_")),
        "gesamt": sum(seats.values()),
        "regierung": {"cab": cab_name, "sitze": stated_total},
        "reihenfolge": order,
        "sitze": seats,
        "parteien": registry,
    }


def build() -> dict:
    titles = [BUND_ARTIKEL] + list(LAND_ARTIKEL.values())
    pages = wikitexts(titles)
    regierungen = json.loads((ROOT / "data" / "regierungen.json").read_text(encoding="utf-8"))
    landesregierungen = json.loads((ROOT / "data" / "landesregierungen.json").read_text(encoding="utf-8"))

    result = {"stand": None, "bund": None, "laender": {}}
    errors = []

    canonical, text = pages[BUND_ARTIKEL]
    try:
        result["bund"] = parse_one(BUND_ARTIKEL, text, canonical, regierungen)
    except Mismatch as exc:
        errors.append(str(exc))

    for slug, title in LAND_ARTIKEL.items():
        canonical, text = pages[title]
        try:
            result["laender"][slug] = parse_one(title, text, canonical, landesregierungen["laender"][slug])
        except Mismatch as exc:
            errors.append(str(exc))

    if errors:
        raise Mismatch("; ".join(errors))
    result["stand"] = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    return result


def dump(obj: dict) -> str:
    text = json.dumps(obj, ensure_ascii=False, indent=1)
    # kurze Reihenfolge-Listen in einer Zeile halten
    text = re.sub(r'\[\s+("[^"\]]*"(?:,\s+"[^"\]]*")*)\s+\]', lambda m: "[" + re.sub(r"\s+", " ", m.group(1)) + "]", text)
    return text + "\n"


def fail(message: str) -> int:
    print(("::error::" if os.environ.get("GITHUB_ACTIONS") else "") + message, file=sys.stderr)
    return 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="nur den Unterschied zur vorhandenen JSON anzeigen")
    args = ap.parse_args()
    try:
        new = dump(build())
    except Mismatch as exc:
        return fail("Sitzverteilung nicht aktualisiert: %s" % exc)
    except Exception as exc:  # noqa: BLE001 - Netzwerk- und Formatfehler sollen den Lauf sichtbar scheitern lassen
        return fail("Sitzverteilung nicht aktualisiert (%s): %s" % (type(exc).__name__, exc))
    old_obj = json.loads(JSON_PATH.read_text(encoding="utf-8")) if JSON_PATH.exists() else {}
    diff = list(difflib.unified_diff(dump(old_obj).splitlines(), new.splitlines(), "bisher", "neu", lineterm="", n=1)) if old_obj else []
    changed = [d for d in diff if d[:1] in "+-" and not d.startswith(("+++", "---")) and '"stand"' not in d]
    if args.dry_run:
        print("\n".join(diff) if changed else ("Keine inhaltlichen Unterschiede." if old_obj else new))
        return 0
    JSON_PATH.write_text(new, encoding="utf-8")
    print("data/sitze.json: %s (%d Warnungen)" % ("inhaltlich geändert" if changed else "inhaltlich unverändert (nur Stand aktualisiert)", len(warnings)))
    return 0


if __name__ == "__main__":
    sys.exit(main())

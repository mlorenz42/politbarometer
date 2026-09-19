#!/usr/bin/env python3
"""Aktualisiert data/regierungen.json aus der deutschen Wikipedia.

Quellen (zwei voneinander unabhängige Seitentypen, die gegeneinander geprüft werden):
  1. Die Infobox jedes Kabinettsartikels („Kabinett Kohl V“ … „Kabinett Merz“). Von Kohl V
     aus folgt das Skript dem Feld „Nachfolger“, ein neues Kabinett wird also von selbst
     erkannt. Liefert: Kanzler(in), Amtszeit, Koalitionsparteien (samt Wechsel während
     der Amtszeit).
  2. Die Tabelle in „Liste der deutschen Bundesregierungen“. Liefert: Partei des Kanzlers,
     den aktuellen Vizekanzler und dient als Gegenprobe (Kanzler, Daten, Parteien).

Stimmen die beiden Quellen nicht überein, ist eine Partei unbekannt oder eine Seite
umgebaut, bricht das Skript mit Fehlercode 1 ab und lässt die JSON unberührt.

    python scripts/update_regierungen.py             # JSON aktualisieren
    python scripts/update_regierungen.py --dry-run   # nur anzeigen, was sich ändern würde
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import difflib
import json
import os
import re
import sys
import urllib.parse
from pathlib import Path

from wikitext import MONTHS, Mismatch, expand, first_link_name, german_date, infobox, parse_wikitable, plain, wikitext

ROOT = Path(__file__).resolve().parent.parent
JSON_PATH = ROOT / "data" / "regierungen.json"
CSV_PATH = ROOT / "data" / "politbarometer.csv"
FIRST_CABINET = "Kabinett Kohl V"  # das erste Kabinett, das den Datenbeginn (1998) überdeckt
LIST_ARTICLE = "Liste der deutschen Bundesregierungen"

# Kürzel wie in der Grafik (Template) -> Anzeigename
PARTY_LABEL = {"cdu": "CDU", "spd": "SPD", "gru": "GRÜNE", "fdp": "FDP", "lin": "LINKE", "afd": "AfD", "bsw": "BSW"}


def party_keys(text: str) -> list:
    keys = []
    for token in re.split(r"[,/]|\bund\b", text):
        t = token.strip().lower()
        if not t:
            continue
        if "cdu" in t or "csu" in t or "union" in t:
            k = "cdu"
        elif "spd" in t:
            k = "spd"
        elif "grüne" in t or "bündnis 90" in t:
            k = "gru"
        elif "fdp" in t:
            k = "fdp"
        elif "linke" in t or "pds" in t:
            k = "lin"
        elif "afd" in t:
            k = "afd"
        elif "bsw" in t or "wagenknecht" in t:
            k = "bsw"
        else:
            raise Mismatch("Unbekannte Partei '%s'. Neue Partei im Template (PARTIES/CSS) und hier ergänzen." % token.strip())
        if k not in keys:
            keys.append(k)
    return keys


# ---------- Quelle 1: Infobox eines Kabinettsartikels ----------
def coalition_phases(raw: str, start: str, end, title: str) -> list:
    """Koalition-Feld -> Phasen. Mehrere Koalitionen stehen als 'Parteien<br />(bis D)<br />Parteien<br />(ab D)'."""
    parts, quals = [], []
    for seg in re.split(r"<br\s*/?>", raw):
        seg = seg.strip()
        if not seg:
            continue
        if plain(seg).startswith("("):
            d = german_date(seg)
            if d is None:
                raise Mismatch("%s: Koalitionsvermerk '%s' nicht lesbar" % (title, plain(seg)))
            quals.append(d)
        else:
            link = re.search(r"\[\[([^\]|]+)\|", seg)
            parts.append({"co": party_keys(plain(seg)), "name": link.group(1) if link else ""})
    if not parts:
        raise Mismatch("%s: keine Koalitionsparteien in der Infobox" % title)
    if len(parts) == 1 and not quals:
        return [{"from": start, "to": end, "co": parts[0]["co"], "coalition": parts[0]["name"]}]
    if len(parts) == 2 and len(quals) == 2 and quals[0] == quals[1]:
        return [{"from": start, "to": quals[0], "co": parts[0]["co"], "coalition": parts[0]["name"]},
                {"from": quals[0], "to": end, "co": parts[1]["co"], "coalition": parts[1]["name"]}]
    raise Mismatch("%s: Koalitionsangabe hat ein unerwartetes Format: %s" % (title, plain(raw)))


def read_cabinets() -> list:
    cabinets, title, seen = [], FIRST_CABINET, set()
    while title:
        title, text = wikitext(title)
        if title in seen:
            raise Mismatch("Schleife in der Nachfolger-Kette bei '%s'" % title)
        seen.add(title)
        box = infobox(text, title)
        start = box.get("Beginn", "")
        end = box.get("Ende") or None
        if not re.fullmatch(r"\d{4}-\d\d-\d\d", start) or (end and not re.fullmatch(r"\d{4}-\d\d-\d\d", end)):
            raise Mismatch("%s: Beginn/Ende nicht im Format JJJJ-MM-TT ('%s' / '%s')" % (title, start, end))
        cabinets.append({
            "cab": title, "name": re.sub(r"^Kabinett ", "", title),
            "title": plain(box.get("Titel Chef", "")) or "Bundeskanzler",
            "who": first_link_name(box.get("Chef", "")),
            "from": start, "to": end,
            "phases": coalition_phases(box.get("Koalition", ""), start, end, title),
            "text": text,
        })
        nxt = re.search(r"\[\[([^\]|]+)", box.get("Nachfolger", ""))
        title = nxt.group(1).strip() if nxt else None
    return cabinets


# ---------- Quelle 2: Tabelle in der Liste der Bundesregierungen ----------
def read_list() -> list:
    _, text = wikitext(LIST_ARTICLE)
    grid = expand(parse_wikitable(text))
    header = [plain(c) for c in grid[0]]

    def col(word: str) -> int:
        for i, h in enumerate(header):
            if word in h:
                return i
        raise Mismatch("Liste der Bundesregierungen: Spalte '%s' fehlt (Spalten: %s)" % (word, header))

    ci = {k: col(k) for k in ("Kabinett", "Parteien", "Bundeskanzler", "Vizekanzler", "Amtsantritt", "Ende")}
    rows, started = [], False
    for r in grid[1:]:
        if len(r) < len(header):
            continue
        cab_link = re.search(r"\[\[([^\]|]+)", r[ci["Kabinett"]])
        if not cab_link:
            continue
        started = started or cab_link.group(1).strip() == FIRST_CABINET
        if not started:  # ältere Kabinette enthalten Parteien (DP, BHE, ...), die hier keine Rolle spielen
            continue
        chancellor_cell = r[ci["Bundeskanzler"]]
        party = re.findall(r"\(([^()]*)\)\s*$", plain(chancellor_cell))
        vice_cell = r[ci["Vizekanzler"]]
        vice_party = re.findall(r"\(([^()]*)\)\s*$", plain(vice_cell))
        rows.append({
            "cab": cab_link.group(1).strip(),
            "co": party_keys(", ".join(re.findall(r"\{\{Partei\|([^|}]+)", r[ci["Parteien"]]))),
            "from": german_date(r[ci["Amtsantritt"]]), "to": german_date(r[ci["Ende"]]),
            "who": first_link_name(chancellor_cell),
            "who_party": party_keys(party[-1])[0] if party and party[-1] and not party[-1].startswith("*") else None,
            "vice": first_link_name(vice_cell) if "[[" in vice_cell else None,
            "vice_party": party_keys(vice_party[-1])[0] if vice_party else None,
        })
    if not rows:
        raise Mismatch("Liste der Bundesregierungen: keine Zeilen gelesen")
    return rows


# ---------- Zusammenführen, Gegenprobe ----------
def cross_check(cab: dict, rows: list) -> list:
    mine = [r for r in rows if r["cab"] == cab["cab"]]
    if not mine:
        raise Mismatch("%s steht nicht in der Liste der Bundesregierungen" % cab["cab"])
    problems = []
    if mine[0]["who"] != cab["who"]:
        problems.append("Kanzler: Infobox '%s' / Liste '%s'" % (cab["who"], mine[0]["who"]))
    if mine[0]["from"] != cab["from"]:
        problems.append("Beginn: Infobox %s / Liste %s" % (cab["from"], mine[0]["from"]))
    if mine[-1]["to"] != cab["to"]:
        problems.append("Ende: Infobox %s / Liste %s" % (cab["to"], mine[-1]["to"]))
    groups = []  # aufeinanderfolgende Zeilen mit gleicher Koalition (Vizekanzlerwechsel) zusammenfassen
    for r in mine:
        if not groups or groups[-1]["co"] != r["co"]:
            groups.append({"co": r["co"], "from": r["from"]})
    if [(g["co"], g["from"]) for g in groups] != [(p["co"], p["from"]) for p in cab["phases"]]:
        problems.append("Koalitionen: Infobox %s / Liste %s" % (
            [(p["co"], p["from"]) for p in cab["phases"]], [(g["co"], g["from"]) for g in groups]))
    return ["%s: %s" % (cab["cab"], p) for p in problems]


def coalition_label(cab: dict) -> str:
    name = cab["phases"][-1]["coalition"]
    if name and not re.search(r"Kabinett", name):
        return name[0].upper() + name[1:]
    return " + ".join(PARTY_LABEL[k] for k in cab["phases"][-1]["co"]) + "-Koalition"


def phases_out(cab: dict) -> list:
    out = []
    for i, p in enumerate(cab["phases"]):
        ph = {"from": p["from"], "to": p["to"], "co": p["co"]}
        if i > 0:
            left = [PARTY_LABEL[k] for k in cab["phases"][i - 1]["co"] if k not in p["co"]]
            if left:
                ph["nm"] = "ohne " + " und ".join(left)
        out.append(ph)
    return out


def elections() -> list:
    if not CSV_PATH.exists():
        return []
    with CSV_PATH.open(encoding="utf-8", newline="") as fh:
        return sorted(r["date"] for r in csv.DictReader(fh) if r["election"] == "1")


def long_date(iso: str) -> str:
    y, m, d = (int(x) for x in iso.split("-"))
    return "%d. %s %d" % (d, MONTHS[m - 1], y)


def current_block(cab: dict, rows: list) -> dict:
    last = [r for r in rows if r["cab"] == cab["cab"]][-1]
    wp = last["who_party"]
    if wp is None or wp not in cab["phases"][-1]["co"]:
        raise Mismatch("%s: Partei des Kanzlers (%s) nicht unter den Koalitionsparteien" % (cab["cab"], wp))
    female = cab["title"].endswith("in")
    lead = "die Union" if wp == "cdu" else "die " + PARTY_LABEL[wp]
    block = {
        "koalitionsname": coalition_label(cab),
        "kanzler_zusatz": "%s · %s stellt %s" % (PARTY_LABEL[wp], lead, "die Kanzlerin" if female else "den Kanzler"),
    }
    if last["vice"]:
        ministry = re.search(r"Stellvertreter des Bundeskanzlers[^\n]*?<br\s*/?>\s*\[\[(Bundesministerium[^\]|]*)", cab["text"])
        party = PARTY_LABEL.get(last["vice_party"], "")
        extra = " · ".join(x for x in (party, ("leitet zugleich das %s" % ministry.group(1).strip()) if ministry else "") if x)
        block["vizekanzler"] = {"titel": "Vizekanzler", "name": last["vice"], "partei": last["vice_party"], "zusatz": extra}
    before = [d for d in elections() if d < cab["from"]]
    if before and (dt.date.fromisoformat(cab["from"]) - dt.date.fromisoformat(before[-1])).days < 300:
        block["seit_zusatz"] = "Wahl im Bundestag nach der Bundestagswahl vom " + long_date(before[-1])
    # „Zuletzt“: jüngster Abschnitt „Kabinettsumbildung <Jahr>“ im Artikel, Monat aus dem ersten Datum darin
    sections = re.findall(r"^==\s*(Kabinettsumbildung[^=\n]*?)\s*==\s*\n(.*?)(?=^==[^=]|\Z)", cab["text"], re.S | re.M)
    if sections:
        heading, body = sections[-1]
        year = re.search(r"\d{4}", heading)
        month = re.search(r"\d{1,2}\.\s*(%s)\s+(\d{4})" % "|".join(MONTHS), body)
        if month:
            block["zuletzt"] = "Kabinettsumbildung im %s %s" % (month.group(1), month.group(2))
        elif year:
            block["zuletzt"] = "Kabinettsumbildung " + year.group(0)
    return block


def build() -> dict:
    cabinets = read_cabinets()
    rows = read_list()
    problems = [p for c in cabinets for p in cross_check(c, rows)]
    if problems:
        raise Mismatch("Infobox und Liste widersprechen sich:\n  " + "\n  ".join(problems))
    kabinette = []
    for c in cabinets:
        wp = next(r for r in rows if r["cab"] == c["cab"])["who_party"]
        if wp not in c["phases"][0]["co"]:
            raise Mismatch("%s: Partei des Kanzlers (%s) nicht unter den Koalitionsparteien" % (c["cab"], wp))
        kabinette.append({"name": c["name"], "cab": c["cab"], "title": c["title"], "who": c["who"], "wp": wp,
                          "from": c["from"], "to": c["to"], "ph": phases_out(c)})
    current = cabinets[-1]
    if current["to"] is not None:
        raise Mismatch("Das jüngste Kabinett (%s) hat ein Enddatum, ein Nachfolger fehlt in der Kette" % current["cab"])
    return {
        "stand": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d"),
        "quelle": "https://de.wikipedia.org/wiki/" + urllib.parse.quote(LIST_ARTICLE.replace(" ", "_")),
        "aktuell": current_block(current, rows),
        "kabinette": kabinette,
    }


def dump(obj: dict) -> str:
    text = json.dumps(obj, ensure_ascii=False, indent=2)
    # kurze String-Listen (Koalitionsparteien) in einer Zeile halten
    text = re.sub(r'\[\s+("[^"\]]*"(?:,\s+"[^"\]]*")*)\s+\]', lambda m: "[" + re.sub(r"\s+", " ", m.group(1)) + "]", text)
    return text + "\n"


def fail(message: str) -> int:
    # In GitHub Actions wird "::error::" als Annotation an den Lauf gehängt
    print(("::error::" if os.environ.get("GITHUB_ACTIONS") else "") + message, file=sys.stderr)
    return 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="nur den Unterschied zur vorhandenen JSON anzeigen")
    args = ap.parse_args()
    try:
        new = dump(build())
    except Mismatch as exc:
        return fail("Regierungsdaten nicht aktualisiert: %s" % exc)
    except Exception as exc:  # noqa: BLE001 - Netzwerk- und Formatfehler sollen den Lauf sichtbar scheitern lassen
        return fail("Regierungsdaten nicht aktualisiert (%s): %s" % (type(exc).__name__, exc))
    old_obj = json.loads(JSON_PATH.read_text(encoding="utf-8")) if JSON_PATH.exists() else {}
    diff = list(difflib.unified_diff(dump(old_obj).splitlines(), new.splitlines(), "bisher", "neu", lineterm="", n=1)) if old_obj else []
    # der Stand ändert sich bei jedem Lauf; inhaltlich zählt nur der Rest
    changed = [d for d in diff if d[:1] in "+-" and not d.startswith(("+++", "---")) and '"stand"' not in d]
    if args.dry_run:
        print("\n".join(diff) if changed else "Keine inhaltlichen Unterschiede.")
        return 0
    JSON_PATH.write_text(new, encoding="utf-8")
    if changed:
        print("data/regierungen.json: inhaltlich geändert")
        print("\n".join(diff))
    else:
        print("data/regierungen.json: inhaltlich unverändert (nur Stand aktualisiert)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

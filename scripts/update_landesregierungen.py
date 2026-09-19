#!/usr/bin/env python3
"""Erzeugt data/landesregierungen.json aus der deutschen Wikipedia.

Quellen:
  1. Der Artikel „Liste der Ministerpräsidenten der deutschen Länder“. Je Land enthält er eine Tabelle
     mit allen Regierungschefs, ihrer Partei und den Kabinetten. Daraus stammen die Kabinettstitel
     und die Partei des Regierungschefs. Neue Kabinette erscheinen dort von selbst.
  2. Die Infobox jedes Kabinettsartikels („Kabinett Söder III“, „Senat Wegner“ …). Daraus stammen
     Regierungschef, Amtsantritt und Ende sowie die Koalitionsparteien (auch Wechsel während der
     Amtszeit, etwa „bis 22. November 2024, danach ohne Bündnis 90/Die Grünen“).

Die beiden Quellen werden gegeneinander geprüft: lückenlose Amtszeiten ohne Überschneidung,
Regierungschef laut Infobox gleich dem laut Liste. Fehlt ein Artikel, ist eine Infobox unlesbar oder
widersprechen sich die Quellen deutlich, bricht das Skript mit Fehlercode 1 ab und lässt die JSON
unberührt. Kleinere Auffälligkeiten (z. B. kommissarische Zwischenzeiten) erscheinen als Warnung.

    python scripts/update_landesregierungen.py             # JSON aktualisieren
    python scripts/update_landesregierungen.py --dry-run   # nur anzeigen, was sich ändern würde
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

from wikitext import MONTHS, Mismatch, expand, first_link_name, german_date, infobox, parse_wikitable, plain, wikitext, wikitexts

ROOT = Path(__file__).resolve().parent.parent
JSON_PATH = ROOT / "data" / "landesregierungen.json"
CSV_PATH = ROOT / "data" / "landtage.csv"
LIST_ARTICLE = "Liste der Ministerpräsidenten der deutschen Länder"
EARLIEST = "1989-01-01"  # Kabinette, die vorher endeten, spielen für die Umfragedaten keine Rolle

# (Kürzel der Seite bei wahlrecht.de, Abschnitt im Wikipedia-Artikel, Bezeichnung der Wahl)
LAENDER = [
    ("baden-wuerttemberg", "Baden-Württemberg", "Landtagswahl"), ("bayern", "Bayern", "Landtagswahl"),
    ("berlin", "Berlin", "Abgeordnetenhauswahl"), ("brandenburg", "Brandenburg", "Landtagswahl"),
    ("bremen", "Bremen", "Bürgerschaftswahl"), ("hamburg", "Hamburg", "Bürgerschaftswahl"),
    ("hessen", "Hessen", "Landtagswahl"), ("mecklenburg-vorpommern", "Mecklenburg-Vorpommern", "Landtagswahl"),
    ("niedersachsen", "Niedersachsen", "Landtagswahl"), ("nrw", "Nordrhein-Westfalen", "Landtagswahl"),
    ("rheinland-pfalz", "Rheinland-Pfalz", "Landtagswahl"), ("saarland", "Saarland", "Landtagswahl"),
    ("sachsen", "Sachsen", "Landtagswahl"), ("sachsen-anhalt", "Sachsen-Anhalt", "Landtagswahl"),
    ("schleswig-holstein", "Schleswig-Holstein", "Landtagswahl"), ("thueringen", "Thüringen", "Landtagswahl"),
]
# Kürzel, die die Seite kennt, samt Anzeigename. Alle anderen Parteien erscheinen als "x-<name>" in "parteien".
LABEL = {"cdu": "CDU", "spd": "SPD", "gru": "GRÜNE", "fdp": "FDP", "lin": "LINKE", "afd": "AfD", "bsw": "BSW",
         "fw": "FW", "ssw": "SSW", "pir": "PIRATEN"}
warnings: list = []


def warn(message: str) -> None:
    warnings.append(message)
    print(("::warning::" if os.environ.get("GITHUB_ACTIONS") else "Warnung: ") + message, file=sys.stderr)


# ---------- Parteien ----------
def party_key(token: str, registry: dict) -> str:
    t = token.strip().lower()
    if re.fullmatch(r"cdu|csu|union", t):
        return "cdu"
    if t == "spd":
        return "spd"
    if "grün" in t or t in ("gal", "al", "b’90/grüne", "b'90/grüne") or t.startswith("bündnis 90"):
        return "gru"
    if "fdp" in t or t in ("dps", "fdp/dps", "fdp/dvp"):
        return "fdp"
    if "linke" in t or "pds" in t:
        return "lin"
    if t == "afd":
        return "afd"
    if t == "bsw":
        return "bsw"
    if t in ("fw", "freie wähler", "bvb/fw") or t.startswith("freie wähler"):
        return "fw"
    if t == "ssw":
        return "ssw"
    if "piraten" in t:
        return "pir"
    key = "x-" + re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    registry[key] = token.strip()
    return key


def split_parties(text: str, registry: dict) -> list:
    text = re.sub(r"B(?:ündnis|’|')\s*90\s*/\s*(?:Die )?Grünen?", "Grüne", text, flags=re.I)
    text = re.sub(r"CDU\s*/\s*CSU", "CDU", text)
    text = re.sub(r"FDP\s*/\s*(?:DPS|DVP)", "FDP", text)
    keys = []
    for token in re.split(r",|\bund\b|\+", text):
        token = re.sub(r"-Alleinregierung$", "", token.strip())  # "SPD-Alleinregierung"
        if token and not token.lower().startswith(("minderheits", "gestützt", "ab ", "zuvor")):
            k = party_key(token, registry)
            if k not in keys:
                keys.append(k)
    return keys


def coalition_phases(raw: str, start: str, end, title: str, registry: dict) -> list:
    """Koalitionsfeld -> Phasen [{from, to, co, coalition, nm}]."""
    link = re.search(r"\[\[([^\]|]+)\|", raw)
    coalition = link.group(1) if link else ""
    text = plain(raw)
    note = None
    if re.search(r"Minderheitsregierung", text):
        note = "Minderheitsregierung"
    elif re.search(r"gestützt von", text):
        note = re.search(r"gestützt von[^)]*", text).group(0)
    split = re.search(r"\(bis (\d{1,2}\.\s*\w+\s+\d{4}), danach ohne ([^)]+)\)", text)
    text = re.sub(r"\((?:[^()]|\([^()]*\))*\)", "", text) if not split else re.sub(r"\(bis[^)]*\)", "", text)
    text = re.sub(r"\s+", " ", text).strip(" ,")
    keys = split_parties(text, registry)
    if not keys:
        raise Mismatch("%s: keine Koalitionsparteien in '%s'" % (title, plain(raw)))
    phases = [{"from": start, "to": end, "co": keys, "coalition": coalition, "nm": note}]
    if split:
        boundary = german_date(split.group(1))
        left = set(split_parties(split.group(2), registry))
        rest = [k for k in keys if k not in left]
        if boundary is None or not rest:
            raise Mismatch("%s: Koalitionswechsel nicht lesbar: %s" % (title, plain(raw)))
        phases = [{"from": start, "to": boundary, "co": keys, "coalition": coalition, "nm": None},
                  {"from": boundary, "to": end, "co": rest, "coalition": coalition,
                   "nm": "ohne " + " und ".join(LABEL.get(k) or registry[k] for k in keys if k in left)}]
    return phases


# ---------- Liste der Ministerpräsidenten ----------
def read_list(registry: dict) -> dict:
    _, text = wikitext(LIST_ARTICLE)
    out = {}
    headings = [(m.group(2).strip(), m.start()) for m in re.finditer(r"^(={2,3})\s*([^=\n]+?)\s*\1\s*$", text, re.M)]
    for slug, section, _ in LAENDER:
        starts = [i for i, (name, _) in enumerate(headings) if name == section]
        if not starts:
            raise Mismatch("Abschnitt '%s' fehlt in der Liste der Ministerpräsidenten" % section)
        i = starts[0]
        body = text[headings[i][1]: headings[i + 1][1] if i + 1 < len(headings) else len(text)]
        cabinets = []
        for chunk in re.findall(r"\{\|.*?\n\|\}", body, re.S):
            grid = expand(parse_wikitable(chunk))
            ci = person = None  # eine Tabelle kann mehrere Kopfzeilen haben (z. B. Berlin: Magistrat, später Senat)
            for r in grid:
                if any(plain(c) == "Amtszeit" for c in r):
                    hdr = [plain(c) for c in r]
                    ci = {"Amtszeit": hdr.index("Amtszeit"), "Partei": hdr.index("Partei"),
                          "Regierung": next(i for i, c in enumerate(hdr) if c in ("Regierung", "Senat", "Kabinett", "Magistrat"))}
                    person = next(i for i, c in enumerate(hdr) if i not in ci.values() and c not in ("Anmerkungen", "Bild"))
                    width = len(hdr)
                    continue
                if ci is None or len(r) < width or len(set(r)) == 1:  # Zwischenüberschriften ("1945 bis 1948:")
                    continue
                years = re.findall(r"\d{4}", plain(r[ci["Amtszeit"]]))
                if not years or (int(years[-1]) < 1989 and "Seit" not in r[ci["Amtszeit"]]):
                    continue
                titles = [t.strip() for t in re.findall(r"\[\[((?:Kabinett|Senat) [^\]|]+)", r[ci["Regierung"]])]
                who = first_link_name(r[person]) if "[[" in r[person] else plain(r[person])
                for title in titles:
                    if all(c["title"] != title for c in cabinets):
                        cabinets.append({"title": title, "mp": who, "party": party_key(re.sub(r"\s*\(.*", "", plain(r[ci["Partei"]])) or "?", registry)})
        if not cabinets:
            raise Mismatch("%s: keine Kabinette in der Liste gefunden" % section)
        out[slug] = cabinets
    return out


# ---------- Zusammensetzen ----------
def elections(slug: str) -> list:
    if not CSV_PATH.exists():
        return []
    with CSV_PATH.open(encoding="utf-8", newline="") as fh:
        return sorted({r["date"] for r in csv.DictReader(fh) if r["land"] == slug and r["election"] == "1"})


def long_date(iso: str) -> str:
    y, m, d = (int(x) for x in iso.split("-"))
    return "%d. %s %d" % (d, MONTHS[m - 1], y)


def build_state(slug: str, section: str, election_name: str, listed: list, pages: dict, registry: dict) -> dict:
    cabinets = []
    for entry in listed:
        canonical, text = pages[entry["title"]]
        box = infobox(text, canonical)
        start, end = box.get("Beginn", ""), box.get("Ende") or None
        if not re.fullmatch(r"\d{4}-\d\d-\d\d", start):
            raise Mismatch("%s: Beginn nicht im Format JJJJ-MM-TT ('%s')" % (canonical, start))
        if end and not re.fullmatch(r"\d{4}-\d\d-\d\d", end):
            # Tippfehler in der Wikipedia (z. B. "1996-06-1"): das Ende folgt dann aus dem Beginn des Nachfolgers
            warn("%s: Ende '%s' ist kein gültiges Datum, es wird der Beginn des Nachfolgers verwendet" % (canonical, end))
            end = "?"
        elif end and end < EARLIEST:
            continue
        phases = coalition_phases(box.get("Koalition", ""), start, end, canonical, registry)
        who = first_link_name(box.get("Chef", "")) if "[[" in box.get("Chef", "") else plain(box.get("Chef", ""))
        if who != entry["mp"]:
            warn("%s: Regierungschef laut Infobox '%s', laut Liste '%s'" % (canonical, who, entry["mp"]))
        cabinets.append({
            "name": re.sub(r"^(Kabinett|Senat) ", "", canonical), "cab": canonical,
            "title": plain(box.get("Titel Chef", "")) or "Regierungschef", "who": who, "wp": entry["party"],
            "from": start, "to": end, "phases": phases,
        })
    cabinets.sort(key=lambda c: c["from"])
    if not cabinets:
        raise Mismatch("%s: keine Kabinette seit %s" % (section, EARLIEST))
    for prev, cur in zip(cabinets, cabinets[1:]):
        if prev["to"] == "?":
            prev["to"] = cur["from"]
            prev["phases"][-1]["to"] = cur["from"]
    for prev, cur in zip(cabinets, cabinets[1:]):
        if prev["to"] is None:
            raise Mismatch("%s: %s hat kein Ende, aber %s folgt" % (section, prev["cab"], cur["cab"]))
        gap = (dt.date.fromisoformat(cur["from"]) - dt.date.fromisoformat(prev["to"])).days
        if gap < 0:
            warn("%s: %s beginnt %d Tage vor dem Ende von %s" % (section, cur["cab"], -gap, prev["cab"]))
        elif gap > 60:
            raise Mismatch("%s: Lücke von %d Tagen zwischen %s und %s" % (section, gap, prev["cab"], cur["cab"]))
    if cabinets[-1]["to"] is not None:
        raise Mismatch("%s: das jüngste Kabinett (%s) hat ein Enddatum" % (section, cabinets[-1]["cab"]))
    out = []
    for c in cabinets:
        out.append({"name": c["name"], "cab": c["cab"], "title": c["title"], "who": c["who"], "wp": c["wp"],
                    "from": c["from"], "to": c["to"],
                    "ph": [dict({"from": p["from"], "to": p["to"], "co": p["co"]}, **({"nm": p["nm"]} if p["nm"] else {}))
                           for p in c["phases"]]})
    last, block = cabinets[-1], {}
    label = last["phases"][-1]["coalition"]
    block["koalitionsname"] = (label[0].upper() + label[1:]) if label else ""
    before = [d for d in elections(slug) if d < last["from"]]
    if before and (dt.date.fromisoformat(last["from"]) - dt.date.fromisoformat(before[-1])).days < 300:
        block["seit_zusatz"] = "Regierungsbildung nach der %s vom %s" % (election_name, long_date(before[-1]))
    return {"name": section, "wahl": election_name, "aktuell": block, "kabinette": out}


def build() -> dict:
    registry: dict = {}
    listed = read_list(registry)
    titles = sorted({e["title"] for lst in listed.values() for e in lst})
    pages = wikitexts(titles)
    laender = {}
    for slug, section, election_name in LAENDER:
        laender[slug] = build_state(slug, section, election_name, listed[slug], pages, registry)
    used = {k for L in laender.values() for c in L["kabinette"] for k in [c["wp"]] + [x for p in c["ph"] for x in p["co"]]}
    registry = {k: v for k, v in registry.items() if k in used}
    return {
        "stand": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d"),
        "quelle": "https://de.wikipedia.org/wiki/" + urllib.parse.quote(LIST_ARTICLE.replace(" ", "_")),
        "parteien": {k: v for k, v in sorted(registry.items())},
        "laender": laender,
    }


def dump(obj: dict) -> str:
    text = json.dumps(obj, ensure_ascii=False, indent=1)
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
        return fail("Landesregierungen nicht aktualisiert: %s" % exc)
    except Exception as exc:  # noqa: BLE001 - Netzwerk- und Formatfehler sollen den Lauf sichtbar scheitern lassen
        return fail("Landesregierungen nicht aktualisiert (%s): %s" % (type(exc).__name__, exc))
    old_obj = json.loads(JSON_PATH.read_text(encoding="utf-8")) if JSON_PATH.exists() else {}
    diff = list(difflib.unified_diff(dump(old_obj).splitlines(), new.splitlines(), "bisher", "neu", lineterm="", n=1)) if old_obj else []
    changed = [d for d in diff if d[:1] in "+-" and not d.startswith(("+++", "---")) and '"stand"' not in d]
    if args.dry_run:
        print("\n".join(diff) if changed else ("Keine inhaltlichen Unterschiede." if old_obj else new))
        return 0
    JSON_PATH.write_text(new, encoding="utf-8")
    print("data/landesregierungen.json: %s (%d Warnungen)" % ("inhaltlich geändert" if changed else "inhaltlich unverändert (nur Stand aktualisiert)", len(warnings)))
    return 0


if __name__ == "__main__":
    sys.exit(main())

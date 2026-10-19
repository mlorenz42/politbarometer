#!/usr/bin/env python3
"""Baut docs/index.html und docs/laender.html aus den src/-Vorlagen und den data/*.json/csv-Dateien
(Umfragen, Regierungen, Landtagsumfragen, Landesregierungen, Sitzverteilung).

Die Seite ist eigenständig (keine Nachladeanfragen): Umfragewerte und Regierungsdaten
werden direkt ins HTML eingebettet. Die Ausgabe ist deterministisch, damit ein Lauf
ohne neue Daten keinen Commit erzeugt.
"""
from __future__ import annotations

import csv
import datetime
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


def load_sitze() -> dict:
    return json.loads((ROOT / "data" / "sitze.json").read_text(encoding="utf-8"))


def load_land_meta() -> list:
    meta = json.loads((ROOT / "data" / "laender.json").read_text(encoding="utf-8"))
    return [{"slug": l["slug"], "name": l["name"], "union": "CSU" if l["slug"] == "bayern" else "CDU"} for l in meta]


def load_germany_paths() -> dict:
    return json.loads((ROOT / "data" / "germany-paths.json").read_text(encoding="utf-8"))


def build_sitzverteilung(sitze: dict) -> int:
    laender_meta = load_land_meta()
    germany = load_germany_paths()
    template = (ROOT / "src" / "sitzverteilung.html").read_text(encoding="utf-8")
    for marker in ("/*SITZE*/{}", "/*LAENDER*/[]", "/*GERMANY*/{}", "/*COMMON_CSS*/", "/*COMMON_JS*/"):
        if template.count(marker) != 1:
            print("Platzhalter %s im Sitzverteilung-Template nicht genau einmal vorhanden." % marker, file=sys.stderr)
            return 1
    out = template.replace("/*SITZE*/{}", embed(sitze)).replace("/*LAENDER*/[]", embed(laender_meta))
    out = out.replace("/*GERMANY*/{}", embed(germany))
    out = out.replace("/*COMMON_CSS*/", (ROOT / "src" / "common.css").read_text(encoding="utf-8").rstrip("\n"))
    out = out.replace("/*COMMON_JS*/", (ROOT / "src" / "common.js").read_text(encoding="utf-8").rstrip("\n"))
    (ROOT / "docs" / "sitzverteilung.html").write_text(out, encoding="utf-8")
    print("docs/sitzverteilung.html: %d Länder, %d KB" % (len(laender_meta), len(out) // 1024))
    return 0


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


def build_laender(sitze: dict) -> int:
    laender, gov = load_landtage()
    template = (ROOT / "src" / "laender.html").read_text(encoding="utf-8")
    for marker in ("/*LAENDER*/[]", "/*GOV*/{}", "/*SITZE*/{}", "/*COMMON_CSS*/", "/*COMMON_JS*/"):
        if template.count(marker) != 1:
            print("Platzhalter %s im Länder-Template nicht genau einmal vorhanden." % marker, file=sys.stderr)
            return 1
    sitze_land = {"stand": sitze["stand"], "laender": sitze["laender"]}
    out = template.replace("/*LAENDER*/[]", embed(laender)).replace("/*GOV*/{}", embed(gov))
    out = out.replace("/*SITZE*/{}", embed(sitze_land))
    out = out.replace("/*COMMON_CSS*/", (ROOT / "src" / "common.css").read_text(encoding="utf-8").rstrip("\n"))
    out = out.replace("/*COMMON_JS*/", (ROOT / "src" / "common.js").read_text(encoding="utf-8").rstrip("\n"))
    (ROOT / "docs" / "laender.html").write_text(out, encoding="utf-8")
    print("docs/laender.html: %d Länder, %d Zeilen, %d KB" % (len(laender), sum(len(l["rows"]) for l in laender), len(out) // 1024))
    return 0


# ---------- Prognose (lineare AfD-Trendfortschreibung) ----------
# Bewusst grobes Modell: gewöhnliche lineare Regression der letzten 2 Jahre Umfragen (Wahlergebnisse
# ausgenommen, die reagieren auf die Wahl selbst und würden die Steigung verzerren), nichts Ausgefeiltes.
# Der Sinn ist nicht, eine seriöse Prognose zu liefern (das kann eine Gerade durch Umfragepunkte nicht
# leisten – Umfragen verlaufen nicht linear, Wahlen setzen die Dynamik zurück, Ereignisse können alles
# ändern), sondern eine nachvollziehbare, mechanische Fortschreibung "wenn es exakt so weiterginge".
TREND_WINDOW_DAYS = 730  # 2 Jahre
MAJORITY_THRESHOLD = 45.0  # Hilfsgröße statt 50 %, weil der Sitzanteil auch von der 5-%-Hürde bei den übrigen Parteien abhängt
GERMAN_MONTHS = {"Januar": 1, "Februar": 2, "März": 3, "April": 4, "Mai": 5, "Juni": 6, "Juli": 7,
                 "August": 8, "September": 9, "Oktober": 10, "November": 11, "Dezember": 12}
SEASON_MONTH = {"Frühjahr": 4, "Sommer": 7, "Herbst": 10, "Winter": 1}


def _linreg(points: list) -> tuple | None:
    n = len(points)
    if n < 4:
        return None
    sx = sum(p[0] for p in points)
    sy = sum(p[1] for p in points)
    sxx = sum(p[0] * p[0] for p in points)
    sxy = sum(p[0] * p[1] for p in points)
    denom = n * sxx - sx * sx
    if denom == 0:
        return None
    slope = (n * sxy - sx * sy) / denom
    return slope, (sy - slope * sx) / n


def _parse_wahltermin(text: str):
    # "18. April 2027" (genau) oder "Herbst 2028" (nur Jahreszeit, auf Monatsmitte der Jahreszeit gelegt) –
    # beides wie von wahlrecht.de notiert. Gibt None zurück, wenn das Format nicht erkannt wird.
    import re
    m = re.match(r"(\d{1,2})\.\s*(\w+)\s*(\d{4})", text)
    if m and m.group(2) in GERMAN_MONTHS:
        return datetime.date(int(m.group(3)), GERMAN_MONTHS[m.group(2)], int(m.group(1))), True
    m = re.match(r"(\w+)\s*(\d{4})", text)
    if m and m.group(1) in SEASON_MONTH:
        return datetime.date(int(m.group(2)), SEASON_MONTH[m.group(1)], 15), False
    return None, False


def build_prognose() -> int:
    land_meta = json.loads((ROOT / "data" / "laender.json").read_text(encoding="utf-8"))
    with (ROOT / "data" / "landtage.csv").open(encoding="utf-8", newline="") as fh:
        records = list(csv.DictReader(fh))
    by_land: dict = {}
    for r in records:
        by_land.setdefault(r["land"], []).append(r)

    today = datetime.date.today()
    cutoff = today - datetime.timedelta(days=TREND_WINDOW_DAYS)
    out = []
    for land in land_meta:
        slug = land["slug"]
        polls = sorted((r for r in by_land.get(slug, []) if r["election"] == "0"), key=lambda r: r["date"])
        if len(polls) < 4:
            continue

        def series(col: str) -> list:
            pts = []
            for r in polls:
                v = value(r[col])
                if v is None:
                    continue
                pts.append((datetime.date.fromisoformat(r["date"]), v))
            return pts

        def trend(col: str):
            pts = series(col)
            if not pts:
                return None, None
            recent = [p for p in pts if p[0] >= cutoff]
            if len(recent) < 6:  # zu wenige Umfragen im Zeitfenster (manche Länder werden selten umfragt)
                recent = pts[-20:]
            fit = _linreg([((dt - today).days, v) for dt, v in recent])
            return pts[-1][1], fit  # (letzter Wert, (Steigung/Tag, Achsenabschnitt) oder None)

        afd_cur, afd_fit = trend("AfD")
        if afd_cur is None:
            continue
        last_poll_date = polls[-1]["date"]

        # Aktuell führende Partei: Schnitt der letzten 5 Umfragen über alle Parteien hinweg.
        last5 = polls[-5:]
        sums, counts = {}, {}
        for r in last5:
            for key, col in LAND_PLOTTED:
                v = value(r[col])
                if v is not None:
                    sums[key] = sums.get(key, 0) + v
                    counts[key] = counts.get(key, 0) + 1
        cur_avg = {k: sums[k] / counts[k] for k in sums}
        leader = max(cur_avg, key=cur_avg.get) if cur_avg else None
        leader_label = ("CSU" if slug == "bayern" else "CDU/CSU") if leader == "cdu" else dict(LAND_PLOTTED).get(leader, leader)

        stark_datum = None
        if leader != "afd" and afd_fit and leader:
            leader_cur, leader_fit = trend(dict(LAND_PLOTTED)[leader])
            if leader_fit:
                a_slope, a_int = afd_fit
                l_slope, l_int = leader_fit
                rel = a_slope - l_slope
                if rel > 0:
                    x = (l_int - a_int) / rel
                    if x > 0:
                        stark_datum = (today + datetime.timedelta(days=x)).strftime("%Y-%m")

        mehrheit_datum = None
        if afd_fit:
            a_slope, a_int = afd_fit
            if a_slope > 0:
                x = (MAJORITY_THRESHOLD - a_int) / a_slope
                if x > 0:
                    mehrheit_datum = (today + datetime.timedelta(days=x)).strftime("%Y-%m")

        next_text = land["naechste_wahl"]
        next_date, next_exact = _parse_wahltermin(next_text)
        vor_naechster_wahl = None
        if next_date and (stark_datum or mehrheit_datum):
            ziel = stark_datum or mehrheit_datum
            ziel_date = datetime.date(int(ziel[:4]), int(ziel[5:7]), 1)
            vor_naechster_wahl = ziel_date <= next_date

        out.append({
            "slug": slug, "name": land["name"], "stand": last_poll_date,
            "afd_aktuell": round(afd_cur, 1), "afd_trend_jahr": round(afd_fit[0] * 365, 2) if afd_fit else None,
            "fuehrend": leader, "fuehrend_label": leader_label,
            "fuehrend_aktuell": round(cur_avg[leader], 1) if leader else None,
            "bereits_fuehrend": leader == "afd",
            "stark_datum": stark_datum, "mehrheit_datum": mehrheit_datum,
            "naechste_wahl": next_text, "naechste_wahl_exakt": next_exact,
            "naechste_wahl_monat": next_date.strftime("%Y-%m") if next_date else None,
            "vor_naechster_wahl": vor_naechster_wahl,
        })

    def sort_key(e):
        d = e["stark_datum"] or e["mehrheit_datum"]
        if e["bereits_fuehrend"]:
            return (0, e["mehrheit_datum"] or "0000-00")
        if d:
            return (1, d)
        return (2, e["name"])
    out.sort(key=sort_key)

    data = {"stand": today.isoformat(), "fenster_tage": TREND_WINDOW_DAYS, "schwelle": MAJORITY_THRESHOLD, "laender": out}
    (ROOT / "data" / "prognose.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    template = (ROOT / "src" / "prognose.html").read_text(encoding="utf-8")
    for marker in ("/*PROGNOSE*/{}", "/*COMMON_CSS*/", "/*COMMON_JS*/"):
        if template.count(marker) != 1:
            print("Platzhalter %s im Prognose-Template nicht genau einmal vorhanden." % marker, file=sys.stderr)
            return 1
    html = template.replace("/*PROGNOSE*/{}", embed(data))
    html = html.replace("/*COMMON_CSS*/", (ROOT / "src" / "common.css").read_text(encoding="utf-8").rstrip("\n"))
    html = html.replace("/*COMMON_JS*/", (ROOT / "src" / "common.js").read_text(encoding="utf-8").rstrip("\n"))
    (ROOT / "docs" / "prognose.html").write_text(html, encoding="utf-8")
    print("docs/prognose.html: %d Länder" % len(out))
    return 0


def main() -> int:
    rows = load_rows()
    if len(rows) < 400:
        print("Nur %d Umfragezeilen, das sieht nicht plausibel aus." % len(rows), file=sys.stderr)
        return 1
    gov = json.loads((ROOT / "data" / "regierungen.json").read_text(encoding="utf-8"))
    sitze = load_sitze()
    template = (ROOT / "src" / "template.html").read_text(encoding="utf-8")
    for marker in ("/*DATA*/[]", "/*GOV*/{}", "/*SITZE*/{}"):
        if template.count(marker) != 1:
            print("Platzhalter %s im Template nicht genau einmal vorhanden." % marker, file=sys.stderr)
            return 1
    sitze_bund = {"stand": sitze["stand"], "bund": sitze["bund"]}
    out = template.replace("/*DATA*/[]", embed(rows)).replace("/*GOV*/{}", embed(gov))
    out = out.replace("/*SITZE*/{}", embed(sitze_bund))
    out = out.replace("/*COMMON_CSS*/", (ROOT / "src" / "common.css").read_text(encoding="utf-8").rstrip("\n"))
    out = out.replace("/*COMMON_JS*/", (ROOT / "src" / "common.js").read_text(encoding="utf-8").rstrip("\n"))
    target = ROOT / "docs" / "index.html"
    target.parent.mkdir(exist_ok=True)
    target.write_text(out, encoding="utf-8")
    print("docs/index.html: %d Umfragezeilen, %d Kabinette, %d KB" % (len(rows), len(gov["kabinette"]), len(out) // 1024))
    code = build_laender(sitze)
    code = code or build_sitzverteilung(sitze)
    return code or build_prognose()


if __name__ == "__main__":
    sys.exit(main())

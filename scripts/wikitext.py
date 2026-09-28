"""Gemeinsame Helfer zum Lesen der deutschen Wikipedia (Wikitext, Infoboxen, Tabellen).

Genutzt von update_regierungen.py (Bundesregierung) und update_landesregierungen.py (Länder).
"""
from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request

API = "https://de.wikipedia.org/w/api.php"
USER_AGENT = "politbarometer-verlauf/1.0 (https://github.com/mlorenz42/politbarometer)"
MONTHS = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November", "Dezember"]


class Mismatch(Exception):
    """Die Quellen widersprechen sich oder haben ein unerwartetes Format."""


# ---------- Abruf ----------
_last_request = [0.0]


def _query(titles: str) -> dict:
    wait = 1.0 - (time.time() - _last_request[0])  # höflich: höchstens eine Anfrage pro Sekunde
    if wait > 0:
        time.sleep(wait)
    query = urllib.parse.urlencode({
        "action": "query", "prop": "revisions", "rvprop": "content", "rvslots": "main",
        "titles": titles, "redirects": 1, "format": "json", "formatversion": 2,
    })
    req = urllib.request.Request(API + "?" + query, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.load(resp)
    _last_request[0] = time.time()
    return data["query"]


def wikitext(title: str) -> tuple:
    """(kanonischer Titel, Wikitext) eines Artikels."""
    return wikitexts([title])[title]


def wikitexts(titles: list) -> dict:
    """Mehrere Artikel in wenigen Anfragen. Ergebnis: angefragter Titel -> (kanonischer Titel, Wikitext)."""
    out = {}
    for i in range(0, len(titles), 20):
        batch = titles[i:i + 20]
        q = _query("|".join(batch))
        alias = {}
        for kind in ("normalized", "redirects"):
            for m in q.get(kind, []):
                alias[m["from"]] = m["to"]
        pages = {p["title"]: p for p in q["pages"]}
        for title in batch:
            canonical = title
            for _ in range(3):
                canonical = alias.get(canonical, canonical)
            page = pages.get(canonical)
            if page is None or page.get("missing"):
                raise Mismatch("Wikipedia-Artikel '%s' nicht gefunden" % title)
            out[title] = (page["title"], page["revisions"][0]["slots"]["main"]["content"])
    return out


# ---------- Wikitext-Helfer ----------
def plain(s: str) -> str:
    s = re.sub(r"<ref[^>]*/>|<ref[^>]*>.*?</ref>", "", s, flags=re.S)
    s = re.sub(r"<br\s*/?>", " ", s)
    s = re.sub(r"</?small[^>]*>", "", s)
    s = re.sub(r"\[\[[^\]|]*\|([^\]]*)\]\]", r"\1", s)
    s = re.sub(r"\[\[([^\]]*)\]\]", r"\1", s)
    s = re.sub(r"\{\{[^}]*\}\}", "", s)
    s = re.sub(r"'{2,}", "", s).replace("&nbsp;", " ")
    return re.sub(r"\s+", " ", s).strip()


def first_link_name(s: str) -> str:
    m = re.search(r"\[\[([^\]|]*)(?:\|([^\]]*))?\]\]", s)
    if not m:
        raise Mismatch("Kein Link in '%s'" % s[:60])
    return re.sub(r"\s*\([^)]*\)$", "", (m.group(2) or m.group(1)).strip())


def german_date(s: str):
    """'6. Mai 2025' -> '2025-05-06'; ''amtierend'' oder leer -> None."""
    m = re.search(r"(\d{1,2})\.\s*(%s)\s+(\d{4})" % "|".join(MONTHS), plain(s))
    if not m:
        return None
    return "%s-%02d-%02d" % (m.group(3), MONTHS.index(m.group(2)) + 1, int(m.group(1)))


def template_body(text: str, name: str):
    """Rohtext zwischen "{{name" und der zugehörigen schließenden "}}", klammertiefen-bewusst
    (eine Infobox kann selbst weitere {{…}}-Vorlagen enthalten, die ebenfalls mit "}}" enden –
    ein einfacher, nicht-gieriger Regex-Abschluss am ersten "}}" würde dort zu früh aufhören)."""
    marker = "{{" + name
    i = text.find(marker)
    if i < 0:
        return None
    i += len(marker)
    depth, j, n = 1, i, len(text)
    while j < n and depth > 0:
        two = text[j:j + 2]
        if two == "{{":
            depth += 1; j += 2
        elif two == "}}":
            depth -= 1; j += 2
        else:
            j += 1
    return text[i:j - 2] if depth == 0 else None


def infobox(text: str, title: str, name: str = "Infobox Regierung") -> dict:
    """Feld -> Wert der obersten Ebene einer Infobox. Ein Feldwert darf über mehrere Zeilen gehen
    (bis zur nächsten Zeile, die selbst mit "|…=" ein neues Feld beginnt); das deckt auch reinen
    Fließtext wie ein "Sitzverteilung ="-Feld ab, dessen Wert erst in der Folgezeile beginnt."""
    body = template_body(text, name)
    if body is None:
        raise Mismatch("%s: %s nicht gefunden" % (title, name))
    box: dict = {}
    key = None
    for line in body.split("\n"):
        mm = re.match(r"\|[ \t]*([^=|]+?)[ \t]*=[ \t]*(.*)$", line)
        if mm:
            key = mm.group(1)
            box[key] = mm.group(2)
        elif key is not None:
            box[key] += "\n" + line
    return {k: v.strip() for k, v in box.items()}


# ---------- Parteien ----------
# Kürzel, die die Grafik kennt, samt Anzeigename. Alle anderen Parteien erhalten ein "x-<name>"-Kürzel
# und werden in einer eigenen Registry gesammelt (grau dargestellt, siehe common.css ".p-x-*").
PARTY_LABEL = {"cdu": "CDU", "spd": "SPD", "gru": "GRÜNE", "fdp": "FDP", "lin": "LINKE", "afd": "AfD",
               "bsw": "BSW", "fw": "FW", "ssw": "SSW", "pir": "PIRATEN"}


def party_key(token: str, registry: dict) -> str:
    """Erkennt eine Partei aus ihrem (oft uneinheitlich geschriebenen) Namen in der Wikipedia."""
    t = re.sub(r"\s*\([^)]*\)", "", token).strip().lower()  # Landeskürzel abstreifen, z. B. "FW(BY)" -> "fw"
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


def split_top(s: str, seps: tuple) -> list:
    """Teilt an Trennzeichen außerhalb von [[…]] und {{…}}."""
    out, depth, buf, i = [], 0, "", 0
    while i < len(s):
        two = s[i:i + 2]
        if two in ("[[", "{{"):
            depth += 1; buf += two; i += 2; continue
        if two in ("]]", "}}"):
            depth -= 1; buf += two; i += 2; continue
        if depth == 0 and any(s.startswith(sep, i) for sep in seps):
            sep = next(sp for sp in seps if s.startswith(sp, i))
            out.append(buf); buf = ""; i += len(sep); continue
        buf += s[i]; i += 1
    out.append(buf)
    return out


def parse_wikitable(text: str) -> list:
    start = text.index("{|")
    end = text.index("\n|}", start)
    rows, cur = [], None
    for line in text[start:end].split("\n")[1:]:
        if line.startswith("|-"):
            cur = []; rows.append(cur); continue
        if line.startswith("|+"):
            continue
        if line[:1] in ("|", "!"):
            if cur is None:
                cur = []; rows.append(cur)
            for cell in split_top(line[1:], ("||", "!!")):
                bits = split_top(cell, ("|",))
                attrs, content = ("", cell)
                if len(bits) > 1 and "=" in bits[0] and "[[" not in bits[0]:
                    attrs, content = bits[0], "|".join(bits[1:])
                cur.append((attrs, content.strip()))
        elif cur:
            attrs, content = cur[-1]
            cur[-1] = (attrs, content + "\n" + line)
    return rows


def expand(rows: list) -> list:
    grid, carry = [], {}
    for cells in rows:
        row, col = [], 0

        def fill():
            nonlocal col
            while col in carry:
                rem, content = carry.pop(col)
                row.append(content)
                if rem > 1:
                    carry[col] = (rem - 1, content)
                col += 1

        for attrs, content in cells:
            fill()
            rs = re.search(r"rowspan=\"?(\d+)", attrs)
            cs = re.search(r"colspan=\"?(\d+)", attrs)
            for _ in range(int(cs.group(1)) if cs else 1):
                row.append(content)
                if rs and int(rs.group(1)) > 1:
                    carry[col] = (int(rs.group(1)) - 1, content)
                col += 1
        fill()
        grid.append(row)
    return grid

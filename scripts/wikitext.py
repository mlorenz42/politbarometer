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


def infobox(text: str, title: str) -> dict:
    m = re.search(r"\{\{Infobox Regierung[ \t]*\n(.*?)\n\}\}", text, re.S)
    if not m:
        raise Mismatch("%s: Infobox nicht gefunden" % title)
    box = {}
    for line in m.group(1).split("\n"):
        mm = re.match(r"\|[ \t]*([^=|]+?)[ \t]*=[ \t]*(.*)$", line)
        if mm:
            box[mm.group(1)] = mm.group(2).strip()
    return box


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

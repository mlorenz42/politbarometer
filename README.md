# Politbarometer seit 1998

Interaktive Grafiken zum Verlauf der Sonntagsfrage (ZDF-Politbarometer für den Bundestag, wahlrecht.de-Umfragen für die 16 Landtage), jeweils mit Regierung, Koalition und Sitzverteilung.

**Live:**
- https://mlorenz42.github.io/politbarometer/ – Bundestag
- https://mlorenz42.github.io/politbarometer/laender.html – Bundesländer
- https://mlorenz42.github.io/politbarometer/sitzverteilung.html – Sitzverteilung aller 17 Parlamente auf einen Blick

## Was die Seiten zeigen

- **Bundestag:** Umfrageverlauf seit 1998, Filter nach Zeitraum, Kabinett, Kanzlerschaft oder Bundestagswahl sowie „Nur Umfragen“/„Nur Wahlergebnisse“, dazu Bundesregierung und Sitzverteilung als Halbkreisdiagramm. Die Auswahl steht als Hash in der Adresse (`#wahl=2025`, `#kabinett=Scholz`, `#art=wahlergebnisse` …) und lässt sich teilen.
- **Bundesländer:** Land wählen, Umfragen mehrerer Institute mit gleitendem Trend, Landesregierung, Sitzverteilung, gleiche Filterlogik wie beim Bundestag plus Institutsfilter.
- **Sitzverteilung:** Bundestag groß oben, alle 16 Landtage klein im 4×4-Raster darunter – zum Vergleichen auf einen Blick statt einzeln durchzuklicken. Jede Kachel verlinkt zur vollen Länderansicht. Die großen Diagramme lassen sich per Knopf als PNG speichern.

## So funktioniert es

Fünf Skripte holen die Rohdaten, `build_site.py` baut daraus alle drei `docs/*.html`:

| Skript | Quelle | Ausgabe |
|---|---|---|
| `update_data.py` | wahlrecht.de, Politbarometer | `data/politbarometer.csv` |
| `update_regierungen.py` | Wikipedia (Kabinettsartikel + Liste der Bundesregierungen) | `data/regierungen.json` |
| `update_landtage.py` | wahlrecht.de, 16 Landesseiten | `data/landtage.csv`, `data/laender.json` |
| `update_landesregierungen.py` | Wikipedia (Liste der Ministerpräsidenten + Kabinettsartikel) | `data/landesregierungen.json` |
| `update_sitze.py` | Wikipedia (Bundestag + 16 Landtage) | `data/sitze.json` |

`update_sitze.py` gleicht dabei gegen die beiden Regierungsdateien ab und läuft deshalb nach ihnen. Jedes Skript prüft seine Daten gegen eine unabhängige zweite Quelle bzw. auf Plausibilität und bricht bei einem Widerspruch ab, statt die Datei zu überschreiben – die Seite bleibt dann beim letzten guten Stand, GitHub schickt eine Fehlermail.

Die GitHub Action [`update.yml`](.github/workflows/update.yml) läuft jeden Montag automatisch und lässt sich im Actions-Tab auch manuell starten. Ohne neue Daten entsteht kein Commit.

## Lokal ausprobieren

Braucht nur Python 3.9+, keine weiteren Pakete.

```sh
python3 scripts/update_data.py --full   # einmalig: alle Archivseiten 1998–2017 laden
python3 scripts/update_regierungen.py
python3 scripts/update_landtage.py      # 16 Seiten, dauert etwa eine halbe Minute
python3 scripts/update_landesregierungen.py
python3 scripts/update_sitze.py         # nach den beiden Regierungsskripten
python3 scripts/build_site.py
open docs/index.html
```

## Daten, Quellen, Lizenz

- Umfragen: [wahlrecht.de](https://www.wahlrecht.de/umfragen/) (ehrenamtlich betrieben, keine ausdrückliche Lizenz für die Daten – bitte Quelle nennen).
- Regierungen & Sitzverteilung: deutschsprachige Wikipedia ([CC BY-SA](https://creativecommons.org/licenses/by-sa/4.0/deed.de)).
- Der Code steht unter der [MIT-Lizenz](LICENSE); das gilt nicht für die Daten selbst.

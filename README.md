# Politbarometer seit 1998

Interaktive Grafik zum Verlauf der Sonntagsfrage im ZDF-Politbarometer (Forschungsgruppe Wahlen), ergänzt um die jeweilige Bundesregierung: Kabinett, Koalitionsparteien, Kanzler.

**Live:** https://mlorenz42.github.io/politbarometer/

Die Seite zeigt CDU/CSU, SPD, Grüne, FDP, Linke (früher PDS), AfD und BSW, dazu die Ergebnisse der Bundestagswahlen und die 5-%-Hürde. Zeiträume und Parteien lassen sich umschalten, alle Werte gibt es auch als Tabelle.

## So funktioniert es

```
wahlrecht.de ──► scripts/update_data.py ──► data/politbarometer.csv ─┐
                                                                     ├─► scripts/build_site.py ──► docs/index.html ──► GitHub Pages
data/regierungen.json (von Hand gepflegt) ───────────────────────────┘
```

Die GitHub Action [`update.yml`](.github/workflows/update.yml) läuft am 2. jedes Monats, ruft die aktuelle Politbarometer-Seite ab, führt neue Umfragen in die CSV ein, baut die Seite neu und veröffentlicht sie. Gibt es keine neuen Daten, entsteht kein Commit. Sie lässt sich auch manuell starten (Actions-Tab, „Run workflow“) und läuft bei Änderungen an Skripten, Template oder Regierungsdaten.

Bei unplausiblen Abrufergebnissen (leere Seite, umgebaute Tabelle, älteres Datum als bisher) bricht der Lauf ab, statt die Daten zu überschreiben. GitHub schickt dann eine Fehlermail.

## Regierungsdaten pflegen

Die Regierungen lassen sich nicht zuverlässig automatisch abrufen. Sie stehen in [`data/regierungen.json`](data/regierungen.json) und müssen bei einem Regierungswechsel von Hand angepasst werden:

1. Beim bisherigen Kabinett `to` und beim letzten `ph`-Abschnitt `to` auf das Enddatum setzen.
2. Ein neues Kabinett anfügen (`to: null` = im Amt) und den Block `aktuell` anpassen.
3. `stand` auf das heutige Datum setzen.

Nach dem Push baut die Action die Seite neu. `wp` und `co` verwenden die Kürzel `cdu`, `spd`, `gru`, `fdp`, `lin`, `afd`, `bsw`.

## Lokal ausprobieren

Benötigt wird nur Python 3.9 oder neuer, keine weiteren Pakete.

```sh
python3 scripts/update_data.py          # aktuelle Seite abrufen und in die CSV einarbeiten
python3 scripts/update_data.py --full   # zusätzlich alle Archivseiten 1998–2017 neu laden
python3 scripts/build_site.py           # docs/index.html neu erzeugen
open docs/index.html
```

## Daten und Quellen

- Umfragedaten: [wahlrecht.de](https://www.wahlrecht.de/umfragen/politbarometer.htm), Politbarometer der Forschungsgruppe Wahlen. Wahlrecht.de ist ein ehrenamtlich betriebener Informationsdienst und nennt keine ausdrückliche Lizenz für die Daten. Bitte die Quelle nennen und die Originalseiten verlinken. Das Skript ruft nur eine Seite pro Lauf ab.
- Regierungsdaten: Wikipedia und Amtszeiten der jeweiligen Kabinette.
- Angegeben ist jeweils das Veröffentlichungsdatum der Umfrage. Die CSV enthält auch FW, PIRATEN und Sonstige, die Grafik zeigt sie nicht. Fehlt ein Wert, wurde die Partei in dieser Umfrage nicht einzeln ausgewiesen.

Die Spalte `election` markiert Zeilen, die kein Umfragewert, sondern das Ergebnis einer Bundestagswahl sind.

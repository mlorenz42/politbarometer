# Politbarometer seit 1998

Interaktive Grafik zum Verlauf der Sonntagsfrage im ZDF-Politbarometer (Forschungsgruppe Wahlen), ergänzt um die jeweilige Bundesregierung: Kabinett, Koalitionsparteien, Kanzler.

**Live:** https://mlorenz42.github.io/politbarometer/

Die Seite zeigt CDU/CSU, SPD, Grüne, FDP, Linke (früher PDS), AfD und BSW, dazu die Ergebnisse der Bundestagswahlen und die 5-%-Hürde. Zeiträume und Parteien lassen sich umschalten, alle Werte gibt es auch als Tabelle. Zusätzlich lässt sich der Verlauf seit einer beliebigen Bundestagswahl anzeigen (Auswahlliste, etwa „Seit der Bundestagswahl 2025“) sowie auf ein einzelnes Kabinett (z. B. „Kabinett Scholz“) oder eine Kanzlerschaft über mehrere Kabinette (z. B. Angela Merkel) eingrenzen, entweder über die Auswahlliste oder per Klick auf das Regierungsband über dem Diagramm. Die Auswahl steht in der Adresse und lässt sich teilen, etwa `https://mlorenz42.github.io/politbarometer/#wahl=2025`, `#kabinett=Scholz` oder `#kanzlerschaft=Angela%20Merkel`.

## So funktioniert es

```
wahlrecht.de ──► scripts/update_data.py ──► data/politbarometer.csv ─┐
                                                                     ├─► scripts/build_site.py ──► docs/index.html ──► GitHub Pages
Wikipedia ──► scripts/update_regierungen.py ──► data/regierungen.json ┘
```

Die GitHub Action [`update.yml`](.github/workflows/update.yml) läuft am 2. jedes Monats, ruft die aktuelle Politbarometer-Seite ab, führt neue Umfragen in die CSV ein, baut die Seite neu und veröffentlicht sie. Gibt es keine neuen Daten, entsteht kein Commit. Sie lässt sich auch manuell starten (Actions-Tab, „Run workflow“) und läuft bei Änderungen an Skripten, Template oder Workflow.

Bei unplausiblen Abrufergebnissen (leere Seite, umgebaute Tabelle, älteres Datum als bisher) bricht der Lauf ab, statt die Daten zu überschreiben. GitHub schickt dann eine Fehlermail.

## Regierungsdaten

`data/regierungen.json` wird ebenfalls automatisch aus der deutschen Wikipedia erzeugt (`scripts/update_regierungen.py`). Das Skript nutzt zwei Seitentypen, die es gegeneinander prüft:

1. die Infobox jedes Kabinettsartikels („Kabinett Kohl V“ bis „Kabinett Merz“). Von Kohl V aus folgt es dem Feld „Nachfolger“, ein **neues Kabinett wird also von selbst erkannt**. Daraus stammen Kanzler, Amtszeit und Koalitionsparteien, auch Wechsel innerhalb einer Amtszeit (etwa der Ausstieg der FDP aus der Ampel).
2. die Tabelle in [Liste der deutschen Bundesregierungen](https://de.wikipedia.org/wiki/Liste_der_deutschen_Bundesregierungen). Daraus stammen die Partei des Kanzlers und der Vizekanzler, außerdem dient sie als Gegenprobe.

Widersprechen sich die Quellen, ist eine Partei unbekannt (die Grafik kennt CDU/CSU, SPD, Grüne, FDP, Linke, AfD, BSW) oder eine Seite umgebaut, schreibt das Skript nichts und der Schritt schlägt fehl. Die Umfragedaten werden dann trotzdem veröffentlicht, der Lauf wird aber als fehlgeschlagen markiert und GitHub schickt eine Fehlermail. Dann muss jemand nachsehen, zum Beispiel mit `python scripts/update_regierungen.py --dry-run`.

Das Feld „Zuletzt“ (Kabinettsumbildung) ist eine Best-Effort-Ableitung aus dem Abschnitt „Kabinettsumbildung …“ im Artikel des aktuellen Kabinetts und entfällt, wenn es keinen solchen Abschnitt gibt. Das Datum „Stand“ in der Fußzeile ist der Tag des letzten erfolgreichen Abgleichs.

## Lokal ausprobieren

Benötigt wird nur Python 3.9 oder neuer, keine weiteren Pakete.

```sh
python3 scripts/update_data.py          # aktuelle Seite abrufen und in die CSV einarbeiten
python3 scripts/update_data.py --full   # zusätzlich alle Archivseiten 1998–2017 neu laden
python3 scripts/update_regierungen.py   # Regierungsdaten aus Wikipedia (--dry-run zeigt nur die Änderungen)
python3 scripts/build_site.py           # docs/index.html neu erzeugen
open docs/index.html
```

## Daten und Quellen

- Umfragedaten: [wahlrecht.de](https://www.wahlrecht.de/umfragen/politbarometer.htm), Politbarometer der Forschungsgruppe Wahlen. Wahlrecht.de ist ein ehrenamtlich betriebener Informationsdienst und nennt keine ausdrückliche Lizenz für die Daten. Bitte die Quelle nennen und die Originalseiten verlinken. Das Skript ruft nur eine Seite pro Lauf ab.
- Regierungsdaten: deutschsprachige Wikipedia (Kabinettsartikel und Liste der deutschen Bundesregierungen, [CC BY-SA](https://creativecommons.org/licenses/by-sa/4.0/deed.de)).
- Angegeben ist jeweils das Veröffentlichungsdatum der Umfrage. Die CSV enthält auch FW, PIRATEN und Sonstige, die Grafik zeigt sie nicht. Fehlt ein Wert, wurde die Partei in dieser Umfrage nicht einzeln ausgewiesen.

Die Spalte `election` markiert Zeilen, die kein Umfragewert, sondern das Ergebnis einer Bundestagswahl sind.

## Lizenz

Der Code steht unter der [MIT-Lizenz](LICENSE). Sie gilt nicht für die Daten: Umfragewerte stammen von wahlrecht.de, Regierungsangaben aus der Wikipedia, siehe „Daten und Quellen“.

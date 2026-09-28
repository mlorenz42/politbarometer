# Politbarometer seit 1998

Interaktive Grafiken zum Verlauf der Sonntagsfrage: im ZDF-Politbarometer (Forschungsgruppe Wahlen) für den Bundestag und in den Umfragen zu den Landtagswahlen der 16 Länder, jeweils ergänzt um die Regierung: Kabinett, Koalitionsparteien, Regierungschef.

**Live:** https://mlorenz42.github.io/politbarometer/ (Bundestag) · https://mlorenz42.github.io/politbarometer/laender.html (Bundesländer) · https://mlorenz42.github.io/politbarometer/sitzverteilung.html (Sitzverteilung auf einen Blick)

**Bundestag:** CDU/CSU, SPD, Grüne, FDP, Linke (früher PDS), AfD und BSW im Politbarometer der Forschungsgruppe Wahlen seit 1998, dazu die Ergebnisse der Bundestagswahlen, die 5-%-Hürde, die jeweilige Bundesregierung und die aktuelle Sitzverteilung im Bundestag als Halbkreisdiagramm. Zeiträume und Parteien lassen sich umschalten, alle Werte gibt es auch als Tabelle. Der Verlauf lässt sich auf „Seit <Jahr>“ in 5-Jahres-Schritten (Schaltflächen für 2010 und 2020, alle Schritte in der Auswahlliste), seit einer beliebigen Bundestagswahl, auf ein einzelnes Kabinett (z. B. „Kabinett Scholz“) oder eine Kanzlerschaft über mehrere Kabinette (z. B. Angela Merkel) eingrenzen, entweder über die Auswahlliste oder per Klick auf das Regierungsband über dem Diagramm. Unter der Überschrift zeigen die Parteien-Schaltflächen für den gewählten Zeitraum den Stand der letzten Umfrage und die Veränderung seit der ersten Umfrage in Prozentpunkten (bei „Seit der Bundestagswahl …“ gegenüber dem Wahlergebnis). Ohne Vergleichswert steht „–“, etwa bei der AfD in einem Zeitraum, der vor ihrer Gründung beginnt. Zusätzlich lässt sich die Art der Daten auf „Nur Umfragen“ oder „Nur Wahlergebnisse“ eingrenzen; Letzteres verbindet nur die acht Bundestagswahl-Ergebnisse zu einer Linie über die ganze Zeitspanne. Die Auswahl steht in der Adresse und lässt sich teilen, etwa `https://mlorenz42.github.io/politbarometer/#wahl=2025`, `#kabinett=Scholz`, `#zeitraum=y2010`, `#kanzlerschaft=Angela%20Merkel` oder `#art=wahlergebnisse`.

**Bundesländer:** Sonntagsfrage zu den Landtagswahlen aller 16 Länder. Man wählt das Land (Standard ist das mit der jüngsten Umfrage), sieht die aktuelle Landesregierung samt Regierungschef, den nächsten Wahltermin, die aktuelle Sitzverteilung im Landtag (bzw. in der Bürgerschaft/im Abgeordnetenhaus) und den Verlauf. Weil hier viele Institute befragen, zeigt das Diagramm jede Umfrage als Punkt und darüber einen gewichteten gleitenden Mittelwert (± 45 Tage, getrennt je Wahlperiode, bei Lücken über 150 Tage unterbrochen). Filter: seit einer Wahl, Amtszeit eines Regierungschefs, einzelnes Kabinett, einzelnes Institut sowie „Nur Umfragen“ oder „Nur Wahlergebnisse“ (verbindet dann nur die Wahlergebnisse selbst, ohne Trend; der Institutsfilter ist in diesem Modus ausgegraut, weil Wahlergebnisse kein Institut haben). Die Schaltflächen der Parteien zeigen den Durchschnitt der jüngsten Umfragen und die Veränderung gegenüber dem Wahlergebnis bzw. den ersten Umfragen. Adressen wie `laender.html#land=bayern&wahl=2023&institut=INSA` oder `laender.html#land=bayern&art=wahlergebnisse`.

**Sitzverteilung:** dritte Seite mit dem Bundestag groß oben und darunter einem Raster aller 16 Landtage klein, jeweils Halbkreisdiagramm plus Kabinett und Koalitionsparteien in einer Zeile – um sie auf einen Blick zu vergleichen, statt einzeln durchzuklicken. Jede Länderkachel verlinkt auf die passende Ansicht der Länderseite.

## So funktioniert es

```
wahlrecht.de (Politbarometer) ─► scripts/update_data.py ─────────► data/politbarometer.csv ──┐
Wikipedia (Bundesregierung) ───► scripts/update_regierungen.py ──► data/regierungen.json ────┤
                                                                                              │
wahlrecht.de (Landtage) ───────► scripts/update_landtage.py ─────► data/landtage.csv ─────────┼─► scripts/build_site.py ─┬─► docs/index.html (Bundestag)
                                                                  data/laender.json ──────────┤                        ├─► docs/laender.html (Bundesländer)
Wikipedia (Ministerpräsidenten) ► scripts/update_landesregierungen.py ► data/landesregierungen.json ┤                  └─► docs/sitzverteilung.html (Sitzverteilung)
                                                                                              │
Wikipedia (Sitzverteilung, 17 Artikel) ► scripts/update_sitze.py ────► data/sitze.json ───────┘
    (gleicht dabei die beiden Regierungsdateien ab, läuft deshalb nach ihnen)
```

Die GitHub Action [`update.yml`](.github/workflows/update.yml) läuft jeden Montag, ruft die aktuelle Politbarometer-Seite, die 16 Länderseiten und die Wikipedia-Artikel ab, führt neue Umfragen in die CSV ein, baut die Seite neu und veröffentlicht sie. Gibt es keine neuen Daten, entsteht kein Commit. Sie lässt sich auch manuell starten (Actions-Tab, „Run workflow“) und läuft bei Änderungen an Skripten, Template oder Workflow.

Bei unplausiblen Abrufergebnissen (leere Seite, umgebaute Tabelle, älteres Datum als bisher) bricht der Lauf ab, statt die Daten zu überschreiben. GitHub schickt dann eine Fehlermail.

## Regierungsdaten

`data/regierungen.json` wird ebenfalls automatisch aus der deutschen Wikipedia erzeugt (`scripts/update_regierungen.py`). Das Skript nutzt zwei Seitentypen, die es gegeneinander prüft:

1. die Infobox jedes Kabinettsartikels („Kabinett Kohl V“ bis „Kabinett Merz“). Von Kohl V aus folgt es dem Feld „Nachfolger“, ein **neues Kabinett wird also von selbst erkannt**. Daraus stammen Kanzler, Amtszeit und Koalitionsparteien, auch Wechsel innerhalb einer Amtszeit (etwa der Ausstieg der FDP aus der Ampel).
2. die Tabelle in [Liste der deutschen Bundesregierungen](https://de.wikipedia.org/wiki/Liste_der_deutschen_Bundesregierungen). Daraus stammen die Partei des Kanzlers und der Vizekanzler, außerdem dient sie als Gegenprobe.

Widersprechen sich die Quellen, ist eine Partei unbekannt (die Grafik kennt CDU/CSU, SPD, Grüne, FDP, Linke, AfD, BSW) oder eine Seite umgebaut, schreibt das Skript nichts und der Schritt schlägt fehl. Die Umfragedaten werden dann trotzdem veröffentlicht, der Lauf wird aber als fehlgeschlagen markiert und GitHub schickt eine Fehlermail. Dann muss jemand nachsehen, zum Beispiel mit `python scripts/update_regierungen.py --dry-run`.

Das Feld „Zuletzt“ (Kabinettsumbildung) ist eine Best-Effort-Ableitung aus dem Abschnitt „Kabinettsumbildung …“ im Artikel des aktuellen Kabinetts und entfällt, wenn es keinen solchen Abschnitt gibt. Das Datum „Stand“ in der Fußzeile ist der Tag des letzten erfolgreichen Abgleichs.

## Landtagsumfragen und Landesregierungen

`scripts/update_landtage.py` liest die 16 Seiten `wahlrecht.de/umfragen/landtage/<land>.htm` (eine Anfrage alle 1,5 Sekunden) und führt neue Umfragen in `data/landtage.csv` ein. Jede Landesseite hat mehrere Tabellen (je Wahlperiode) mit unterschiedlichen Spalten, die Skript-Logik findet die Spalten deshalb über ihre Überschriften. Ein Wahlergebnis steht dort am Ende der einen und am Anfang der nächsten Tabelle, behalten wird die Zeile mit den meisten einzeln ausgewiesenen Parteien. Umfragen mit unvollständigem Datum (`??.12.1992`) werden übersprungen. Die Übersichtsseite liefert außerdem den nächsten Wahltermin je Land (`data/laender.json`).

`scripts/update_landesregierungen.py` baut `data/landesregierungen.json` aus dem Wikipedia-Artikel [Liste der Ministerpräsidenten der deutschen Länder](https://de.wikipedia.org/wiki/Liste_der_Ministerpr%C3%A4sidenten_der_deutschen_L%C3%A4nder) (Kabinettstitel, Partei des Regierungschefs) und den Infoboxen der einzelnen Kabinettsartikel (Regierungschef, Amtszeit, Koalition, auch Koalitionswechsel innerhalb einer Amtszeit). Neue Kabinette erscheinen mit der Liste von selbst. Geprüft wird auf lückenlose Amtszeiten ohne Überschneidung; kleine Auffälligkeiten (etwa ein Kabinett, das einen Tag vor dem Ende des vorigen beginnt) werden als Warnung ausgegeben, Tippfehler in Datumsfeldern der Wikipedia werden aus dem Beginn des Nachfolgers abgeleitet. Parteien, die die Grafik nicht kennt, erscheinen ohne eigene Farbe in Grau (z. B. „Statt“ in Hamburg).

Die Grafik zeigt je Land bis zu acht Parteien mit mindestens 3,5 % in fünf oder mehr Umfragen. Kleine Parteien wie SSW, NPD oder BIW stehen nur in der Tabelle unter „Sonstige“ bzw. in `data/landtage.csv` (Spalten `SSW`, `NPD`, `BIW`, `weitere`).

## Sitzverteilung

Bundestag und jeder Landtag haben einen dauerhaften Wikipedia-Artikel („Deutscher Bundestag“, „Bayerischer Landtag“ …), der nach jeder Wahl aktualisiert wird und in seiner Infobox zwei zusammenhängende Angaben trägt: die Sitze je Partei (Vorlage `{{Sitzverteilung|…}}`, inklusive der von den Wikipedia-Autoren gewählten Reihenfolge im politischen Spektrum) und einen Link auf das amtierende Kabinett als „Regierung (n Sitze)“. `scripts/update_sitze.py` liest alle 17 Artikel in einer einzigen Anfrage, prüft das verlinkte Kabinett gegen `data/regierungen.json` bzw. `data/landesregierungen.json` (die deshalb vor diesem Skript aktuell sein müssen) und die Sitze seiner Koalitionsparteien gegen die genannte Zahl, und schreibt `data/sitze.json` (inklusive der Koalitions-Parteikürzel je Kabinett, damit die Seiten nicht die deutlich größeren Regierungsdateien laden müssen). Scheitert das für den Bundestag oder eines der Länder, bricht der ganze Lauf ab und lässt die JSON unberührt – wie bei den anderen `update_*.py`-Skripten lieber gar nicht veröffentlichen als eine Datei mit teils veralteten Ständen.

Auf allen drei Seiten zeigt ein Halbkreisdiagramm die Sitze als einzelne Punkte, in Parteifarbe und von links nach rechts im politischen Spektrum angeordnet (Reihen und Sitze berühren sich, wie bei den bekannten Sitzverteilungsgrafiken). Über den beiden großen Diagrammen (Bundestag, gewähltes Land) steht dauerhaft Sitzzahl und Anteil an den Gesamtsitzen je Fraktion – nicht nur beim Hover. Die Beschriftung sitzt über dem jeweils höchsten eigenen Punkt (nicht der Winkelmitte, das würde bei einer sehr breiten Fraktion mitten in die eigenen Punkte geraten) und weicht bei eng benachbarten kleinen Fraktionen stufenweise nach oben aus, damit sie sich nicht überlappen. Regierungsparteien erscheinen in voller Farbe und mit der Markierung „Regierung“, Oppositionsparteien blasser. Parteien, die die Grafik nicht kennt (z. B. „Unabh.“ oder lokale Kleinparteien), erscheinen grau, mit ihrem echten Namen in der Liste bzw. der Kabinettszeile. Auf `sitzverteilung.html` sind die 16 Länderdiagramme verkleinert und ohne Detailliste, dafür mit einer knappen Kabinettszeile – zum Vergleichen auf einen Blick statt einzeln durchzuklicken; jede Kachel verlinkt auf die volle Ansicht in `laender.html`.

## Lokal ausprobieren

Benötigt wird nur Python 3.9 oder neuer, keine weiteren Pakete.

```sh
python3 scripts/update_data.py          # aktuelle Seite abrufen und in die CSV einarbeiten
python3 scripts/update_data.py --full   # zusätzlich alle Archivseiten 1998–2017 neu laden
python3 scripts/update_regierungen.py   # Regierungsdaten aus Wikipedia (--dry-run zeigt nur die Änderungen)
python3 scripts/update_landtage.py       # Landtagsumfragen (16 Seiten, dauert etwa eine halbe Minute)
python3 scripts/update_landesregierungen.py   # Landesregierungen aus Wikipedia
python3 scripts/update_sitze.py         # Sitzverteilung aus Wikipedia (läuft nach den beiden Regierungsdateien)
python3 scripts/build_site.py           # docs/index.html und docs/laender.html neu erzeugen
open docs/index.html
```

## Daten und Quellen

- Umfragedaten: [wahlrecht.de](https://www.wahlrecht.de/umfragen/politbarometer.htm), Politbarometer der Forschungsgruppe Wahlen, und [Umfragen zu Landtagswahlen](https://www.wahlrecht.de/umfragen/landtage/) (mehrere Institute, jeweils mit Auftraggeber und Feldzeit). Wahlrecht.de ist ein ehrenamtlich betriebener Informationsdienst und nennt keine ausdrückliche Lizenz für die Daten. Bitte die Quelle nennen und die Originalseiten verlinken. Das Skript ruft nur eine Seite pro Lauf ab.
- Regierungsdaten und Sitzverteilung: deutschsprachige Wikipedia (Kabinettsartikel, Liste der deutschen Bundesregierungen, Liste der Ministerpräsidenten der deutschen Länder sowie die Artikel zu Bundestag und den 16 Landtagen, [CC BY-SA](https://creativecommons.org/licenses/by-sa/4.0/deed.de)).
- Angegeben ist jeweils das Veröffentlichungsdatum der Umfrage. Die CSV enthält auch FW, PIRATEN und Sonstige, die Grafik zeigt sie nicht. Fehlt ein Wert, wurde die Partei in dieser Umfrage nicht einzeln ausgewiesen.

Die Spalte `election` markiert Zeilen, die kein Umfragewert, sondern das Ergebnis einer Bundestagswahl sind.

## Lizenz

Der Code steht unter der [MIT-Lizenz](LICENSE). Sie gilt nicht für die Daten: Umfragewerte stammen von wahlrecht.de, Regierungsangaben aus der Wikipedia, siehe „Daten und Quellen“.

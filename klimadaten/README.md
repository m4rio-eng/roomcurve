# Klimadaten – Testreferenzjahre (TRY)

## Quelle und Rechte

Die in diesem Ordner enthaltenen Testreferenzjahre (TRY) wurden **vom Deutschen Wetterdienst (DWD) für das Bundesinstitut für Bau-, Stadt- und Raumforschung (BBSR) entwickelt**.

Die Datensätze sind kostenfrei über das TRY-Portal des BBSR beziehbar: https://www.bbsr-geg.bund.de/GEGPortal/DE/Praxishilfen/Testreferenzjahre/TRY_node.html

Dort finden sich beide Ausgaben: die TRY-Ausgabe 2011 (direkter Download) und die ortsgenaue TRY-Ausgabe 2017 (Bezug über das Klimaberatungsmodul des DWD; einmalige, kostenfreie Registrierung erforderlich).

Die Bereitstellung der Datensätze in diesem Repository erfolgt mit Zustimmung des BBSR. Die TRY-Daten sind **nicht** Bestandteil der AGPL-Lizenz dieses Projekts; für sie gelten die Bedingungen des BBSR/DWD.

## Enthaltene Datensätze

Drei Repräsentanzstandorte der Sommerklimaregionen nach DIN 4108-2 (A = Rostock / TRY-Zone 02, B = Potsdam / TRY-Zone 04, C = Mannheim / TRY-Zone 12), jeweils aus zwei TRY-Veröffentlichungen:

| Datei-Präfix | Veröffentlichung | Zeitraum-Basis | Charakter |
|---|---|---|---|
| TRY2010 | TRY-Ausgabe 2011 | 1988–2007 (gemessen) | mittleres Vergangenheitsjahr (teilweise auch als „Gegenwartsjahr“ bezeichnet) |
| TRY2035 | TRY-Ausgabe 2011 | 2021–2050 (projiziert) | mittleres Zukunftsjahr |
| TRY2015 | ortsgenaue TRY-Ausgabe 2017 | 1995–2012 (gemessen) | mittleres Vergangenheitsjahr (teilweise auch als „Gegenwartsjahr“ bezeichnet) |
| TRY2045 | ortsgenaue TRY-Ausgabe 2017 | 2031–2060 (projiziert) | mittleres Zukunftsjahr |

Dateinamensschema: `TRY<Jahr>-<Zone>-Jahr.txt` (z. B. `TRY2010-04-Jahr.txt` = Gegenwarts-TRY, Zone 04 Potsdam).

## Dateiformat

Stündliche Jahresdatensätze (8 760 Zeilen) im TRY-Textformat des DWD (Festbreiten-Spalten, Latin-1-kodiert) mit u. a. Lufttemperatur, Direkt-/Diffusstrahlung, Windgeschwindigkeit, Bedeckungsgrad und relativer Feuchte. Das Einlesen übernimmt `iso52016/climate.py`; eigene TRY-Dateien gleichen Formats können in der App hochgeladen werden.

## Normativer Kontext

Für den Nachweis des sommerlichen Wärmeschutzes nach DIN 4108-2:2026-05, Abschnitt 8.5, sind die Gegenwarts-TRY (Ausgabe 2011, Zonen 02/04/12) heranzuziehen. Rechnungen mit Zukunfts-TRY entsprechen einer Bewertung mit individuellen Randbedingungen nach Anhang B (informativ) und ersetzen den Nachweis nicht.

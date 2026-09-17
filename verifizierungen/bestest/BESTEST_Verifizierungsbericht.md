# BESTEST-Verifizierungsbericht — RoomCurve 0.1.0

**Stand:** 2026-08-19 · **Suite:** ISO 52016-1:2018-04 Kap. 7.2 (14 Fälle) · **Byte-Baseline dieses Stands:** `ergebnisse_alle.json` (Wiederholungslauf byte-stabil) · generiert von `bestest_bericht.py`

**Ergebnis:** 10/14 Fälle nach der eigenen Bandregel bestanden (Maßstab und Quellenlage Abschn. 2; alle Heizwerte im Band, Abweichungen kühlseitig, Einordnung Abschn. 6). **Reproduktion:** `python run_bestest.py` (Lauf + Byte-Baseline-Abgleich), anschließend `python bestest_bericht.py` (dieser Bericht).

Terminologie nach Projektregel: ISO-Vergleich = **Verifizierung** (VDI-Vergleich = Validierung, eigener Bericht unter `verifizierungen/vdi6020/`). Offene Punkte: siehe Abschn. 7.

## 1 Prüfaufbau

- **Klima:** DRYCOLD (Denver-Stapleton; φ 39,76 / λ −104,86 / TZ −7 / 1609 m), Fassadenwerte nach ISO 52010-1, Quelle EPB-Center-Begleitdatei 2019-11-19. Datei `klimadaten/DRYCOLD_52016_verifizierung.csv` (Direkt-/Diffus getrennt je Ebene). Verifiziert: Monats-/Jahreswerte gegen Tabelle 26; Sub-Stunden-Konvention rechnerisch bestätigt (Sonnenstand zur Stundenmitte nach 52010-1 Gl. 9/10; DNI-Konsistenztest zweier Ebenen identisch).
- **Prüfskript:** `run_bestest.py` generiert die Configs bei jedem Lauf neu (Warndatei im configs-Ordner beachten). Der Klimapfad nutzt die Direktspalten der CSV; die interne 52010-1-Konvertierung wird hier nicht durchlaufen. Die Configs setzen die konventionellen Übergangskoeffizienten der Tabelle 25 sowie die Lüftungs- und Höhenkonvention nach 7.2.2.14 (0,411 = 0,5 × 0,822) EXPLIZIT je Bauteil bzw. Profil.
- **Norm-Referenzwerte (ISO 52016-1, 7.2.4):** Tabellen 28/29 (Jahres-/Monatswerte), Tabelle 30/32/34 (operative Temperaturen, Freilauf), Tabelle 31 (Spitzenlasten), Tabelle 33 (Stundenlasten
  4. Januar); FF-Berichtsgrößen siehe `berichtsgroessen_7_2_4.md`. Fall 900: Tab. 28/29 sind laut EPB Center Comment Sheet EN ISO 52016-1:2017 (2022-08-15), Kommentar 28, spaltenvertauscht gedruckt — korrekt Heizen 1827 / Kühlen 3360 kWh (Anmerkung M3 im Normtext-Register `../normtext_anmerkungen_52016_1.md`). Kommentar 31: Leichtbau-Referenzen (600/640/600FF) selbst fehlerbehaftet; belastbare Anker: 900/940.

## 2 Maßstab und Quellenlage der Bandbreiten

**Deklaration:** ASHRAE 140 ist ein „method of test" OHNE Pass/Fail-Kriterien; die Annex-B8-Bänder sind INFORMATIV (Beispielergebnisse der Referenzprogramme). „Im Band" ist eine EIGENE, strengere Bewertungsregel von RoomCurve, kein Normkriterium. Gleiches gilt für das dokumentierte FF-Kriterium (|Δ Monatsmittel| ≤ 1,0 K für alle 12 Monate und |Δ max|/|Δ min| ≤ 2,0 K gegen Tab. 30/32). Die Peak-, Monats-, Stunden- und Freilauf-Referenzen stammen aus ISO 52016-1 Tab. 28–34 und sind von der ASHRAE-Ausgabenfrage unberührt.

**Quellenlage der Bandbreiten:** Bänder nach ASHRAE 140, Informativer Annex B8, Abschnitt B8.1 (Beispielergebnisse der Referenzprogramme); die von ISO 52016-1 referenzierte Originalausgabe 140-2014 wurde nicht eingesehen, die Werte sind gegen zwei voneinander unabhängige, frei zugängliche Quellen abgeglichen — Einzelheiten (Quellen-URLs, Ausgabenlage, Kreuzabgleich, Prüfdatum) im Meta-Block der Datendatei `referenz_ashrae140.json` — aus dieser Datei bezieht das Prüfskript die Bänder ausschließlich.

## 3 Ergebnisse (Jahreswerte)

Gegen die Annex-B8-Bandbreiten [kWh] nach der eigenen Bandregel (Abschn. 2):

| Fall | Q_H [kWh] | Q_C [kWh] | Q_H,Band [kWh] (Annex B8) | Q_C,Band [kWh] (Annex B8) | Status |
|------|-----|-----|----------|----------|--------|
| 600   | 5486 | 7982 | 4296–5709 | 6137–7964 | Q_C +0,2 % über Bandkante |
| 600FF | 0 | 0 | — | — | bestanden (Tab.30 max Δθ=0.6K, Tab.32 dmax=0.6/dmin=1.8K; eigenes Kriterium, s. Maßstab) |
| 610   | 5540 | 5316 | 4355–5786 | 3915–5778 | bestanden |
| 620   | 5710 | 4874 | 4613–5944 | 3417–5004 | bestanden |
| 630   | 6079 | 3417 | 5050–6469 | 2129–3701 | bestanden |
| 640   | 3523 | 7662 | 2751–3803 | 5952–7811 | bestanden |
| 650   | 0 | 6276 | 0–0 | 4816–6545 | bestanden |
| 900   | 1906 | 3556 | 1170–2041 | 2132–3415 | Q_C +4,1 % über Bandkante |
| 900FF | 0 | 0 | — | — | bestanden (Tab.30 max Δθ=0.5K, Tab.32 dmax=0.7/dmin=1.4K; eigenes Kriterium, s. Maßstab) |
| 910   | 2241 | 1590 | 1575–2282 | 821–1872 | bestanden |
| 920   | 4114 | 3084 | 3313–4300 | 1840–3092 | bestanden |
| 930   | 4926 | 2118 | 4143–5335 | 1039–2238 | bestanden |
| 940   | 1319 | 3433 | 793–1411 | 2079–3241 | Q_C +5,9 % über Bandkante |
| 950   | 0 | 1090 | 0–0 | 387–921 | Q_C +18 % (absolut +169 kWh) |

**Bilanz: 10/14 bestanden; ALLE Heizwerte im Band; alle Abweichungen kühlseitig.** Gegen die korrigierten Norm-Anker (Case 900: Q_H 1827 / Q_C 3360 kWh): Q_H +3,8 %, Q_C +6,0 %.

## 4 Fall-zu-Fall-Deltas (16 Paare)

| Vergleich | Effekt | ΔQ_H [kWh] | ΔQ_C [kWh] | erwartete Richtung |
|-----------|--------|------|------|-----------|
| 600→610 | Süd-Verschattung | +54 | -2,666 | Q_H↑, Q_C↓ |
| 600→620 | Fenster S→O/W | +224 | -3,108 | Q_H↑, Q_C↓ |
| 620→630 | O/W-Verschattung | +369 | -1,457 | Q_H↑, Q_C↓ |
| 600→640 | Nachtabsenkung | -1,964 | -320 | Q_H↓, Q_C~ |
| 600→650 | Nachtlüftung | -5,486 | -1,706 | Q_H~, Q_C↓ |
| 900→910 | Süd-Verschattung | +335 | -1,966 | Q_H↑, Q_C↓ |
| 900→920 | Fenster S→O/W | +2,207 | -472 | Q_H↑, Q_C~ |
| 920→930 | O/W-Verschattung | +812 | -966 | Q_H↑, Q_C↓ |
| 900→940 | Nachtabsenkung | -587 | -123 | Q_H↓, Q_C~ |
| 900→950 | Nachtlüftung | -1,906 | -2,466 | Q_H~, Q_C↓ |
| 600→900 | Therm. Masse | -3,580 | -4,426 | Q_H↓, Q_C↓ |
| 610→910 | Masse+Verschatt. | -3,299 | -3,725 | Q_H↓, Q_C↓ |
| 620→920 | Masse+O/W-Fenst. | -1,596 | -1,791 | Q_H↓, Q_C↓ |
| 630→930 | Masse+O/W-Versch. | -1,154 | -1,300 | Q_H↓, Q_C↓ |
| 640→940 | Masse+Nachtabs. | -2,204 | -4,229 | Q_H↓, Q_C↓ |
| 650→950 | Masse+Nachtlüft. | +0 | -5,186 | Q_H~, Q_C↓ |

**Alle 16 Deltas in korrekter Richtung** (Richtungsbewertung in der Terminalausgabe von `run_bestest.py`; Definitionen: `DELTA_PAARE`).

## 5 Stundenprofil 4. Januar, Fall 900 (Tabelle 33)

Eingeschwungener Lauf (Vorlaufjahr), f_H;c = 1,00:

- Nachtstunden 1–8: Tool −0,8 bis −2,0 % gegenüber Tabelle 33.
- Mittags-Totband (Heizung = 0): Std. 12–17 wie Referenz; Randstunden 11/18 um jeweils eine Stunde versetzt (Einzelstunden-Effekt im Promillebereich der Tagessumme).
- Tagessumme: 50 494 Wh gegen 50 862 Wh Referenz = −0,7 %.

Damit ist der Winter-Heizpfad des Schwerbaus stundenaufgelöst normnah.

## 6 Einordnung der kühlseitigen Überschreitungen

Alle vier Überschreitungen (600/900/940 knapp, 950 deutlich) liegen auf der Kühlseite bei vollständig bandkonformer Heizseite und vollständig richtungskorrekten Deltas. Die 900er-Reihe gegen die korrigierten Norm-Anker (Case 900: 1827/3360) liegt bei +3,8/+6,0 % — die Suite ist damit als Ganzes konsistent kühlseitig leicht heiß, was mit dem informativen Charakter der B8-Bänder (Beispielergebnis-Streuung der Referenzprogramme, keine Akzeptanzgrenzen) und den bekannten Unsicherheiten der Leichtbau-Referenzen (EPB-Kommentar 31) zu lesen ist. Kein Fall wird als „bestanden" ausgewiesen, der es nach der eigenen Bandregel nicht ist; die Byte-Baseline friert den exakten Zahlenstand ein.

## 7 Offene Punkte

Nicht von dieser Suite abgedeckt (Einzelheiten in den offenen Punkten im Wurzelverzeichnis): das Erdreichmodell und Mehrzonenmodelle — alle 14 Prüffälle sind einzonig und ohne Erdreich-Bauteil. Die Orientierungs-Rasterung von Klimadateien ohne Direkt-/Diffus-Rohdaten ist im BESTEST-Setup exakt wirkungslos (der einzige Nicht-Raster-Kandidat, der Boden, hat α_sol = 0). Eine optionale Nachschärfung der Klimaverifizierung mit den originalen DRYCOLD-Rohdaten ist in `../tab26_verifizierung.md` beschrieben.

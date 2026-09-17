# RoomCurve 0.1.0

Stündliches Heiz-/Kühllastverfahren für Räume nach **DIN EN ISO 52016-1:2018-04** (5-Knoten-Verfahren) mit Solarkette nach **DIN EN ISO 52010-1:2018-03** und Erdreichparametern nach **DIN EN ISO 13370:2018-03**. Python-Kern mit JSON-Eingaben, optionale Streamlit-GUI.

## Anwendungsbereich und Grenzen

**Verifiziert** (BESTEST nach ISO 52016-1 Kap. 7.2, 14 Fälle gegen die informativen Referenzbänder nach ANSI/ASHRAE 140, Annex B8; Herleitung im Bericht): einzonige Modelle mit Außenluft-Hüllflächen, Fenstern, Verschattung (Überhang/Fin/Horizont), Infiltration/Lüftung, Nachtabsenkung/-lüftung, leichter und schwerer Bauart. Stand: **10/14 Fälle im Band, alle Heizwerte im Band, alle 16 Fall-Deltas in korrekter Richtung**; Abweichungen ausschließlich kühlseitig und im Bericht charakterisiert (`verifizierungen/bestest/`).

**Implementiert, aber UNVERIFIZIERT** (kein Referenzfall in der Suite — Nutzung auf eigenes Risiko; Einzelheiten in den offenen Punkten):

- Erdreich (Bodenplatte auf Erdreich, Gl.-48-Knotenmodell mit ISO-13370-Ableitung). Keller, aufgeständerte Platten und Randdämmung sind NICHT implementiert.
- Mehrzonenmodelle: nachbarzone-Elemente werden normkonform als interne Trennwand behandelt (Gl. 42, adiabate Mittelebene) — es gibt KEINE thermische Kopplung zwischen Zonen (die simultane Kopplung nach Anhang D ist nicht implementiert; die Nachbarzonentemperatur geht nicht in die Rechnung ein).

**Nicht implementiert:** Feuchtebilanz (optionales Normkapitel 6.5.14) — RoomCurve rechnet sensible Heiz-/Kühllasten und ist für Anwendungen mit Entfeuchtungsanforderung ungeeignet. Was RoomCurve darüber hinaus nicht kann oder was ungeprüft ist, ist in den offenen Punkten dokumentiert (Datei im Wurzelverzeichnis).

**Validierung VDI 6020** (nicht Zielgröße): 0/7 Testbeispiele nach Maßstab Typ a, Ursachen vollständig charakterisiert (`verifizierungen/vdi6020/`, Validierungsbericht mit Laufdatum).

## Stand 0.1.0

Kern: stündliches 5-Knoten-Verfahren nach DIN EN ISO 52016-1:2018-04 (Gl. 39–53, 63–70) mit Solarkette nach DIN EN ISO 52010-1:2018-03 (Perez) und Erdreichparametern nach DIN EN ISO 13370:2018-03; konventionelle Übergangskoeffizienten nach Tabelle 25 (explizite Werte haben Vorrang vor der h_ci-Automatik), ρ_a·c_a nach Tabelle 20 mit Opt-in-Höhenkorrektur, Rahmenanteil-Default 0,25 (Tab. B.21). Auslegungsentscheidungen am Normtext sind in `verifizierungen/normtext_anmerkungen_*.md` offengelegt. Die Prüfskripte erzwingen den Repo-Kern (sys.path-Vorrang plus Herkunfts-Prüfung) und brechen laut ab, statt still mit einer anderweitig installierten iso52016-Version zu rechnen. Testsuite: Handrechnungs-Pins, Parameter-Durchreichung, Fangfälle, Regression.

## Installation

```bash
cd roomcurve
pip install -e .
```

## Schnellstart

```python
from iso52016 import lade_klimadaten, lade_gebaeude, simuliere, SimulationsOptionen

klima = lade_klimadaten('klimadaten/TRY2015-04-Jahr.txt', fmt='try_2015')
gebaeude = lade_gebaeude('gebaeude.json', 'nutzung.json')
ergebnis = simuliere(gebaeude, klima, SimulationsOptionen(klimadatei='try'))
print(f"Heizwärmebedarf: {ergebnis['gesamt']['Q_H_kWh']:.0f} kWh/a")
```

Beispiele: `examples/`. GUI: `pip install -e ".[gui]"`, dann `streamlit run gui/app.py`.

## Verifizierung / Validierung reproduzieren

```bash
# BESTEST (erzeugt Configs neu, vergleicht gegen ASHRAE-140-Bänder)
cd verifizierungen/bestest && python run_bestest.py

# VDI 6020 (Hauptlauf κ_voll; Sensitivität: --kappa iso13786;
# Diagramme benötigen matplotlib: pip install -e ".[verifizierung]")
cd verifizierungen/vdi6020
python vdi6020_lauf.py
python vdi6020_vergleich.py   # findet Hauptlauf + Sensitivität selbst
```

Die Datei `verifizierungen/bestest/ergebnisse_alle.json` ist die Byte-Baseline dieses Stands (Wiederholungsläufe müssen byte-identisch sein).

## Projektstruktur

```
roomcurve/
├── iso52016/                # Kern (simulation, climate, solar,
│                            #  erdreich, thermal_mass, analysis)
├── examples/
├── gui/                     # Streamlit-GUI
├── tests/                   # pytest-Suite
├── verifizierungen/
│   ├── bestest/             # ISO-Verifizierung + Bericht + Baseline
│   ├── vdi6020/             # VDI-Validierung (Ableitung, Läufe, Bericht)
│   ├── normtext_anmerkungen_52016_1.md
│   └── normtext_anmerkungen_52010_1.md
└── (Wurzel: README, offene Punkte, Projektkonfiguration)
```

## Terminologie

ISO-Vergleich = **Verifizierung**; VDI-Vergleich = **Validierung**. Norm-PDFs sind NICHT Teil des Repositories.

## Danksagung

Mit freundlicher Unterstützung und Beratung durch Prof. Dr.-Ing. Anton Maas.

## Lizenz

Copyright (c) 2026 Mario Vukadinovic. Dieses Programm ist freie Software: Sie können es unter den Bedingungen der GNU Affero General Public License, Version 3 (AGPL-3.0-only), weitergeben und/oder verändern. Es wird in der Hoffnung bereitgestellt, dass es nützlich ist, aber OHNE JEDE GEWÄHR, auch ohne die implizite Gewähr der MARKTGÄNGIGKEIT oder EIGNUNG FÜR EINEN BESTIMMTEN ZWECK. Der vollständige Lizenztext liegt in der Datei `LICENSE` bei. Quellcode-Repository: <https://github.com/m4rio-eng/roomcurve>. Wer die Software als Netzdienst betreibt (z. B. gehostete GUI), muss den Nutzern des Dienstes den Quellcode anbieten (AGPL §13).

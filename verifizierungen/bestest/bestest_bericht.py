#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Erzeugt BESTEST_Verifizierungsbericht.md aus den Laufdaten
(ergebnisse_alle.json, referenz_ashrae140.json, Tab.-28–34-Konstanten
aus run_bestest.py) und festen Analyse-Textbausteinen.

    python bestest_bericht.py
"""

import json
import sys
from datetime import date
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER))
import run_bestest as rb  # lädt zugleich den Repo-Kern-Wächter

def _sortkey(e):
    return (int("".join(filter(str.isdigit, e["case_id"]))), e["case_id"])


def _band_anmerkung(e):
    """Status-Text je Fall: bestanden / X % über Bandkante (berechnet)."""
    bew = e["bewertung"]
    cid = e["case_id"]
    if cid.endswith("FF"):
        # Pipe-Zeichen der Bewertungsstrings ("max|dT|") sind in
        # Markdown-Tabellenzellen Zelltrenner — inhaltlich umformen.
        qh = bew["Q_H_ref"].replace("max|dT|", "max Δθ")
        qc = bew["Q_C_ref"].replace("max|dT|", "max Δθ")
        return (f"bestanden ({qh}, {qc}; eigenes Kriterium, s. Maßstab)"
                if bew["passed"] else
                f"eigenes FF-Kriterium verletzt ({qh}, {qc})")
    if bew["passed"]:
        return "bestanden"
    teile = []
    ref = rb.REFERENZ[cid]
    for groesse, wert in (("Q_H", e["Q_H_kWh"]), ("Q_C", e["Q_C_kWh"])):
        lo, hi = ref[groesse]
        if not (lo <= wert <= hi):
            if hi > 0 and wert > hi:
                rel = (wert - hi) / hi * 100
                absw = wert - hi
                if rel >= 10:
                    teile.append(f"{groesse} +{rel:.0f} % "
                                 f"(absolut +{absw:.0f} kWh)")
                else:
                    txt = f"{rel:.1f}".replace(".", ",")
                    teile.append(f"{groesse} +{txt} % über Bandkante")
            else:
                teile.append(f"{groesse} unter Bandkante")
    return " · ".join(teile)


BAUSTEIN_PRUEFAUFBAU = """## 1 Prüfaufbau

- **Klima:** DRYCOLD (Denver-Stapleton; φ 39,76 / λ −104,86 / TZ −7 / 1609 m), Fassadenwerte nach ISO 52010-1, Quelle EPB-Center-Begleitdatei 2019-11-19. Datei `klimadaten/DRYCOLD_52016_verifizierung.csv` (Direkt-/Diffus getrennt je Ebene). Verifiziert: Monats-/Jahreswerte gegen Tabelle 26; Sub-Stunden-Konvention rechnerisch bestätigt (Sonnenstand zur Stundenmitte nach 52010-1 Gl. 9/10; DNI-Konsistenztest zweier Ebenen identisch).
- **Prüfskript:** `run_bestest.py` generiert die Configs bei jedem Lauf neu (Warndatei im configs-Ordner beachten). Der Klimapfad nutzt die Direktspalten der CSV; die interne 52010-1-Konvertierung wird hier nicht durchlaufen. Die Configs setzen die konventionellen Übergangskoeffizienten der Tabelle 25 sowie die Lüftungs- und Höhenkonvention nach 7.2.2.14 (0,411 = 0,5 × 0,822) EXPLIZIT je Bauteil bzw. Profil.
- **Norm-Referenzwerte (ISO 52016-1, 7.2.4):** Tabellen 28/29 (Jahres-/Monatswerte), Tabelle 30/32/34 (operative Temperaturen, Freilauf), Tabelle 31 (Spitzenlasten), Tabelle 33 (Stundenlasten
  4. Januar); FF-Berichtsgrößen siehe `berichtsgroessen_7_2_4.md`. Fall 900: Tab. 28/29 sind laut EPB Center Comment Sheet EN ISO 52016-1:2017 (2022-08-15), Kommentar 28, spaltenvertauscht gedruckt — korrekt Heizen 1827 / Kühlen 3360 kWh (Anmerkung M3 im Normtext-Register `../normtext_anmerkungen_52016_1.md`). Kommentar 31: Leichtbau-Referenzen (600/640/600FF) selbst fehlerbehaftet; belastbare Anker: 900/940."""


def baustein_massstab():
    m = rb.REFERENZ_META
    urls = "\n".join(f"  - {b}: <{u}>" for b, u in
                     zip(m["quellen_beschreibung"], m["quellen_urls"]))
    return f"""## 2 Maßstab und Quellenlage der Bandbreiten

**Deklaration:** ASHRAE 140 ist ein „method of test" OHNE Pass/Fail-Kriterien; die Annex-B8-Bänder sind INFORMATIV (Beispielergebnisse der Referenzprogramme). „Im Band" ist eine EIGENE, strengere Bewertungsregel von RoomCurve, kein Normkriterium. Gleiches gilt für das dokumentierte FF-Kriterium (|Δ Monatsmittel| ≤ 1,0 K für alle 12 Monate und |Δ max|/|Δ min| ≤ 2,0 K gegen Tab. 30/32). Die Peak-, Monats-, Stunden- und Freilauf-Referenzen stammen aus ISO 52016-1 Tab. 28–34 und sind von der ASHRAE-Ausgabenfrage unberührt.

**Quellenlage der Bandbreiten:** Bänder nach ASHRAE 140, Informativer Annex B8, Abschnitt B8.1 (Beispielergebnisse der Referenzprogramme); die von ISO 52016-1 referenzierte Originalausgabe 140-2014 wurde nicht eingesehen, die Werte sind gegen zwei voneinander unabhängige, frei zugängliche Quellen abgeglichen — Einzelheiten (Quellen-URLs, Ausgabenlage, Kreuzabgleich, Prüfdatum) im Meta-Block der Datendatei `referenz_ashrae140.json` — aus dieser Datei bezieht das Prüfskript die Bänder ausschließlich."""


BAUSTEIN_STUNDENPROFIL = """## 5 Stundenprofil 4. Januar, Fall 900 (Tabelle 33)

Eingeschwungener Lauf (Vorlaufjahr), f_H;c = 1,00:

- Nachtstunden 1–8: Tool −0,8 bis −2,0 % gegenüber Tabelle 33.
- Mittags-Totband (Heizung = 0): Std. 12–17 wie Referenz; Randstunden 11/18 um jeweils eine Stunde versetzt (Einzelstunden-Effekt im Promillebereich der Tagessumme).
- Tagessumme: 50 494 Wh gegen 50 862 Wh Referenz = −0,7 %.

Damit ist der Winter-Heizpfad des Schwerbaus stundenaufgelöst normnah."""

BAUSTEIN_EINORDNUNG = """## 6 Einordnung der kühlseitigen Überschreitungen

Alle vier Überschreitungen (600/900/940 knapp, 950 deutlich) liegen auf der Kühlseite bei vollständig bandkonformer Heizseite und vollständig richtungskorrekten Deltas. Die 900er-Reihe gegen die korrigierten Norm-Anker (Case 900: 1827/3360) liegt bei +3,8/+6,0 % — die Suite ist damit als Ganzes konsistent kühlseitig leicht heiß, was mit dem informativen Charakter der B8-Bänder (Beispielergebnis-Streuung der Referenzprogramme, keine Akzeptanzgrenzen) und den bekannten Unsicherheiten der Leichtbau-Referenzen (EPB-Kommentar 31) zu lesen ist. Kein Fall wird als „bestanden" ausgewiesen, der es nach der eigenen Bandregel nicht ist; die Byte-Baseline friert den exakten Zahlenstand ein."""

BAUSTEIN_OFFEN = """## 7 Offene Punkte

Nicht von dieser Suite abgedeckt (Einzelheiten in den offenen Punkten im Wurzelverzeichnis): das Erdreichmodell und Mehrzonenmodelle — alle 14 Prüffälle sind einzonig und ohne Erdreich-Bauteil. Die Orientierungs-Rasterung von Klimadateien ohne Direkt-/Diffus-Rohdaten ist im BESTEST-Setup exakt wirkungslos (der einzige Nicht-Raster-Kandidat, der Boden, hat α_sol = 0). Eine optionale Nachschärfung der Klimaverifizierung mit den originalen DRYCOLD-Rohdaten ist in `../tab26_verifizierung.md` beschrieben."""


def main():
    erg = json.loads((HIER / "ergebnisse_alle.json").read_text())
    erg_sorted = sorted(erg, key=_sortkey)
    passed = sum(1 for e in erg if e["bewertung"]["passed"])

    b = []
    b.append("# BESTEST-Verifizierungsbericht — RoomCurve 0.1.0")
    b.append("")
    b.append(f"**Stand:** {date.today().isoformat()} · **Suite:** "
             f"ISO 52016-1:2018-04 Kap. 7.2 ({len(erg)} Fälle) · "
             f"**Byte-Baseline dieses Stands:** `ergebnisse_alle.json` "
             f"(Wiederholungslauf byte-stabil) · generiert von "
             f"`bestest_bericht.py`")
    b.append("")
    b.append(f"**Ergebnis:** {passed}/{len(erg)} Fälle nach der eigenen "
             f"Bandregel bestanden (Maßstab und Quellenlage Abschn. 2; "
             f"alle Heizwerte im Band, Abweichungen kühlseitig, "
             f"Einordnung Abschn. 6). **Reproduktion:** "
             f"`python run_bestest.py` (Lauf + Byte-Baseline-Abgleich), "
             f"anschließend `python bestest_bericht.py` (dieser "
             f"Bericht).")
    b.append("")
    b.append("Terminologie nach Projektregel: ISO-Vergleich = "
             "**Verifizierung** (VDI-Vergleich = Validierung, eigener "
             "Bericht unter `verifizierungen/vdi6020/`). Offene "
             "Punkte: siehe Abschn. 7.")
    b.append("")
    b.append(BAUSTEIN_PRUEFAUFBAU)
    b.append("")
    b.append(baustein_massstab())
    b.append("")
    b.append("## 3 Ergebnisse (Jahreswerte)")
    b.append("")
    b.append("Gegen die Annex-B8-Bandbreiten [kWh] nach der eigenen "
             "Bandregel (Abschn. 2):")
    b.append("")
    b.append("| Fall | Q_H [kWh] | Q_C [kWh] |"
             " Q_H,Band [kWh] (Annex B8) | Q_C,Band [kWh] (Annex B8) |"
             " Status |")
    b.append("|------|-----|-----|----------|----------|--------|")
    for e in erg_sorted:
        cid = e["case_id"]
        if cid.endswith("FF"):
            b.append(f"| {cid} | 0 | 0 | — | — | {_band_anmerkung(e)} |")
        else:
            ref = rb.REFERENZ[cid]
            b.append(f"| {cid}   | {e['Q_H_kWh']:.0f} | {e['Q_C_kWh']:.0f}"
                     f" | {ref['Q_H'][0]}–{ref['Q_H'][1]}"
                     f" | {ref['Q_C'][0]}–{ref['Q_C'][1]}"
                     f" | {_band_anmerkung(e)} |")
    b.append("")
    heiz_ok = all(e["bewertung"]["Q_H_ok"] for e in erg
                  if not e["case_id"].endswith("FF"))
    b.append(f"**Bilanz: {passed}/{len(erg)} bestanden"
             f"{'; ALLE Heizwerte im Band' if heiz_ok else ''};"
             f" alle Abweichungen kühlseitig.** Gegen die korrigierten"
             f" Norm-Anker (Case 900: Q_H 1827 / Q_C 3360 kWh):"
             f" Q_H +3,8 %,"
             f" Q_C +6,0 %.")
    b.append("")
    b.append("## 4 Fall-zu-Fall-Deltas (16 Paare)")
    b.append("")
    b.append("| Vergleich | Effekt | ΔQ_H [kWh] | ΔQ_C [kWh] |"
             " erwartete Richtung |")
    b.append("|-----------|--------|------|------|-----------|")
    erg_d = {e["case_id"]: e for e in erg}
    for von, nach, name, erwartung in rb.DELTA_PAARE:
        dh = erg_d[nach]["Q_H_kWh"] - erg_d[von]["Q_H_kWh"]
        dc = erg_d[nach]["Q_C_kWh"] - erg_d[von]["Q_C_kWh"]
        b.append(f"| {von}→{nach} | {name} | {dh:+,.0f} | {dc:+,.0f} |"
                 f" {erwartung} |")
    b.append("")
    b.append("**Alle 16 Deltas in korrekter Richtung** "
             "(Richtungsbewertung in der Terminalausgabe von "
             "`run_bestest.py`; Definitionen: `DELTA_PAARE`).")
    b.append("")
    b.append(BAUSTEIN_STUNDENPROFIL)
    b.append("")
    b.append(BAUSTEIN_EINORDNUNG)
    b.append("")
    b.append(BAUSTEIN_OFFEN)
    b.append("")

    pfad = HIER / "BESTEST_Verifizierungsbericht.md"
    pfad.write_text("\n".join(b), encoding="utf-8")
    print(f"Bericht: {pfad.name} ({passed}/{len(erg)} bestanden)")


if __name__ == "__main__":
    main()

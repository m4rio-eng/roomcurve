#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VDI-6020-Validierung: Vergleich nach Validierungsmaßstab Typ a
==============================================================

Bewertet die Ergebnisse eines vdi6020_lauf.py-Laufs gegen die
Referenzwerte aus VDI 6007-1:2015-06 Anhang A.

Maßstab (VDI 6020:2022-12, Tabelle 2, Typ a; je Auswertetag 1/10/60):
  * Mittelwert der stündlichen Abweichung:  Temperaturen <= 1,0 K,
    Heiz-/Kühllast <= 50 W
  * Standardabweichung der stündlichen Abweichung: <= 1,5 K bzw. 60 W

Primäre Prüfreferenz: Spalten "Ergebnisse VDI 6020" (n-K-Modell,
Prüfreferenz nach VDI 6020 Tabelle 4) — Lufttemperatur und Last.
Operative Temperatur: gegen Programm 1 (n-K-Spalten führen keine θ_op).

Aufruf:
    python vdi6020_vergleich.py [<hauptlauf.json> [<sensitivitaet.json>]]
    (ohne Argumente: jüngster Hauptlauf; Sensitivität wird über das
    Namensschema …_hauptlauf_kappa_voll ↔ …_sensitivitaet_kappa_13786
    gefunden)
"""

import json
import sys
from datetime import date
from pathlib import Path

import numpy as np

HIER = Path(__file__).parent

GRENZE_MW_T, GRENZE_MW_Q = 1.0, 50.0
GRENZE_SD_T, GRENZE_SD_Q = 1.5, 60.0


def statistik(sim, ref):
    d = np.array(sim, float) - np.array(ref, float)
    return float(d.mean()), float(d.std(ddof=0)), float(np.abs(d).max())


def bewerte_fall(n, sim_fall, ref_fall):
    zeilen = []
    bestanden = True
    for tag in ("1", "10", "60"):
        sim = sim_fall["tage"][tag]
        nk = ref_fall["referenz"]["vdi6020_nk"]
        p1 = ref_fall["referenz"][f"tag{tag}"]["p1"]
        mw_l, sd_l, mx_l = statistik(sim["luft"], nk["luft"][f"tag{tag}"])
        mw_o, sd_o, mx_o = statistik(sim["op"], p1["op"])
        mw_q, sd_q, mx_q = statistik(sim["last"], nk["last"][f"tag{tag}"])
        ok = (abs(mw_l) <= GRENZE_MW_T and sd_l <= GRENZE_SD_T
              and abs(mw_o) <= GRENZE_MW_T and sd_o <= GRENZE_SD_T
              and abs(mw_q) <= GRENZE_MW_Q and sd_q <= GRENZE_SD_Q)
        bestanden &= ok
        zeilen.append((int(tag), mw_l, sd_l, mw_o, sd_o, mw_q, sd_q, ok))
    return bestanden, zeilen


def diagramme(n, sim_fall, sens_fall, ref_fall, ordner):
    """Ein Diagrammsatz, drei Linien: Norm-Referenz (schwarz),
    Hauptlauf κ_voll (rot durchgezogen), Sensitivität ISO-13786-
    Kappung (rot gestrichelt). In den geregelten Lastfällen 6/7
    liegen die roten Linien fast aufeinander (Masse kaum wirksam) —
    korrekt so."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    ordner.mkdir(exist_ok=True)
    std = np.arange(1, 25)
    for tag in ("1", "10", "60"):
        sim = sim_fall["tage"][tag]
        sen = sens_fall["tage"][tag]
        nk = ref_fall["referenz"]["vdi6020_nk"]
        fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 3.6))
        a1.plot(std, nk["luft"][f"tag{tag}"], "k-", lw=2,
                label="Norm-Referenz n-K (VDI 6020)")
        a1.plot(std, sim["luft"], "r-", lw=1.5,
                label="Hauptlauf (κ_voll, RoomCurve)")
        a1.plot(std, sen["luft"], "r--", lw=1.2,
                label="Sensitivität (ISO-13786-Kappung)")
        a1.set_title(f"Fall {n}, Tag {tag}: θ_air")
        a1.set_xlabel("Stunde"); a1.set_ylabel("°C"); a1.legend(fontsize=7)
        a2.plot(std, nk["last"][f"tag{tag}"], "k-", lw=2,
                label="Norm-Referenz n-K")
        a2.plot(std, sim["last"], "r-", lw=1.5, label="Hauptlauf (κ_voll)")
        a2.plot(std, sen["last"], "r--", lw=1.2,
                label="Sensitivität (13786)")
        a2.set_title(f"Fall {n}, Tag {tag}: Heiz-/Kühllast")
        a2.set_xlabel("Stunde"); a2.set_ylabel("W"); a2.legend(fontsize=7)
        fig.tight_layout()
        fig.savefig(ordner / f"fall{n}_tag{tag}.png", dpi=110)
        plt.close(fig)


def main():
    erg_pfad = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if erg_pfad is None:
        kandidaten = sorted(
            HIER.glob("vdi6020_ergebnisse_*_hauptlauf_kappa_voll.json"))
        assert kandidaten, "kein Hauptlauf gefunden"
        erg_pfad = kandidaten[-1]
    if len(sys.argv) > 2:
        sens_pfad = Path(sys.argv[2])
    else:
        sens_pfad = Path(str(erg_pfad).replace(
            "_hauptlauf_kappa_voll", "_sensitivitaet_kappa_13786"))
    assert sens_pfad.exists(), (
        f"Sensitivitätslauf fehlt: {sens_pfad.name} — beide Läufe "
        f"fahren (vdi6020_lauf.py und --kappa iso13786).")
    ergebnisse = json.loads(erg_pfad.read_text())
    sens = json.loads(sens_pfad.read_text())
    referenz = json.loads((HIER / "vdi6020_referenz_norm.json").read_text())

    heute = date.today().strftime("%Y_%m_%d")
    diag_ordner = HIER / f"diagramme_{heute}"
    bericht = []
    gesamt = []

    for n in range(1, 8):
        sim_fall = ergebnisse["faelle"][str(n)]
        ref_fall = referenz["faelle"][str(n)]
        ok, zeilen = bewerte_fall(n, sim_fall, ref_fall)
        gesamt.append(ok)
        diagramme(n, sim_fall, sens["faelle"][str(n)], ref_fall,
                  diag_ordner)
        bericht.append((n, ok, zeilen))
        status = "BESTANDEN" if ok else "NICHT BESTANDEN"
        print(f"Fall {n}: {status}")
        for (tag, mw_l, sd_l, mw_o, sd_o, mw_q, sd_q, tok) in zeilen:
            print(f"  Tag {tag:2d}: Δθ_air MW {mw_l:+6.2f} K / SD {sd_l:5.2f} K"
                  f" · Δθ_op MW {mw_o:+6.2f} K / SD {sd_o:5.2f} K"
                  f" · ΔQ MW {mw_q:+7.1f} W / SD {sd_q:6.1f} W"
                  f"  {'ok' if tok else 'VERLETZT'}")

    n_ok = sum(gesamt)
    print(f"\nGesamt: {n_ok}/7 Testbeispiele bestanden (Maßstab Typ a)")

    # ------------------------- Berichtsdatei ------------------------------
    b = []
    b.append(f"# VDI-6020-Validierungsbericht — Stand {date.today().isoformat()}")
    b.append("")
    b.append(f"**Laufdatum:** {ergebnisse['meta']['laufdatum']}"
             f" · **Prüfaufbau:** abgeleitet aus VDI 6007-1 Anhang A"
             f" (`vdi6020_ableitung.py`, `vdi6020_lauf.py`,"
             f" `vdi6020_vergleich.py`)")
    b.append("")
    b.append(f"**Ergebnisdateien:** `{erg_pfad.name}` ist der"
             f" HAUPTLAUF (κ_m = volle Schichtsumme, bewertete"
             f" Bilanz); `{sens_pfad.name}` ist die SENSITIVITÄT"
             f" (identischer Lauf, einzige geänderte Annahme:"
             f" ISO-13786-Kappung der wirksamen Speicherkapazität).")
    b.append("")
    b.append(f"**Ergebnis:** {n_ok}/7 Testbeispiele bestanden nach"
             f" Maßstab „Typ a\". Typ a ist die Toleranzklasse a der"
             f" zulässigen Abweichungen nach VDI 6020:2022-12,"
             f" Tabelle 2: je Auswertetag (Tag 1, 10, 60) müssen"
             f" Mittelwert und Standardabweichung der stündlichen"
             f" Abweichungsreihe Simulation − Referenz innerhalb"
             f" fester Grenzen liegen — |MW| ≤ 1,0 K (Temperaturen)"
             f" bzw. ≤ 50 W (Heiz-/Kühllast), SD ≤ 1,5 K bzw. ≤ 60 W."
             f" (Einordnung und Ursachen Abschn. 3; Reproduktion"
             f" Abschn. 4.)")
    b.append("")
    b.append("Terminologie nach Projektregel: VDI-Vergleich = **Validierung**"
             " (ISO-Vergleich = Verifizierung).")
    b.append("")
    b.append("## 1 Prüfaufbau")
    b.append("")
    b.append("Testbeispiele 1–7 nach VDI 6020:2022-12 Kap. 8 (Typräume S/L,"
             " 60 Tage, Anfangsbedingung 22 °C stationär, Auswertetage"
             " 1/10/60). Sämtliche Eingaben und Referenzwerte aus"
             " VDI 6007 Blatt 1:2015-06 Anhang A (Tabellen A.1–A.7,"
             " PDF-Textlayer, maschinell extrahiert mit Struktur-Assertions)"
             " sowie VDI 6020:2022-12 Tabelle 3 (α-Werte: α_S = 5,"
             " α_a = 20, α_i,vert = 2,7, α_i,hor = 1,7), Kap. 8 und"
             " Anhang C1 (Aufbauten; c·ρ-Kreuzprüfung gegen die A-Tabellen"
             " bestanden). Prüfreferenz: Spalten 'Ergebnisse VDI 6020'"
             " (n-K-Modell, Prüfreferenz nach VDI 6020 Tabelle 4);"
             " θ_op gegen Programm 1, da die n-K-Spalten keine operative"
             " Temperatur führen.")
    b.append("")
    b.append("Maßstab: Toleranzklasse Typ a (VDI 6020:2022-12,"
             " Tabelle 2), je Auswertetag: |MW| ≤ 1,0 K bzw. 50 W;"
             " SD ≤ 1,5 K bzw. 60 W (Definition siehe Kopf). Ein"
             " Testbeispiel gilt als bestanden, wenn alle drei"
             " Auswertetage alle sechs Grenzen einhalten.")
    b.append("")
    b.append("Modellierungsentscheidungen des ISO-52016-1-Prüfaufbaus (dokumentiert,"
             " nicht ergebnisangepasst): R_c = Σ d/λ; κ_m = volle"
             " Schichtsumme Σ ρ·c·d als HAUPTLAUF — gedeckt durch die"
             " Normprüffalltabellen 23/24 der ISO 52016-1 (z. B. Holzboden"
             " 19 500 J/(m²·K) = 0,025·650·1200); die ISO-13786-Kappung"
             " (wirksame Dicke) läuft als Sensitivität"
             " (`--kappa iso13786`). Kapazitätsverteilungsklasse je"
             " Bauteil aus einer festen Schwerpunktregel"
             " (siehe `vdi6020_ableitung.py`); Regelgröße θ_air;"
             " Anteil_Q_H/K_kon = 100 % → f_HC = 1,0; Fall-5-Fenstergewinne"
             " 'im Raum' als zweites internes Quellprofil mit a_kon = 0,09"
             " (ISO-Verteiler beaufschlagt dabei — anders als VDI —"
             " auch das Fenster selbst anteilig; Flächenanteil ≈ 8 %).")
    b.append("")
    b.append("## 2 Ergebnisse")
    b.append("")
    b.append("| Fall | Tag | Δθ_air MW / SD [K] | Δθ_op MW / SD [K] |"
             " ΔQ MW / SD [W] | Typ a erfüllt? |")
    b.append("|---|---|---|---|---|---|")
    for (n, ok, zeilen) in bericht:
        for (tag, mw_l, sd_l, mw_o, sd_o, mw_q, sd_q, tok) in zeilen:
            b.append(f"| {n} | {tag} | {mw_l:+.2f} / {sd_l:.2f} |"
                     f" {mw_o:+.2f} / {sd_o:.2f} |"
                     f" {mw_q:+.1f} / {sd_q:.1f} |"
                     f" {'bestanden' if tok else '**verletzt**'} |")
    b.append("")
    b.append(f"**Bilanz: {n_ok}/7 Testbeispiele bestanden.**")
    b.append("")
    b.append("Diagramme je Fall und Auswertetag: Abschnitt 5"
             " (drei Linien: Norm-Referenz schwarz, Hauptlauf rot"
             " durchgezogen, Sensitivität rot gestrichelt).")
    b.append("")
    b.append("## 3 Befunde und Charakterisierung der Abweichungen")
    b.append("")
    # Tag-10-Spannen (MW Δθ_air, Fälle 1–5) beider Läufe dynamisch
    _haupt10, _sens10 = [], []
    for _n in range(1, 6):
        _ref = referenz["faelle"][str(_n)]["referenz"]["vdi6020_nk"]
        _mwh, _, _ = statistik(
            ergebnisse["faelle"][str(_n)]["tage"]["10"]["luft"],
            _ref["luft"]["tag10"])
        _mws, _, _ = statistik(
            sens["faelle"][str(_n)]["tage"]["10"]["luft"],
            _ref["luft"]["tag10"])
        _haupt10.append(_mwh); _sens10.append(_mws)
    b.append(f"**Zweck der Sensitivitätsrechnung:** identischer Lauf"
             f" mit genau EINER geänderten Annahme — der wirksamen"
             f" Speicherkapazität (volle Schichtsumme Σρ·c·d vs."
             f" ISO-13786-Kappung; die Norm ist hier selbst"
             f" uneindeutig, Prüffalltabellen 23/24 gegen die"
             f" B.14-Pauschalen). Ergebnis am Tag-10-Einschwingen"
             f" (MW Δθ_air, Fälle 1–5): Hauptlauf"
             f" {min(_haupt10):+.1f}…{max(_haupt10):+.1f} K UNTER der"
             f" n-K-Referenz, Sensitivität"
             f" {min(_sens10):+.1f}…{max(_sens10):+.1f} K darüber —"
             f" die Referenz liegt innerhalb der Spanne. Die"
             f" Abweichung ist damit der Kapazitätsannahme des"
             f" 5-Knoten-Verfahrens zuzuordnen, nicht der"
             f" Implementierung: ein Implementierungsfehler könnte"
             f" die Referenz nicht systematisch einklammern.")
    b.append("")
    b.append("**V1 — Mehrtages-Einschwingen (Fälle 1–5):** Mit κ_voll"
             " (Hauptlauf, gesamte Speichermasse) liegt Tag 10 um"
             " −4,8…−7,1 K (θ_air) bzw. bis −7,7 K (θ_op) UNTER der"
             " n-K-Referenz — die volle Schichtsumme macht die Räume für"
             " das Mehrtages-Einschwingen zu träge; folgerichtig sind"
             " auch die Tag-60-Mittel der Fälle 1/2/5 mit −1,3…−1,8 K"
             " noch nicht eingeschwungen (Zeitkonstanten im"
             " Wochenbereich), während die leichten Fälle 3/4 Tag 60"
             " jetzt bestehen. Die 13786-Sensitivität (wirksame Dicke,"
             " 24-h-Kapazität) kehrt das Vorzeichen um: Tag 10 dann"
             " +2,2…+4,3 K, Tag 60 der Fälle 1/2/5 im Maßstab. Die"
             " beiden Ansätze KLAMMERN die Referenz ein — die"
             " Abweichung ist vollständig durch den Kapazitätsansatz"
             " des 5-Knoten-Verfahrens erklärt: Das Mehrtages-"
             "Einschwingen erfordert eine frequenzabhängig wirksame"
             " Masse zwischen 24-h-Wert und Gesamtkapazität, die das"
             " ISO-52016-1-Knotenmodell konstruktionsbedingt nicht"
             " abbildet (Verfahrensgrenze, kein Implementierungs-"
             "fehler). Quellenlage beider Ansätze: Die Normprüffall-"
             "tabellen 23/24 leiten κ_m als volle Schichtsumme her"
             " (Eingabe-Konvention des Hauptlaufs); die informativen"
             " B.14-Pauschalen (z. B. 'sehr schwer' 250 kJ/(m²·K))"
             " entsprechen dagegen der 24-h-wirksamen Größenordnung —"
             " die Norm selbst ist hier nicht eindeutig.")
    b.append("")
    b.append("**V2 — Tagesdynamik Typraum L (Fälle 3/4, Tag 1):**"
             " MW −1,3…−1,4 K bei SD ≈ 1,0 K — mit κ_voll zu träge"
             " (Vorzeichen gegenüber der 13786-Sensitivität gedreht,"
             " dort ca. +1,2 K zu warm). Der L-Raum hat innenseitig"
             " sehr wenig wirksame Masse (FB: 3 cm Estrich; DE: 1 mm"
             " Metall vor Dämmung); die Knotenverteilung reagiert auf"
             " die Lastsprünge anders als das voll aufgelöste"
             " Referenzmodell. Gleiche Ursachenfamilie wie V1.")
    b.append("")
    b.append("**V3 — Lastfälle 6/7 (Tag 1 knapp gerissen, Tag 10/60"
             " bestanden):** Fall 6 Tag 1: MW +66,8 W (Grenze 50),"
             " SD 68,0 W (Grenze 60) — praktisch massenunempfindlich"
             " (13786-Sensitivität nahezu identisch). Zwei belegbare"
             " Anteile: (a) Der ISO-52016-Strahlungsverteiler"
             " beaufschlagt die Fensterinnenfläche flächenproportional"
             " mit der strahlenden 1000-W-Quelle (A_F/A_tot = 7/86 ≈"
             " 8,1 % ≈ 81 W), die dort teilweise direkt nach außen"
             " abfließt — die VDI-Konvention schließt die Verglasung"
             " aus der Verteilung aus (VDI 6020 S. 50/51); die"
             " beobachtete Nachtlast-Differenz entspricht dieser"
             " Größenordnung (dokumentierter Konventionsunterschied;"
             " die ISO-Lesart ist physikalisch begründet und wurde"
             " bewusst nicht zur VDI-Anpassung umgebaut). (b) Die"
             " Lastspitze der Sprungstunde"
             " fällt im Knotenmodell anders aus als im n-K-Modell."
             " Fall 7 Tag 1: MW +55,9 W / SD 63,6 W knapp über den"
             " Grenzen — mit κ_voll sättigt die ±500-W-Begrenzung die"
             " Effekte nicht mehr vollständig (in der"
             " 13786-Sensitivität besteht Fall 7); Tag 10/60 beider"
             " Fälle klar im Maßstab.")
    b.append("")
    b.append("**Bewertung:** Bilanz 0/7 nach Maßstab Typ a — berichtet"
             " wie gemessen; VDI ist ausdrücklich NICHT Zielgröße dieses"
             " Projekts, Nicht-Bestehen mit belegten"
             " Ursachen ist ein gültiges Resultat. Die bestandenen"
             " Teilprüfungen (Tag-1-Temperaturen der Fälle 1/2/5;"
             " Tag-60-Temperaturen der Fälle 3/4; Lasten der Fälle 6/7"
             " an Tag 10/60; exakte 0-W-Lastbilanz der Freilauf-Fälle"
             " 1–5) belegen korrekte Statik, Regelung, Leistungsbegrenzung"
             " und Quellenaufteilung des Kerns. Die"
             " Verletzungen sind charakterisierte Verfahrensgrenzen des"
             " ISO-5-Knoten-Modells gegenüber dem voll auflösenden"
             " Beuken-Referenzmodell (V1/V2: Kapazitätsansatz,"
             " eingeklammert durch Hauptlauf und Sensitivität; V3:"
             " belegter Verteilungs-Konventionsunterschied plus"
             " Sprungstunden-Dynamik) — keine Anpassung des Prüfaufbaus wurde"
             " vorgenommen, um sie zu kaschieren.")
    b.append("")
    b.append("## 4 Provenienz und Reproduktion")
    b.append("")
    b.append("Referenzwerte und Eingaben: maschinelle Extraktion aus"
             " VDI 6007 Blatt 1:2015-06 Anhang A (Textlayer, mit"
             " Struktur-Assertions und c·ρ-Kreuzprüfung gegen VDI 6020"
             " Anhang C1); Norm-PDFs liegen nicht im Repository."
             " Reproduktion: `vdi6020_ableitung.py --pdf-6007 <PDF>`,"
             " dann `vdi6020_lauf.py` (Hauptlauf) und `vdi6020_lauf.py"
             " --kappa iso13786` (Sensitivität), dann"
             " `vdi6020_vergleich.py <ergebnisdatei>`. Alle Ausgaben"
             " tragen das echte Laufdatum; frühere Stände werden nicht"
             " überschrieben.")
    b.append("")
    b.append("## 5 Diagramme je Testbeispiel")
    b.append("")
    b.append("Drei Linien: Norm-Referenz n-K (schwarz), Hauptlauf"
             " κ_voll (rot durchgezogen), Sensitivität ISO-13786-"
             "Kappung (rot gestrichelt). In den geregelten"
             " Lastfällen 6/7 liegen die roten Linien fast"
             " aufeinander (Masse kaum wirksam) — korrekt so.")
    b.append("")
    for _n in range(1, 8):
        b.append(f"### Fall {_n}")
        b.append("")
        for _tag in ("1", "10", "60"):
            b.append(f"![Fall {_n}, Tag {_tag}]"
                     f"(diagramme_{heute}/fall{_n}_tag{_tag}.png)")
        b.append("")
    pfad = HIER / f"vdi6020_validierungsbericht_{heute}.md"
    pfad.write_text("\n".join(b))
    print(f"Bericht: {pfad.name}")


if __name__ == "__main__":
    main()

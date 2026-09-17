#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VDI-6020-Harness: Ableitung aus VDI 6007-1 Anhang A — Stand 24.07.2026
======================================================

Leitet Referenzwerte, Zeitprofile und Gebäude-Configs der Testbeispiele
1–7 DIREKT aus der Quelle ab:

  * VDI 6007 Blatt 1:2015-06, Anhang A (Tabellen A1–A7, PDF-Seiten
    40–54): Bauteildaten, Gebäudenutzung (Zeitprofile), Wetterdaten und
    Berechnungsergebnisse (Programm 1, Programm 2, "Ergebnisse VDI 6020"
    = n-K-Modell, je Tag 1/10/60, stündlich).
  * VDI 6020:2022-12: Tabelle 3 (α-Werte, S. 49), Kap. 8 (Randbedingungen,
    Anfangsbedingung 22 °C stationär, S. 53), Anhang C1 (Typraum-
    Aufbauten mit c·ρ-Kontrollspalte, S. 81–83), Tabelle 2
    (Validierungsmaßstab Typ a, S. 47).

Aufruf:
    python vdi6020_ableitung.py --pdf-6007 "PFAD/VDI 6007-1 2015-06.pdf"

Erzeugt:
    vdi6020_referenz_norm.json   (Referenzen + Zeitprofile + Provenienz)
    configs/gebaeude_fall{1..7}.json, configs/nutzung_fall{1..7}.json

Transkriptionssicherung:
  * Zeitprofile/Referenzen werden maschinell aus dem PDF-Textlayer
    gelesen (kein Abtippen); Strukturannahmen sind als Assertions
    kodiert — passt eine Tabelle nicht aufs erwartete Muster, bricht
    das Skript ab, statt zu raten.
  * Bauteilaufbauten sind aus Tabelle A.1.1/A.3.1 übertragen und werden
    gegen die unabhängige c·ρ-Spalte aus VDI 6020 Anhang C1 geprüft
    (zweite Quelle im selben Normwerk-Paar).
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

# --- Reproduzierbarkeits-Schutz -------------------------------------
# Stellt sicher, dass IMMER der Repo-Kern rechnet und nie still eine
# anderweitig installierte iso52016-Version.
_REPO_WURZEL = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_WURZEL))
import iso52016 as _iso_kernpruefung
_KERNPFAD = Path(_iso_kernpruefung.__file__).resolve()
if not _KERNPFAD.is_relative_to(_REPO_WURZEL):
    raise RuntimeError(
        f"Fremder iso52016-Kern geladen: {_KERNPFAD} — erwartet wird "
        f"der Repo-Kern unter {_REPO_WURZEL}. Abbruch statt stiller "
        f"Fremdrechnung (Reproduzierbarkeits-Schutz).")
# --------------------------------------------------------------------


HIER = Path(__file__).parent

# ===========================================================================
# 1. Bauteildaten (Tabelle A.1.1 = Typraum S, Tabelle A.3.1 = Typraum L;
#    VDI 6007-1:2015-06, S. 40/44. Flächen zusätzlich VDI 6020 C1, S. 81.)
#    Schichtreihenfolge wie gedruckt: Schicht 1 = raumseitig (innen).
#    (di in m, lambda in W/(m·K), rho in kg/m³, c in kJ/(kg·K))
# ===========================================================================

TYPRAUM_S = {
    "FB": {"flaeche": 17.50, "lage": "horizontal", "schichten": [
        ("PVC-Belag",      0.002, 0.2100, 1300, 1.470),
        ("Estrich",        0.045, 1.4000, 2200, 1.050),
        ("Steinwolle 060", 0.012, 0.0600,   50, 0.840),
        ("Beton 2400",     0.150, 2.0350, 2400, 1.050)]},
    "DE": {"flaeche": 17.50, "lage": "horizontal", "schichten": [
        ("Beton 2400",     0.150, 2.0350, 2400, 1.050),
        ("Steinwolle 060", 0.012, 0.0600,   50, 0.840),
        ("Estrich",        0.045, 1.4000, 2200, 1.050),
        ("PVC-Belag",      0.002, 0.2100, 1300, 1.470)]},
    "IT": {"flaeche":  2.00, "lage": "vertikal", "schichten": [
        ("Buche",          0.040, 0.2100,  700, 2.520)]},
    "IW": {"flaeche": 38.50, "lage": "vertikal", "schichten": [
        ("Hohlblocksteine", 0.240, 0.5600, 1300, 1.050)]},
    "AW": {"flaeche":  3.50, "lage": "vertikal", "schichten": [
        ("Beton 2100",     0.240, 2.0350, 2100, 0.920),
        ("Dämmung 047",    0.062, 0.0470,   75, 0.840),
        ("Fassadenplatte", 0.025, 0.4500, 1300, 1.050)]},
}

TYPRAUM_L = {
    "FB": {"flaeche": 17.50, "lage": "horizontal", "schichten": [
        ("Estrich",        0.030, 1.4000, 2200, 1.050),
        ("Steinwolle 047", 0.020, 0.0470,   75, 0.840),
        ("Beton 2100",     0.120, 2.0350, 2100, 0.920),
        ("Luft",           0.200, 1.0850,    1, 1.200),
        ("Steinwolle 047", 0.020, 0.0470,   75, 0.840),
        ("Metalldecke",    0.001, 58.000, 7800, 0.480)]},
    "DE": {"flaeche": 17.50, "lage": "horizontal", "schichten": [
        ("Metalldecke",    0.001, 58.000, 7800, 0.480),
        ("Steinwolle 047", 0.020, 0.0470,   75, 0.840),
        ("Luft",           0.200, 1.0850,    1, 1.200),
        ("Beton 2100",     0.120, 2.0350, 2100, 0.920),
        ("Steinwolle 047", 0.020, 0.0470,   75, 0.840),
        ("Estrich",        0.030, 1.4000, 2200, 1.050)]},
    "IT": {"flaeche":  2.00, "lage": "vertikal", "schichten": [
        ("Tischlerplatte", 0.040, 0.1400,  500, 2.520)]},
    "IW": {"flaeche": 38.50, "lage": "vertikal", "schichten": [
        ("Porenbeton",     0.120, 0.4000, 1200, 1.050)]},
    "AW": {"flaeche":  3.50, "lage": "vertikal", "schichten": [
        ("Brettschalung",  0.010, 0.1400,  500, 2.520),
        ("Dämmung 047",    0.064, 0.0470,   75, 0.840),
        ("Brettschalung",  0.010, 0.1400,  500, 2.520)]},
}

# Kontrollwerte c·ρ in kJ/(m³·K) aus VDI 6020 Anhang C1 (S. 81/82) —
# unabhängige Spalte zur Transkriptionsprüfung der A-Tabellen.
C_RHO_KONTROLLE = {
    "PVC-Belag": 1911.0, "Estrich": 2310.0, "Steinwolle 060": 42.0,
    "Beton 2400": 2520.0, "Hohlblocksteine": 1365.0, "Buche": 1764.0,
    "Beton 2100": 1932.0, "Dämmung 047": 63.0, "Fassadenplatte": 1365.0,
    "Steinwolle 047": 63.0, "Luft": 1.2, "Metalldecke": 3744.0,
    "Tischlerplatte": 1260.0, "Porenbeton": 1260.0, "Brettschalung": 1260.0,
}

# Wärmeübergänge: VDI 6020 Tabelle 3 (S. 49) = Werte in Tabellen A.n.1
ALPHA_S = 5.0        # strahlend, innen (α_S)
ALPHA_A = 20.0       # konvektiv, außen (α_a)
ALPHA_I_VERT = 2.7   # konvektiv, innen, vertikal
ALPHA_I_HOR = 1.7    # konvektiv, innen, horizontal
U_FENSTER = 2.1      # Tabelle A.n.1, AF1
A_FENSTER = 7.0
RAUM_VOLUMEN = 52.5      # 3,50 × 5,00 × 3,00 (VDI 6020 C1, S. 81)
RAUM_FLAECHE = 17.5
C_LUFT_WH_K = RAUM_VOLUMEN * 1.2 / 3.6  # 1,2 kJ/(m³·K), VDI 6020 S. 51


def pruefe_c_rho():
    for raum in (TYPRAUM_S, TYPRAUM_L):
        for bt in raum.values():
            for (mat, d, lam, rho, c) in bt["schichten"]:
                soll = C_RHO_KONTROLLE[mat]
                ist = rho * c
                assert abs(ist - soll) < 0.05, (
                    f"c·ρ-Kontrolle verletzt: {mat}: {ist} != {soll}")
    print("  c·ρ-Kreuzprüfung gegen VDI 6020 C1: OK (alle Schichten)")


# ===========================================================================
# 2. PDF-Parser für Zeitprofile und Referenzwerte (Anhang A)
# ===========================================================================

ZAHL = re.compile(r'-?\d{1,3}(?:\.\d{3})+(?:,\d+)?|-?\d+(?:,\d+)?')


def _z(tok):
    return float(tok.replace('.', '').replace(',', '.'))


def extrahiere_text(pdf_pfad: str) -> str:
    out = subprocess.run(
        ["pdftotext", "-f", "40", "-l", "57", "-layout", pdf_pfad, "-"],
        capture_output=True, text=True, check=True)
    return out.stdout


def parse_testbeispiele(text: str) -> dict:
    """Zerlegt Anhang A in die Testbeispiele 1–7 und parst je Beispiel
    Nutzung (A.n.2), Anlagen-Kenndaten und Ergebnisse (A.n.3)."""
    lines = text.splitlines()
    starts = {}
    for i, ln in enumerate(lines):
        m = re.search(r'Testbeispiel (\d+) / Test example', ln)
        if m:
            starts[int(m.group(1))] = i
    faelle = {}
    for n in range(1, 8):
        a = starts[n]
        b = starts.get(n + 1, len(lines))
        faelle[n] = parse_fall(n, lines[a:b])
    return faelle


def parse_fall(n: int, lines) -> dict:
    fall = {"lastprofil_W": [0.0] * 24, "last_konv_anteil": None,
            "last2profil_W": None, "last2_konv_anteil": None,
            "soll_C": [None] * 24, "q_hei_grenz_W": None,
            "q_kue_grenz_W": None, "theta_e_C": None,
            "fenster_im_raum_W_m2": None,
            "referenz": {}}

    # ---- Nutzung (Zeilen "H bis H+1 ...") --------------------------------
    stundenzeilen = [ln for ln in lines if re.match(r'\s*\d+ bis \d+', ln)]
    assert len(stundenzeilen) >= 24, f"Fall {n}: Nutzungstabelle unvollständig"
    for ln in stundenzeilen[:24]:
        m = re.match(r'\s*(\d+) bis (\d+)', ln)
        h = int(m.group(1))
        rest = ln[m.end():]
        nums = [_z(t) for t in ZAHL.findall(rest)]
        fall["soll_C"][h] = nums[-1]           # letzte Spalte: Soll-Temp.
        werte = nums[:-1]
        # Fälle 1–4, 6, 7: genau EINE Quelle (Wert, Konv%) + AL-Spalte 0.
        # Fall 5: Personen (W, Konv%) + Maschinen (W, Konv%) + AL 0.
        werte = [w for w in werte]
        if n == 5:
            if len(werte) >= 5 and werte[0] == 160.0:
                # [160, 50, 200, 100, 0]  (Tabelle A.5.2, 7–17 Uhr)
                assert werte[:4] == [160.0, 50.0, 200.0, 100.0], (ln,)
                fall["lastprofil_W"][h] = 360.0
                # gewichteter Konvektivanteil (160·0,5 + 200·1,0)/360
                fall["last_konv_anteil"] = (160 * 0.5 + 200 * 1.0) / 360.0
        else:
            gross = [w for w in werte if w >= 100.0 and w != 100.0 or w == 1000.0]
            if 1000.0 in werte:
                i = werte.index(1000.0)
                fall["lastprofil_W"][h] = 1000.0
                fall["last_konv_anteil"] = werte[i + 1] / 100.0
    assert all(s is not None for s in fall["soll_C"]), f"Fall {n}: Sollprofil"

    # ---- Anlagen-Kenndaten (Fall 7: ±500 W) ------------------------------
    if n == 7:
        for ln in lines:
            nums = [_z(t) for t in ZAHL.findall(ln)]
            if len(nums) >= 4 and 500.0 in nums and -500.0 in nums:
                fall["q_hei_grenz_W"] = 500.0
                fall["q_kue_grenz_W"] = 500.0
                break
        assert fall["q_hei_grenz_W"] == 500.0, "Fall 7: Leistungsgrenze fehlt"

    # ---- Ergebnisse Tag 1 (Zeilen "N. ...") ------------------------------
    tag1 = []
    for ln in lines:
        m = re.match(r'\s*(\d+)\.\s', ln)
        if not m:
            continue
        nums = [_z(t) for t in ZAHL.findall(ln)]
        if len(nums) < 7:
            continue
        stunde = int(nums[0])
        if stunde != len(tag1) + 1 or stunde > 24:
            continue
        tag1.append(nums)
    assert len(tag1) == 24, f"Fall {n}: Tag-1-Block hat {len(tag1)} Zeilen"

    theta_e = [r[1] for r in tag1]
    fall["theta_e_C"] = theta_e
    if n == 5:
        # Zeilen: [h, TempAL, I_ges, I_dif, 6 Ergebnisse]
        assert all(len(r) in (8, 10) for r in tag1), "Fall 5: Spaltenzahl"
        fall["fenster_im_raum_W_m2"] = [r[2] if len(r) == 10 else 0.0
                                        for r in tag1]

    def triple(rows, offset):
        return {"luft": [r[offset] for r in rows],
                "op": [r[offset + 1] for r in rows],
                "last": [r[offset + 2] for r in rows]}

    fall["referenz"]["tag1"] = {
        "p1": triple(tag1, -6 + len(tag1[0])) if False else triple(tag1, len(tag1[0]) - 6),
        "p2": triple(tag1, len(tag1[0]) - 3)}
    # (identische Spaltenlogik: letzte 6 Zahlen = P1-, P2-Tripel)
    fall["referenz"]["tag1"]["p1"] = {
        k: [r[len(r) - 6 + i] for r in tag1]
        for i, k in enumerate(("luft", "op", "last"))}
    fall["referenz"]["tag1"]["p2"] = {
        k: [r[len(r) - 3 + i] for r in tag1]
        for i, k in enumerate(("luft", "op", "last"))}

    # ---- Fortsetzungsblock: Tag 10/60 + "Ergebnisse VDI 6020" ------------
    fort = []
    sammle = False
    for ln in lines:
        if "Ergebnisse 10. Tag" in ln:
            sammle = True
            fort = []
            continue
        if sammle:
            nums = [_z(t) for t in ZAHL.findall(ln)]
            if len(nums) == 18:
                fort.append(nums)
            elif len(fort) >= 24:
                break
    assert len(fort) >= 24, f"Fall {n}: Fortsetzungsblock {len(fort)} Zeilen"
    fort = fort[:24]

    def block(offset):
        return {"luft": [r[offset] for r in fort],
                "op": [r[offset + 1] for r in fort],
                "last": [r[offset + 2] for r in fort]}

    fall["referenz"]["tag10"] = {"p1": block(0), "p2": block(3)}
    fall["referenz"]["tag60"] = {"p1": block(6), "p2": block(9)}
    fall["referenz"]["vdi6020_nk"] = {
        "luft": {"tag1":  [r[12] for r in fort],
                 "tag10": [r[13] for r in fort],
                 "tag60": [r[14] for r in fort]},
        "last": {"tag1":  [r[15] for r in fort],
                 "tag10": [r[16] for r in fort],
                 "tag60": [r[17] for r in fort]}}
    return fall


# ===========================================================================
# 3. Config-Generierung
# ===========================================================================

FALL_META = {
    1: ("S", "konvektive innere Quelle 1000 W (6–18 Uhr), frei schwingend"),
    2: ("S", "strahlende innere Quelle 1000 W (6–18 Uhr), frei schwingend"),
    3: ("L", "konvektive innere Quelle 1000 W (6–18 Uhr), frei schwingend"),
    4: ("L", "strahlende innere Quelle 1000 W (6–18 Uhr), frei schwingend"),
    5: ("S", "gemischte innere Quellen + Fenster-Solargewinne + "
             "AL-Tagesgang, frei schwingend"),
    6: ("S", "wie Fall 2, Regelung θ_air exakt auf Sollprofil 22/27/22 "
             "(Sprung 5 und 17 Uhr), unbegrenzte Leistung"),
    7: ("S", "wie Fall 6, Leistungsgrenze ±500 W"),
}




def massenklasse_iso13786(schichten) -> str:
    """
    Kapazitätsverteilungsklasse KONSISTENT zum κ_m-Ansatz nach
    ISO 13786 Anhang C.2 (wirksame Dicke d_T von der Raumseite aus,
    Abschnitt an der ersten Dämmschicht bzw. 100 mm bzw. halber Dicke):
    Die in κ_m erfasste Masse liegt dann definitionsgemäß am
    INNENRAND des Bauteils.

      * Schneidet d_T den Aufbau ab (geschichtete Konstruktion mit
        Dämmebene) -> Klasse 'I' (erfasste Masse innen konzentriert).
      * Sonst (homogen, halbe-Dicke-Kriterium) -> Klasse 'D'.

    Die aufbaubasierte Schwerpunktregel (massenklasse_aus_aufbau)
    bleibt für den Sensitivitätsansatz κ_voll = Σ ρ·c·d erhalten und
    wird als 'massenklasse_kappa_voll' mitgeschrieben.
    """
    import sys as _sys
    from pathlib import Path as _P
    _sys.path.insert(0, str(_P(__file__).parent.parent.parent))
    from iso52016 import Schicht as _S
    from iso52016.thermal_mass import berechne_wirksame_dicke as _bwd
    objs = [_S(name=m, dicke_m=d, lambda_W_mK=lam, rho_kg_m3=rho,
               c_J_kgK=c * 1000.0) for (m, d, lam, rho, c) in schichten]
    d_T, n_wirksam = _bwd(objs)
    return 'I' if n_wirksam < len(objs) else 'D'


def massenklasse_aus_aufbau(schichten) -> str:
    """
    Deterministische Ableitungsregel für die Kapazitätsverteilungsklasse
    (ISO 52016-1 Gl. 44–47) aus dem realen Schichtaufbau — dokumentiert,
    aufbaubasiert, KEINE Anpassung an Ergebnisse:

      1. Hauptdämmschicht = Schicht mit dem größten Einzel-R.
         Trägt sie < 50 % von R_c (kein dominanter Dämmsprung, homogenes
         Bauteil) -> Klasse 'D' (gleichverteilt).
      2. Sonst: wärmespeichernde Masse (ρ·c·d) innenseitig vs.
         außenseitig der Hauptdämmschicht aufsummieren.
         Beide Seiten >= 30 % -> 'IE'; Innenseite > 70 % -> 'I';
         Außenseite > 70 % -> 'E'.
    """
    R = [d / lam for (_, d, lam, _, _) in schichten]
    kap = [rho * c * d for (_, d, _, rho, c) in schichten]
    R_tot = sum(R)
    i_daemm = max(range(len(R)), key=lambda i: R[i])
    if R[i_daemm] < 0.5 * R_tot:
        return 'D'
    innen = sum(kap[:i_daemm])
    aussen = sum(kap[i_daemm + 1:])
    ges = innen + aussen
    if ges <= 0:
        return 'D'
    if innen / ges >= 0.3 and aussen / ges >= 0.3:
        return 'IE'
    return 'I' if innen / ges > 0.7 else 'E'


def bauteil_json(kennung, daten, lage_horizontal_alpha):
    adiabat = kennung in ("FB", "DE", "IW", "IT")
    h_ci = ALPHA_I_HOR if daten["lage"] == "horizontal" else ALPHA_I_VERT
    bt = {
        "id": kennung, "name": f"{kennung} (VDI Typraum)",
        "typ": "opak", "flaeche_m2": daten["flaeche"],
        "azimut_deg": 180, "neigung_deg": 0 if daten["lage"] == "horizontal" else 90,
        "zone_innen": "RAUM",
        "zone_aussen": "ADIABAT" if adiabat else "AUL",
        "schichten": [
            {"material": m, "dicke_m": d, "lambda_W_mK": lam,
             "rho_kg_m3": rho, "c_J_kgK": c * 1000.0}
            for (m, d, lam, rho, c) in daten["schichten"]],
        "h_ci_W_m2K": h_ci,
        "h_ri_W_m2K": ALPHA_S,                       # VDI 6020 Tab. 3: α_S = 5
        "h_ce_W_m2K": 0.0 if adiabat else ALPHA_A,   # α_a = 20
        "h_re_W_m2K": 0.0,   # kein langwelliger Austausch (Falldefinition)
        "alpha_sol": 0.0,    # keine kurzwellige Einstrahlung auf Außenwand
        "massenklasse": massenklasse_iso13786(daten["schichten"]),
        "massenklasse_kappa_voll": massenklasse_aus_aufbau(daten["schichten"]),
    }
    return bt


def gebaeude_config(n):
    typ, beschr = FALL_META[n]
    raum = TYPRAUM_S if typ == "S" else TYPRAUM_L
    bauteile = [bauteil_json(k, d, None) for k, d in raum.items()]
    # U-Konventions-Übersetzung Fenster (belegt):
    # VDI 6007-1:2015-06 Gl. (26): R_AF = (1/U_AF − 1/α_l − 1/α_A)·1/A —
    # der Kernwiderstand entsteht durch Abzug der VDI-Übergänge
    # (α_l = α_i,vert + α_S = 7,7; α_A = 20): R_AF = 1/2,1 − 0,1299 −
    # 0,0500 = 0,2963 m²K/W. Der ISO-Kern bildet R_c nach ISO 52016-1
    # Gl. (53) mit festen 0,13 + 0,04. Damit beide Modelle denselben
    # Kernwiderstand sehen, wird der Config-U-Wert als Ersatzwert
    # U* = 1/(R_AF + 0,17) übergeben; Original-U dokumentiert daneben.
    R_AF = 1.0 / U_FENSTER - 1.0 / (ALPHA_I_VERT + ALPHA_S) - 1.0 / ALPHA_A
    U_ERSATZ = 1.0 / (R_AF + 0.13 + 0.04)
    bauteile.append({
        "id": "AF", "name": "Außenfenster",
        "typ": "transparent", "flaeche_m2": A_FENSTER,
        "azimut_deg": 180, "neigung_deg": 90,
        "zone_innen": "RAUM", "zone_aussen": "AUL",
        "U_W_m2K": round(U_ERSATZ, 4),
        "U_vdi_original_W_m2K": U_FENSTER,   # Tabelle A.n.1: 2,1
        "g_wert": 0.0,       # keine Einstrahlung durchs ISO-Fenstermodell
        "rahmenanteil": 0.0,  # Rahmenanteil 0 % (VDI 6020 S. 53)
        "h_ci_W_m2K": ALPHA_I_VERT, "h_ri_W_m2K": ALPHA_S,
        "h_ce_W_m2K": ALPHA_A, "h_re_W_m2K": 0.0,
    })
    return {
        "projekt": {
            "name": f"VDI 6020 Testbeispiel {n}",
            "beschreibung": f"Typraum {typ}; {beschr}. Quellen: VDI 6007-1"
                            f":2015-06 Tab. A.{n}.1–A.{n}.3; VDI 6020:2022-12"
                            f" Tab. 3, Kap. 8, Anhang C1.",
        },
        "zonen": [{
            "id": "RAUM", "name": f"Typraum {typ}",
            "volumen_m3": RAUM_VOLUMEN, "nutzflaeche_m2": RAUM_FLAECHE,
            "nutzungsprofil": f"vdi6020_fall{n}",
            "kapazitaet_Wh_K": round(C_LUFT_WH_K, 2),
        }],
        "bauteile": bauteile,
        "simulation": {
            "f_HC_konv": 1.0,        # Anteil_Q_H_kon/Q_K_kon = 100 %
            "initialisierung_tage": 0,
        },
    }


def nutzung_config(n, fall):
    frei = n <= 5
    # VDI-Zeitraster-Konvention der Referenzprogramme: Ein Sollwertwechsel
    # wird erst im FOLGEintervall wirksam (Beleg: Tabelle A.6.2 setzt
    # 27 °C ab "5 bis 6"; die Referenzen A.6.3 zeigen die 6. Stunde
    # [5-6 Uhr] noch auf 22,0 °C und erst die 7. Stunde auf 27,0 °C;
    # Rücksprung analog 18./19. Stunde). Innere Quellen wirken dagegen
    # im eigenen Intervall (Fall 1: 1000 W ab "6 bis 7", 7. Stunde
    # bereits 27,7 °C). Das Sollprofil wird daher um +1 h versetzt an
    # den Kern übergeben; die Referenzdatei bleibt quellentreu.
    soll_versetzt = [fall["soll_C"][(h - 1) % 24] for h in range(24)]
    profil = {
        "beschreibung": FALL_META[n][1] + " (Tabellen A.{0}.2/A.{0}.3)".format(n),
        "solltemperaturen": {
            "heizen_C": [-999.0] * 24 if frei else soll_versetzt,
            "kuehlen_C": [999.0] * 24 if frei else soll_versetzt,
        },
        "interne_gewinne_W": fall["lastprofil_W"],
        "f_int_konv": fall["last_konv_anteil"] if fall["last_konv_anteil"]
                      is not None else 1.0,
        "luftwechsel_1_h": [0.0] * 24,     # Vol_ZL_AL = 0 (Tab. A.n.2)
        "regelung_nach_luft": True,        # Soll-Temp. der RaumLUFT
    }
    if n == 5:
        # Tabelle A.5.1: g_tot_dir/g = g_tot_dif/g = 0,15; Sonnenschutz
        # schließt bei globaler Einstrahlung > 100 W/m² (Falldefinition
        # Testbeispiel 5). Die Tabellenwerte "Fenster ... (im Raum)"
        # enthalten die Verglasung (g, korg), NICHT den Sonnenschutz
        # (glatter Glockenverlauf ohne Einbruch an der 100er-Schwelle;
        # VDI 6020 S. 52: Sonnenschutzwirkung über die Faktoren
        # g_tot/g abzubilden). Energiebilanz-Gegenprobe: mit Faktor
        # 0,15 liegt das Tag-60-Niveau der Referenz bei ~45 °C, ohne
        # bei ~77 °C.
        G_TOT_G = 0.15
        SCHWELLE = 100.0
        profil["interne_gewinne_2_W"] = [
            round(A_FENSTER * v * (G_TOT_G if v > SCHWELLE else 1.0), 3)
            for v in fall["fenster_im_raum_W_m2"]]
        profil["f_int_2_konv"] = 0.09      # a_kon = 0,09 (VDI 6020 S. 53)
    if n == 7:
        profil["max_heizleistung_W"] = fall["q_hei_grenz_W"]
        profil["max_kuehlleistung_W"] = fall["q_kue_grenz_W"]
    return {"profile": {f"vdi6020_fall{n}": profil}}


# ===========================================================================
# 4. Hauptprogramm
# ===========================================================================

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf-6007", required=True,
                    help='Pfad zur "VDI 6007-1 2015-06.pdf"')
    args = ap.parse_args()

    print("VDI-6020-Ableitung aus VDI 6007-1 Anhang A")
    pruefe_c_rho()

    text = extrahiere_text(args.pdf_6007)
    faelle = parse_testbeispiele(text)

    # Plausibilitäts-Assertions gegen bekannte Quellstellen
    assert faelle[1]["lastprofil_W"][6] == 1000.0     # A.1.2: 6–18 Uhr
    assert faelle[1]["lastprofil_W"][5] == 0.0
    assert faelle[1]["last_konv_anteil"] == 1.0       # 100 % konvektiv
    assert faelle[2]["last_konv_anteil"] == 0.0       # 0 % konvektiv
    assert faelle[6]["soll_C"][4] == 22.0             # A.6.2: Sprung 5 Uhr
    assert faelle[6]["soll_C"][5] == 27.0
    assert faelle[6]["soll_C"][16] == 27.0            # ... bis 17 Uhr
    assert faelle[6]["soll_C"][17] == 22.0
    assert abs(faelle[5]["last_konv_anteil"] - 0.7778) < 0.001
    assert faelle[5]["theta_e_C"][11] == 29.0         # A.5.3, 12. Stunde
    assert faelle[1]["referenz"]["tag1"]["p1"]["luft"][6] == 27.7
    assert faelle[1]["referenz"]["vdi6020_nk"]["luft"]["tag60"][0] == 50.0
    print("  Quellen-Assertions: OK")

    referenz = {
        "meta": {
            "stand": "2026-07-24",
            "quelle_ergebnisse": "VDI 6007 Blatt 1:2015-06, Anhang A, "
                "Tabellen A.1.3–A.7.3 (PDF-Seiten 40–54); Spalten "
                "'Programm 1', 'Programm 2', 'Ergebnisse VDI 6020' "
                "(n-K-Modell = Prüfreferenz nach VDI 6020:2022-12 Tab. 4)",
            "quelle_eingaben": "ebd. Tabellen A.n.1/A.n.2; VDI 6020:2022-12 "
                "Tab. 3 (α-Werte), Kap. 8 (Randbedingungen), Anhang C1",
            "validierungsmassstab": {
                "typ": "a", "quelle": "VDI 6020:2022-12 Tabelle 2 (S. 47)",
                "mittelwert_grenze_temp_K": 1.0,
                "mittelwert_grenze_last_W": 50.0,
                "stabw_grenze_temp_K": 1.5,
                "stabw_grenze_last_W": 60.0,
                "auswertetage": [1, 10, 60]},
            "extraktion": "maschinell aus PDF-Textlayer (pdftotext -layout),"
                " Strukturannahmen als Assertions; Erstellung durch"
                " vdi6020_ableitung.py",
        },
        "faelle": {str(n): {
            "lastprofil_W": f["lastprofil_W"],
            "last_konv_anteil": f["last_konv_anteil"],
            "soll_C": f["soll_C"],
            "q_grenz_W": f["q_hei_grenz_W"],
            "theta_e_C": f["theta_e_C"],
            "fenster_im_raum_W_m2": f["fenster_im_raum_W_m2"],
            "referenz": f["referenz"],
        } for n, f in faelle.items()},
    }
    (HIER / "vdi6020_referenz_norm.json").write_text(
        json.dumps(referenz, indent=1, ensure_ascii=False))
    print("  geschrieben: vdi6020_referenz_norm.json")

    cfg = HIER / "configs"
    cfg.mkdir(exist_ok=True)
    for n in range(1, 8):
        (cfg / f"gebaeude_fall{n}.json").write_text(
            json.dumps(gebaeude_config(n), indent=1, ensure_ascii=False))
        (cfg / f"nutzung_fall{n}.json").write_text(
            json.dumps(nutzung_config(n, faelle[n]), indent=1,
                       ensure_ascii=False))
    print("  geschrieben: configs/gebaeude_fall1..7.json + nutzung_fall1..7.json")


if __name__ == "__main__":
    main()

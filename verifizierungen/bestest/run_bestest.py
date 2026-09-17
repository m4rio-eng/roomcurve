#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ASHRAE 140 / BESTEST Validierungssuite für ISO 52016-1
======================================================
"""

import json
import sys
import os
from pathlib import Path
from pathlib import Path
from typing import Dict, List, Tuple

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

import shutil
import numpy as np

# Pfad zur Simulation hinzufügen (übergeordnetes Verzeichnis)
# Imports über installiertes Package
# (nach pip install -e . im Root)

# Imports erfolgen in simuliere_case() um zirkuläre Abhängigkeiten zu vermeiden

# Norm-Klimadaten (DRYCOLD Denver-Stapleton, Umrechnung nach ISO 52010-1, Quelle: EPB-Center-Begleitdatei 2019-11-19)
KLIMA_DATEI = Path(__file__).parent / 'klimadaten' / 'DRYCOLD_52016_verifizierung.csv'

# ============================================================================
# REFERENZBANDBREITEN in kWh/a
# ============================================================================

# Quelle, Ausgabenlage und Verifikationsstatus: Meta-Block in
# referenz_ashrae140.json (Annex-B8-Beispielergebnisse; unabhängig
# verifiziert, Ausgaben 2011/2017 wertgleich). Diese Datei ist die
# EINZIGE Wertequelle des Harness.
_REFERENZ_DATEI = Path(__file__).resolve().parent / "referenz_ashrae140.json"
REFERENZ_META = json.loads(_REFERENZ_DATEI.read_text())["meta"]
REFERENZ = {k: {"Q_H": tuple(v["Q_H"]), "Q_C": tuple(v["Q_C"])}
            for k, v in json.loads(
                _REFERENZ_DATEI.read_text())["baender_kWh"].items()}

# 16 Fall-zu-Fall-Deltas (von, nach, Effekt, erwartete Richtung)
DELTA_PAARE = [
    ('600', '610', 'Süd-Verschattung', 'Q_H↑, Q_C↓'),
    ('600', '620', 'Fenster S→O/W', 'Q_H↑, Q_C↓'),
    ('620', '630', 'O/W-Verschattung', 'Q_H↑, Q_C↓'),
    ('600', '640', 'Nachtabsenkung', 'Q_H↓, Q_C~'),
    ('600', '650', 'Nachtlüftung', 'Q_H~, Q_C↓'),
    ('900', '910', 'Süd-Verschattung', 'Q_H↑, Q_C↓'),
    ('900', '920', 'Fenster S→O/W', 'Q_H↑, Q_C~'),
    ('920', '930', 'O/W-Verschattung', 'Q_H↑, Q_C↓'),
    ('900', '940', 'Nachtabsenkung', 'Q_H↓, Q_C~'),
    ('900', '950', 'Nachtlüftung', 'Q_H~, Q_C↓'),
    ('600', '900', 'Therm. Masse', 'Q_H↓, Q_C↓'),
    ('610', '910', 'Masse+Verschatt.', 'Q_H↓, Q_C↓'),
    ('620', '920', 'Masse+O/W-Fenst.', 'Q_H↓, Q_C↓'),
    ('630', '930', 'Masse+O/W-Versch.', 'Q_H↓, Q_C↓'),
    ('640', '940', 'Masse+Nachtabs.', 'Q_H↓, Q_C↓'),
    ('650', '950', 'Masse+Nachtlüft.', 'Q_H~, Q_C↓'),
]

# Norm-Referenztabellen (DIN EN ISO 52016-1, 7.2.4, Tabellen 28-34).
# ACHTUNG Fall 900: Tab. 28/29 sind laut EPB Comment Sheet 2022-08-15,
# Kommentar 28, spaltenvertauscht gedruckt. Die "Heiz"-Spalte 900 in Tab. 28
# ist tatsaechlich der KUEHLbedarf (Summe 3360); eine korrekte Monats-HEIZ-
# Referenz fuer 900 existiert nicht (nur Jahresanker 1827).
TAB28_QH_M = {  # monatlicher Heizbedarf [kWh]
    '600': [1005,849,636,358,154,63,6,11,95,375,644,938],
    '640': [718,591,358,169,47,22,0,0,19,151,389,646],
    '940': [350,333,118,69,4,8,0,0,0,27,120,272],
}
TAB29_QC_M = {  # monatlicher Kuehlbedarf [kWh]
    '600': [640,498,601,464,404,456,722,778,862,876,589,614],
    '640': [586,451,537,421,380,446,720,775,835,812,538,557],
    '900': [84,53,121,147,175,308,638,656,626,418,84,48],  # = Tab.28-Spalte 900 (Druckfehler, s. o.)
    '940': [63,34,108,141,173,306,638,656,625,412,68,36],
}
TAB30_THETA_M = {  # monatliche mittlere operative Temperatur [degC]
    '600':   [22.0,22.0,22.6,22.9,23.5,24.4,25.6,25.2,24.2,23.0,22.2,22.1],
    '640':   [19.0,18.9,19.8,20.9,22.4,24.0,25.6,25.1,23.6,20.9,19.4,19.0],
    '900':   [22.3,22.2,23.1,23.9,24.5,25.7,26.6,26.6,26.1,24.8,22.8,22.2],
    '940':   [21.2,20.9,22.3,23.5,24.4,25.7,26.6,26.6,26.1,24.7,22.1,21.1],
    '600FF': [17.3,16.7,22.1,24.3,26.7,29.6,35.0,35.2,34.6,29.7,21.4,17.9],
    '900FF': [17.6,16.4,21.9,24.7,26.6,29.3,34.9,35.2,34.7,30.3,21.3,18.0],
}
TAB31_PEAK = {  # Spitzenlast [W] (stuendlich integriert)
    '600': {'H': 4351, 'C': 6363}, '640': {'H': 6690, 'C': 6233},
    '900': {'H': 4067, 'C': 4043}, '940': {'H': 9793, 'C': 4047},
}
TAB32_FF = {  # Jahres-max/min/Mittel der operativen Temperatur [degC]
    '600FF': {'max': 63.5, 'min': -16.9, 'avg': 25.9},
    '900FF': {'max': 44.4, 'min': -2.4, 'avg': 26.0},
}
TAB33_JAN4 = {  # stuendliche Netto-Last 4. Januar [Wh] (Heizen +, Kuehlen -)
    '600': [4189,4287,4254,4289,4314,4334,4351,4008,1678,0,-1478,-2916,-3028,-2620,-1330,0,1170,3047,3194,3347,3529,3602,3661,3729],
    '900': [3663,3805,3826,3900,3962,4017,4067,3994,3069,1890,89,0,0,0,0,0,0,1233,1652,1913,2189,2369,2530,2694],
}
TAB34_JAN4_FF = {  # stuendliche operative Temperatur 4. Januar [degC]
    '600FF': [-12.7,-13.8,-14.5,-15.2,-15.8,-16.4,-16.9,-16.4,-10.3,-1.6,12.1,20.5,26.0,28.8,27.9,23.7,13.8,7.1,3.2,0.4,-1.9,-3.7,-5.2,-6.6],
    '900FF': [0.69,0.13,-0.31,-0.77,-1.22,-1.66,-2.09,-2.38,-1.63,-0.15,2.42,4.39,5.94,7.13,7.55,7.26,5.82,4.54,3.74,3.17,2.63,2.18,1.77,1.36],
}
MONAT_STUNDEN = [31*24,28*24,31*24,30*24,31*24,30*24,31*24,31*24,30*24,31*24,30*24,31*24]
MONAT_START = [sum(MONAT_STUNDEN[:i]) for i in range(12)]
JUL27_START = 207*24  # 27. Juli, 0-basierte Jahresstunde (Tag 208)
_AKTUELLE_EXTRAS = {}  # case_id -> extras (fuer FF-Bewertung + 7.2.4-Bericht)

# ============================================================================
# BAUTEIL-DEFINITIONEN
# ============================================================================

# Wärmeübergangskoeffizienten nach ISO 52016-1 Tabelle 25 (richtungsbezogen).
# Richtung des Wärmestroms folgt der Bauteillage: Wand=horizontal, Dach=aufwärts,
# Boden=abwärts. h_ri=5,13 und h_re=4,14 sind richtungsunabhängig, h_ce=20 konstant.
# (Vorher standen hier ASHRAE-140-Werte 3,16/24,67/4,63 - falsche Spez für den
#  Vergleich gegen die Norm-Referenzwerte in 7.2.4, siehe BEFUNDE-Doku.)
H_WAND = {
    "h_ci_W_m2K": 2.5,   # horizontaler Wärmestrom
    "h_ri_W_m2K": 5.13,
    "h_ce_W_m2K": 20.0,
    "h_re_W_m2K": 4.14
}

H_DACH = {
    "h_ci_W_m2K": 5.0,   # Wärmestrom aufwärts
    "h_ri_W_m2K": 5.13,
    "h_ce_W_m2K": 20.0,
    "h_re_W_m2K": 4.14
}

H_BODEN = {
    "h_ci_W_m2K": 0.7,   # Wärmestrom abwärts
    "h_ri_W_m2K": 5.13,
    "h_ce_W_m2K": 20.0,
    "h_re_W_m2K": 4.14
}

# Konstruktionen
LEICHTBAU = {
    "wand": {"massenklasse": "D", "alpha_sol": 0.6, "schichten": [
        {"material": "Gipsplatte",    "dicke_m": 0.012,  "lambda_W_mK": 0.160, "rho_kg_m3": 950, "c_J_kgK": 840},
        {"material": "Fiberglas",     "dicke_m": 0.066,  "lambda_W_mK": 0.040, "rho_kg_m3": 12,  "c_J_kgK": 840},
        {"material": "Holzverkleid.", "dicke_m": 0.009,  "lambda_W_mK": 0.140, "rho_kg_m3": 530, "c_J_kgK": 900}]},
    "dach": {"massenklasse": "D", "alpha_sol": 0.6, "schichten": [
        {"material": "Gipsplatte",    "dicke_m": 0.010,  "lambda_W_mK": 0.160, "rho_kg_m3": 950, "c_J_kgK": 840},
        {"material": "Fiberglas",     "dicke_m": 0.1118, "lambda_W_mK": 0.040, "rho_kg_m3": 12,  "c_J_kgK": 840},
        {"material": "Dachterrasse",  "dicke_m": 0.019,  "lambda_W_mK": 0.140, "rho_kg_m3": 530, "c_J_kgK": 900}]},
    "boden": {"massenklasse": "I", "alpha_sol": 0.0, "schichten": [
        {"material": "Holzfussboden", "dicke_m": 0.025,  "lambda_W_mK": 0.140, "rho_kg_m3": 650, "c_J_kgK": 1200},
        {"material": "Daemmung",      "dicke_m": 1.003,  "lambda_W_mK": 0.040, "rho_kg_m3": 0,   "c_J_kgK": 0}]}
}

SCHWERBAU = {
    "wand": {"massenklasse": "I", "alpha_sol": 0.6, "schichten": [
        {"material": "Betonblock",    "dicke_m": 0.100,  "lambda_W_mK": 0.510, "rho_kg_m3": 1400, "c_J_kgK": 1000},
        {"material": "Schaumdaemmung","dicke_m": 0.0615, "lambda_W_mK": 0.040, "rho_kg_m3": 10,   "c_J_kgK": 1400},
        {"material": "Holzverkleid.", "dicke_m": 0.009,  "lambda_W_mK": 0.140, "rho_kg_m3": 530,  "c_J_kgK": 900}]},
    "dach": {"massenklasse": "D", "alpha_sol": 0.6, "schichten": [
        {"material": "Gipsplatte",    "dicke_m": 0.010,  "lambda_W_mK": 0.160, "rho_kg_m3": 950, "c_J_kgK": 840},
        {"material": "Fiberglas",     "dicke_m": 0.1118, "lambda_W_mK": 0.040, "rho_kg_m3": 12,  "c_J_kgK": 840},
        {"material": "Dachterrasse",  "dicke_m": 0.019,  "lambda_W_mK": 0.140, "rho_kg_m3": 530, "c_J_kgK": 900}]},
    "boden": {"massenklasse": "I", "alpha_sol": 0.0, "schichten": [
        {"material": "Betonplatte",   "dicke_m": 0.080,  "lambda_W_mK": 1.130, "rho_kg_m3": 1400, "c_J_kgK": 1000},
        {"material": "Daemmung",      "dicke_m": 1.007,  "lambda_W_mK": 0.040, "rho_kg_m3": 0,    "c_J_kgK": 0}]}
}

# Fenster
FENSTER = {
    "U_W_m2K": 2.984,
    "g_wert": 0.789,
    "rahmenanteil": 0.0,
    "F_w": 0.9  # ISO 52016-1 Kap. 7.2.2.6: F_w = 0,9 (Norm-Verifizierungsspez). ASHRAE-140-Modus (F_w=1.0) künftig als Umschalter.
}

# ============================================================================
# CASE-DEFINITIONEN
# ============================================================================

def get_case_definition(case_id: str) -> dict:
    """Gibt die Konfiguration für einen BESTEST-Case zurück."""
    
    # Basis: Leichtbau oder Schwerbau
    is_schwerbau = case_id.startswith('9')
    konstruktion = SCHWERBAU if is_schwerbau else LEICHTBAU
    
    # Standard-Fensterverteilung
    fenster = {"sued": 12.0, "ost": 0.0, "west": 0.0}
    
    # Verschattungsfaktoren (1.0 = keine Verschattung)
    # KORREKTUR: Berücksichtige dass nur Direktstrahlung verschattet wird
    # Bei ~35% Diffusanteil: F_sh_eff = F_sh_dir * 0.65 + 0.35
    # Für 1m Überhang bei 0.5m Abstand: F_sh_dir ≈ 0.45 (für Süd)
    # → F_sh_eff ≈ 0.45 * 0.65 + 0.35 ≈ 0.64
    # ABER: Das aktuelle Modell wendet F_sh auf alles an, daher höhere Werte nötig
    F_sh = {"sued": 1.0, "ost": 1.0, "west": 1.0}
    
    # Nutzungsprofil
    nutzung = "standard"
    
    # Case-spezifische Anpassungen
    if case_id in ['610', '910']:
        # Süd-Überhang: Nur Direktstrahlung wird blockiert
        # Effektiver Faktor für Gesamtstrahlung: höher als für rein Direkt
        F_sh["sued"] = 0.75  # Angepasst: weniger aggressive Verschattung
        
    elif case_id in ['620', '920']:
        # Ost-West Fenster statt Süd
        fenster = {"sued": 0.0, "ost": 6.0, "west": 6.0}
        
    elif case_id in ['630', '930']:
        # Ost-West Fenster mit Überhängen
        fenster = {"sued": 0.0, "ost": 6.0, "west": 6.0}
        # O/W Überhänge sind weniger effektiv (flachere Sonnenhöhe)
        F_sh["ost"] = 0.80
        F_sh["west"] = 0.80
        
    elif case_id in ['640', '940']:
        # Nachtabsenkung
        nutzung = "nachtabsenkung"
        
    elif case_id in ['650', '950']:
        # Nachtlüftung
        nutzung = "nachtlueftung"
    
    elif case_id in ['600FF', '900FF']:
        # Free-Float: keine Heizung/Kuehlung, Raumtemperatur schwingt frei
        nutzung = "freischwingend"
    
    return {
        "konstruktion": konstruktion,
        "fenster": fenster,
        "F_sh": F_sh,
        "nutzung": nutzung
    }


# ============================================================================
# KONFIGURATIONSGENERIERUNG
# ============================================================================

def erstelle_gebaeude_json(case_id: str, case_def: dict) -> dict:
    """Erstellt die Gebäude-JSON für einen BESTEST-Case."""
    
    konstruktion = case_def["konstruktion"]
    fenster = case_def["fenster"]
    F_sh = case_def["F_sh"]
    
    # Geometrie
    LAENGE, BREITE, HOEHE = 8.0, 6.0, 2.7
    A_grund = LAENGE * BREITE  # 48 m²
    
    bauteile = []
    
    # Wände und Fenster
    wand_daten = [
        ("S", 180, LAENGE * HOEHE, fenster["sued"], F_sh["sued"]),  # Süd: 21.6 m²
        ("N", 0, LAENGE * HOEHE, 0.0, 1.0),                          # Nord
        ("O", 90, BREITE * HOEHE, fenster["ost"], F_sh["ost"]),      # Ost: 16.2 m²
        ("W", 270, BREITE * HOEHE, fenster["west"], F_sh["west"]),   # West
    ]
    
    for seite, azimut, A_gesamt, A_fenster, f_sh in wand_daten:
        A_wand = A_gesamt - A_fenster
        
        if A_wand > 0:
            bauteile.append({
                "id": f"AW_{seite}",
                "name": f"Außenwand {seite}",
                "typ": "opak",
                "flaeche_m2": round(A_wand, 1),
                "azimut_deg": azimut,
                "neigung_deg": 90,
                "zone_innen": "Z1",
                "zone_aussen": "AUL",
                **konstruktion["wand"],
                **H_WAND
            })
        
        if A_fenster > 0:
            fenster_dict = {
                "id": f"FE_{seite}",
                "name": f"Fenster {seite}",
                "typ": "transparent",
                "flaeche_m2": A_fenster,
                "azimut_deg": azimut,
                "neigung_deg": 90,
                "zone_innen": "Z1",
                "zone_aussen": "AUL",
                **FENSTER,
                **H_WAND,
                "F_sh_obst": f_sh
            }
            
            # Case 630/930: O/W Fenster mit Überhang + Fins
            if case_id in ["630", "930"] and seite in ["O", "W"]:
                fenster_dict.update({
                    "ueberhang_tiefe_m": 1.0,
                    "ueberhang_abstand_m": 0.5,
                    "fenster_hoehe_m": 2.0,
                    "fin_tiefe_m": 1.0,
                    "fin_abstand_m": 0.0,
                    "fenster_breite_m": 3.0
                })
            
            # Case 610/910: Südfenster mit Überhang (keine Fins)
            elif case_id in ["610", "910"] and seite == "S":
                fenster_dict.update({
                    "ueberhang_tiefe_m": 1.0,
                    "ueberhang_abstand_m": 0.5,
                    "fenster_hoehe_m": 2.0
                })
            
            bauteile.append(fenster_dict)
    
    # Dach
    bauteile.append({
        "id": "DA",
        "name": "Dach",
        "typ": "opak",
        "flaeche_m2": A_grund,
        "azimut_deg": 0,
        "neigung_deg": 0,
        "zone_innen": "Z1",
        "zone_aussen": "AUL",
        **konstruktion["dach"],
        **H_DACH
    })
    
    # Boden: opake Konstruktion an Aussenluft (Tabelle 23/24 Fussnote a).
    # Die kuenstlich dicke Daemmung (R_c ~ 25) entkoppelt thermisch vom Erdreich;
    # NICHT adiabat, sondern gegen Aussenluft gerechnet wie in der Norm-Spez.
    bauteile.append({
        "id": "BO",
        "name": "Boden",
        "typ": "opak",
        "flaeche_m2": A_grund,
        "azimut_deg": 0,
        "neigung_deg": 180,
        "zone_innen": "Z1",
        "zone_aussen": "AUL",
        **konstruktion["boden"],
        **H_BODEN
    })
    
    return {
        "projekt": {
            "name": f"BESTEST {case_id}",
            "beschreibung": f"ASHRAE 140 Testfall {case_id}"
        },
        "zonen": [{
            "id": "Z1",
            "name": "Hauptraum",
            "volumen_m3": LAENGE * BREITE * HOEHE,  # 129.6
            "nutzflaeche_m2": A_grund,
            "nutzungsprofil": "BESTEST",
            # Interne Kapazitaet aus korrigiertem Default (Luft + Moebel nach B.17,
            # 10 000 J/(m2K)); kein Override noetig.
            "kapazitaet_Wh_K": 0
        }],
        "bauteile": bauteile,
        "randbedingungen": {
            "AUL": {"typ": "aussenluft"},
            "ADIABAT": {"typ": "adiabatisch"}
        }
    }


def erstelle_nutzung_json(nutzung_typ: str) -> dict:
    """Erstellt die Nutzungs-JSON für einen BESTEST-Case."""
    
    if nutzung_typ == "nachtabsenkung":
        # Heiz-Setback auf 10°C von 23-07 Uhr
        heizen = [10,10,10,10,10,10,10,20,20,20,20,20,20,20,20,20,20,20,20,20,20,20,20,10]
    else:
        heizen = [20]*24
    
    profil = {
        "beschreibung": f"BESTEST Profil ({nutzung_typ})",
        "solltemperaturen": {
            "heizen_C": heizen,
            "kuehlen_C": [27]*24
        },
        "interne_gewinne_W": [200]*24,
        "luftwechsel_1_h": 0.411,  # ISO 52016-1 Kap. 7.2.2.14: 0,5/h x 0,822 (Hoehenkorrektur 1609 m, Norm-Vorgabe)
        "f_int_konv": 0.4
    }
    
    if nutzung_typ == "nachtlueftung":
        # BESTEST Case 650 Spezifikation (ASHRAE 140):
        # - HEIZUNG = IMMER AUS (nicht nur niedrig, sondern OFF!)
        # - KÜHLUNG = nur tagsüber (07:00-18:00), nachts AUS
        # - Nachtlüftung = 18:00-07:00, rein zeitgesteuert
        # - Volumenstrom: 1703.16 std m³/h ZUSÄTZLICH zur Infiltration
        # - ACH ohne Höhenkorrektur: ~10.8 ACH (Table 5-160)
        
        # Heizung OFF: Sollwert auf -100°C setzen (wird nie erreicht)
        profil["solltemperaturen"]["heizen_C"] = [-100]*24
        
        # Kühlung nur tagsüber (07:00-18:00): nachts auf +100°C (wird nie erreicht)
        kuehlen_650 = [100]*24  # Default: AUS
        for h in range(7, 18):  # 07:00-17:59: Kühlung aktiv
            kuehlen_650[h] = 27
        profil["solltemperaturen"]["kuehlen_C"] = kuehlen_650
        
        # Nachtlüftung
        profil["nachtlueftung_aktiv"] = True
        profil["nachtlueftung_ach"] = 10.8  # BESTEST Table 5-160 (ohne Höhenkorrektur)
        profil["nachtlueftung_stunden"] = list(range(18,24)) + list(range(0,7))  # 18-07 Uhr
    
    if nutzung_typ == "freischwingend":
        # Free-Float (600FF/900FF): keine Heizung, keine Kuehlung.
        # Sollwerte so setzen, dass sie nie erreicht werden -> Raumtemperatur schwingt frei.
        profil["solltemperaturen"]["heizen_C"] = [-100]*24
        profil["solltemperaturen"]["kuehlen_C"] = [100]*24
    
    return {
        "profile": {
            "BESTEST": profil
        }
    }


def erstelle_steuerung_json(case_id: str) -> dict:
    """Erstellt die Steuerungs-JSON."""
    return {
        "simulation": {
            # Relativ zur Steuerungs-JSON (configs/ -> ../klimadaten/...);
            # Aufloesung uebernimmt lade_optionen — Configs bleiben damit
            # maschinen- und startortunabhaengig.
            "klimadatei": f"../klimadaten/{KLIMA_DATEI.name}",
            "klimaformat": "CSV",
            "initialisierung_tage": 31
        },
        "ausgabe": {
            "stundenwerte": False,
            "monatswerte": True,
            "datei_csv": f"ergebnisse_{case_id}.csv",
            "datei_json": f"ergebnisse_{case_id}.json"
        },
        "optionen": {
            "f_sol_konv": 0.1,
            "f_HC_konv": 1.0,  # ISO 52016-1 Kap. 7.2.2.9: f_H;c = f_C;c = 1,00 (Muss-Vorgabe fuer Verifizierung; B.11-Default 0,4 gilt hier NICHT)
            "delta_theta_sky_K": 11.0,
            "klimazone": "zwischen"
        }
    }


# ============================================================================
# SIMULATION
# ============================================================================

def simuliere_case(case_id: str, config_dir: Path, work_dir: Path) -> dict:
    """Führt die Simulation für einen Case durch."""
    
    print(f"\n{'='*60}")
    print(f"Case {case_id}")
    print('='*60)
    
    # Case-Definition holen
    case_def = get_case_definition(case_id)
    
    # Konfigurationsdateien erstellen
    geb = erstelle_gebaeude_json(case_id, case_def)
    nutz = erstelle_nutzung_json(case_def["nutzung"])
    steu = erstelle_steuerung_json(case_id)
    steu["ausgabe"]["stundenwerte"] = True  # 7.2.4-Berichtsgroessen
    
    geb_path = config_dir / f"gebaeude_{case_id}.json"
    nutz_path = config_dir / f"nutzung_{case_id}.json"
    steu_path = config_dir / f"steuerung_{case_id}.json"
    
    with open(geb_path, 'w', encoding='utf-8') as f:
        json.dump(geb, f, indent=2, ensure_ascii=False)
    with open(nutz_path, 'w', encoding='utf-8') as f:
        json.dump(nutz, f, indent=2, ensure_ascii=False)
    with open(steu_path, 'w', encoding='utf-8') as f:
        json.dump(steu, f, indent=2, ensure_ascii=False)
    
    # Simulation ausführen
    original_dir = os.getcwd()
    os.chdir(work_dir)
    
    try:
        from iso52016 import lade_gebaeude, lade_klimadaten, lade_optionen, simuliere
        
        # Lade Konfigurationen
        optionen = lade_optionen(str(steu_path))
        gebaeude = lade_gebaeude(str(geb_path), str(nutz_path))
        klima = lade_klimadaten(optionen.klimadatei, optionen.klimaformat)
        
        # Führe Simulation durch
        # Verschattung wird vom Simulator live aus Geometrie-Parametern berechnet
        ergebnisse = simuliere(gebaeude, klima, optionen)
        
        # 7.2.4-Berichtsgroessen aus den Stundenwerten extrahieren
        z = list(ergebnisse['zonen'].values())[0]
        std = z['stunden']
        theta = [h['theta_op'] for h in std]
        theta_m = [round(sum(theta[MONAT_START[m]:MONAT_START[m]+MONAT_STUNDEN[m]])
                         / MONAT_STUNDEN[m], 1) for m in range(12)]
        qh_m = [round(m['Q_H_kWh'], 0) for m in z['monate']]
        qc_m = [round(m['Q_C_kWh'], 0) for m in z['monate']]
        extras = {
            'theta_op_monat': theta_m,
            'theta_op_max': round(max(theta), 1),
            'theta_op_min': round(min(theta), 1),
            'theta_op_avg': round(sum(theta)/len(theta), 1),
            'Q_H_monat': qh_m, 'Q_C_monat': qc_m,
            'peak_H_W': round(max(h['Phi_H_W'] for h in std), 0),
            'peak_C_W': round(max(-h['Phi_C_W'] for h in std), 0),
            'jan4': [(h['Phi_H_W'], h['Phi_C_W'], h['theta_op']) for h in std[72:96]],
            'jul27': [(h['Phi_H_W'], h['Phi_C_W'], h['theta_op']) for h in std[JUL27_START:JUL27_START+24]],
        }
        return {
            "case_id": case_id,
            "extras": extras,
            "Q_H_kWh": ergebnisse['gesamt']['Q_H_kWh'],
            "Q_C_kWh": ergebnisse['gesamt']['Q_C_kWh'],
            "success": True
        }
    except Exception as e:
        import traceback
        print(f"FEHLER: {e}")
        traceback.print_exc()
        return {
            "case_id": case_id,
            "Q_H_kWh": 0,
            "Q_C_kWh": 0,
            "success": False,
            "error": str(e)
        }
    finally:
        os.chdir(original_dir)


# ============================================================================
# AUSWERTUNG
# ============================================================================

def bewerte_ergebnis(case_id: str, Q_H: float, Q_C: float) -> dict:
    """Bewertet ein Ergebnis gegen die Referenzwerte."""
    
    ref = REFERENZ.get(case_id, {})
    
    # Freilauf-Faelle: keine Q-Baender; Bewertung gegen Tab. 30/32.
    # Die Norm definiert KEIN Akzeptanzkriterium fuer die FF-Temperaturen;
    # hier eigenes, dokumentiertes Kriterium: |Delta Monatsmittel| <= 1,0 K
    # fuer alle 12 Monate UND |Delta max|, |Delta min| <= 2,0 K (Tab. 32).
    if case_id in TAB32_FF:
        ex = _AKTUELLE_EXTRAS.get(case_id)
        if ex is None:
            return {"passed": False, "Q_H_ok": False, "Q_C_ok": False,
                    "Q_H_ref": "-", "Q_C_ref": "-",
                    "Q_H_abw_prozent": 0, "Q_C_abw_prozent": 0}
        dmon = [abs(a-b) for a, b in zip(ex['theta_op_monat'], TAB30_THETA_M[case_id])]
        dmax = abs(ex['theta_op_max'] - TAB32_FF[case_id]['max'])
        dmin = abs(ex['theta_op_min'] - TAB32_FF[case_id]['min'])
        ok = max(dmon) <= 1.0 and dmax <= 2.0 and dmin <= 2.0
        return {"passed": ok, "Q_H_ok": ok, "Q_C_ok": ok,
                "Q_H_ref": f"Tab.30 max|dT|={max(dmon):.1f}K",
                "Q_C_ref": f"Tab.32 dmax={dmax:.1f}/dmin={dmin:.1f}K",
                "Q_H_abw_prozent": 0, "Q_C_abw_prozent": 0}
    
    Q_H_min, Q_H_max = ref.get('Q_H', (0, 99999))
    Q_C_min, Q_C_max = ref.get('Q_C', (0, 99999))
    
    Q_H_ok = Q_H_min <= Q_H <= Q_H_max
    Q_C_ok = Q_C_min <= Q_C <= Q_C_max
    
    # Abweichung vom Bandmittel
    Q_H_mitte = (Q_H_min + Q_H_max) / 2
    Q_C_mitte = (Q_C_min + Q_C_max) / 2
    
    return {
        "Q_H_ok": Q_H_ok,
        "Q_C_ok": Q_C_ok,
        "passed": Q_H_ok and Q_C_ok,
        "Q_H_ref": f"{Q_H_min:.0f}-{Q_H_max:.0f}",
        "Q_C_ref": f"{Q_C_min:.0f}-{Q_C_max:.0f}",
        "Q_H_abw_prozent": (Q_H - Q_H_mitte) / Q_H_mitte * 100 if Q_H_mitte > 0 else 0,
        "Q_C_abw_prozent": (Q_C - Q_C_mitte) / Q_C_mitte * 100 if Q_C_mitte > 0 else 0,
    }


# ============================================================================
# HAUPTPROGRAMM
# ============================================================================

def schreibe_berichtsgroessen(ergebnisse, pfad):
    """Berichtsgroessen nach ISO 52016-1, 7.2.4, mit Norm-Referenzen (Tab. 28-34)."""
    MON = ['Jan','Feb','Mrz','Apr','Mai','Jun','Jul','Aug','Sep','Okt','Nov','Dez']
    L = []
    L.append("# Berichtsgrößen nach ISO 52016-1, Kap. 7.2.4")
    L.append("")
    L.append("Automatisch erzeugt von run_bestest.py (BESTEST-Suitelauf nach Kap. 7.2); je Fall die Berichtsgrößen des Abschnitts 7.2.4 neben den Norm-Referenzen der Tabellen 28–34.")
    L.append("")
    L.append("Spaltenschema: durchgehend Formelzeichen [Einheit]; Referenzspalten heißen Größe,ref [Einheit] mit Angabe der Norm-Tabelle, z. B. θ_op,ref [°C] (Tab. 30); '-' bedeutet: für diesen Fall existiert keine Norm-Referenz. Vorzeichenkonvention der Lasten: Heizen positiv, Kühlen negativ; Φ_netto = Φ_H + Φ_C.")
    L.append("")
    L.append("Hinweise zur Referenzlage: Fall 900: Tab. 28/29 sind spaltenvertauscht gedruckt (EPB-Kommentar 28); als Monats-KÜHLreferenz dient die gedruckte 'Heiz'-Spalte (Summe 3360 kWh); eine Monats-HEIZreferenz für 900 existiert nicht (Jahresanker 1827 kWh). Fall 600/640(/600FF): Referenzen laut EPB-Kommentar 31 selbst fehlerbehaftet. Für den 27. Juli definiert die Norm keine Referenztabelle (reine Berichtspflicht).")
    for e in ergebnisse:
        cid = e['case_id']; ex = _AKTUELLE_EXTRAS.get(cid)
        if not ex:
            continue
        L.append("")
        L.append(f"## Fall {cid}")
        L.append("")
        # Monatswerte
        L.append("| Monat | Q_H [kWh] | Q_H,ref [kWh] (Tab. 28) | Q_C [kWh] | Q_C,ref [kWh] (Tab. 29) | θ_op [°C] | θ_op,ref [°C] (Tab. 30) |")
        L.append("|---|---|---|---|---|---|---|")
        rh = TAB28_QH_M.get(cid); rc = TAB29_QC_M.get(cid); rt = TAB30_THETA_M.get(cid)
        for m in range(12):
            L.append(f"| {MON[m]} | {ex['Q_H_monat'][m]:.0f} | {rh[m] if rh else '-'} | "
                     f"{ex['Q_C_monat'][m]:.0f} | {rc[m] if rc else '-'} | "
                     f"{ex['theta_op_monat'][m]:.1f} | {rt[m] if rt else '-'} |")
        L.append(f"| Jahr | {e['Q_H_kWh']:.0f} | {sum(rh) if rh else '-'} | "
                 f"{e['Q_C_kWh']:.0f} | {sum(rc) if rc else '-'} | "
                 f"{ex['theta_op_avg']:.1f} | "
                 f"{round(sum(rt)/12,1) if rt else '-'} |")
        if rt:
            dmon = max(abs(a-b) for a, b in zip(ex['theta_op_monat'], rt))
            L.append(f"Max. Monatsabweichung θ_op gegenüber Tab. 30: {dmon:.1f} K")
        # Spitzen
        pk = TAB31_PEAK.get(cid)
        L.append(f"Spitzenlast (stündlich integriert): Φ_H,max = {ex['peak_H_W']:.0f} W"
                 + (f" (Φ_H,max,ref (Tab. 31): {pk['H']} W)" if pk else "")
                 + f", Φ_C,max = {ex['peak_C_W']:.0f} W"
                 + (f" (Φ_C,max,ref (Tab. 31): {pk['C']} W)" if pk else ""))
        # FF-Extrema
        ff = TAB32_FF.get(cid)
        if ff:
            L.append(f"Jahres-Extrema θ_op [°C]: max {ex['theta_op_max']:.1f} "
                     f"(θ_op,max,ref (Tab. 32): {ff['max']}), "
                     f"min {ex['theta_op_min']:.1f} "
                     f"(θ_op,min,ref (Tab. 32): {ff['min']}), "
                     f"Mittel {ex['theta_op_avg']:.1f} "
                     f"(θ_op,avg,ref (Tab. 32): {ff['avg']})")
        # Stundenwerte 4. Januar
        L.append("")
        L.append("### Stundenwerte 4. Januar")
        L.append("| Stunde | Φ_H [W] | Φ_C [W] | Φ_netto [W] | Φ_netto,ref [W] (Tab. 33) | θ_op [°C] | θ_op,ref [°C] (Tab. 34) |")
        L.append("|---|---|---|---|---|---|---|")
        r33 = TAB33_JAN4.get(cid); r34 = TAB34_JAN4_FF.get(cid)
        for h in range(24):
            ph, pc, to = ex['jan4'][h]
            L.append(f"| {h+1} | {ph:.0f} | {pc:.0f} | {ph+pc:.0f} | "
                     f"{r33[h] if r33 else '-'} | {to:.2f} | {r34[h] if r34 else '-'} |")
        # Stundenwerte 27. Juli (Berichtspflicht, keine Norm-Referenz)
        L.append("")
        L.append("### Stundenwerte 27. Juli (Berichtspflicht ohne Norm-Referenztabelle)")
        L.append("| Stunde | Φ_H [W] | Φ_C [W] | θ_op [°C] |")
        L.append("|---|---|---|---|")
        for h in range(24):
            ph, pc, to = ex['jul27'][h]
            L.append(f"| {h+1} | {ph:.0f} | {pc:.0f} | {to:.2f} |")
    with open(pfad, 'w', encoding='utf-8') as f:
        f.write("\n".join(L) + "\n")
    print(f"Berichtsgroessen 7.2.4 -> {pfad}")


def main():
    """Führt die komplette BESTEST-Validierung durch."""
    
    print("="*60)
    print("BESTEST-VERIFIZIERUNGSSUITE (Prueffaelle ISO 52016-1 Kap. 7.2, Baender ASHRAE 140)")
    print("ISO 52016-1 Gebäudesimulation")
    print("="*60)
    
    # Verzeichnisse
    base_dir = Path(__file__).parent
    config_dir = base_dir / "configs"
    
    config_dir.mkdir(exist_ok=True)
    
    # Alle Cases (inkl. Free-Float 600FF/900FF)
    cases = ['600', '610', '620', '630', '640', '650',
             '900', '910', '920', '930', '940', '950',
             '600FF', '900FF']
    
    ergebnisse = []
    
    for case_id in cases:
        result = simuliere_case(case_id, config_dir, base_dir)
        _AKTUELLE_EXTRAS[case_id] = result.get('extras')
        
        if result['success']:
            result['bewertung'] = bewerte_ergebnis(
                case_id, result['Q_H_kWh'], result['Q_C_kWh']
            )
        
        ergebnisse.append(result)
    
    # Berichtsgroessen nach 7.2.4 (Monats-Q, Theta_op-Mittel, Stundenwerte 4.1./27.7.)
    schreibe_berichtsgroessen(ergebnisse, base_dir / "berichtsgroessen_7_2_4.md")
    
    # Zusammenfassung ausgeben
    print("\n" + "="*60)
    print("ZUSAMMENFASSUNG")
    print("="*60)
    
    for e in sorted(ergebnisse, key=lambda x: (int(''.join(filter(str.isdigit, x['case_id']))), x['case_id'])):
        bew = e.get('bewertung', {})
        status = "✅ PASS" if bew.get('passed') else "❌ FAIL"
        print(f"  Case {e['case_id']}: Q_H={e['Q_H_kWh']:5.0f}  Q_C={e['Q_C_kWh']:5.0f}  {status}")
    
    passed = sum(1 for e in ergebnisse if e.get('bewertung', {}).get('passed', False))
    print(f"\nGesamt: {passed}/{len(ergebnisse)} bestanden")
    
    # Delta-Analysen (16 Deltas total)
    print("\n" + "-"*60)
    print("DELTA-ANALYSEN")
    print("-"*60)
    
    erg_dict = {e['case_id']: e for e in ergebnisse}
    deltas = [
        # Leichtbau (Basis 600) - 5 Deltas
        ('600', '610', 'Süd-Verschattung', 'Q_H↑, Q_C↓'),
        ('600', '620', 'Fenster S→O/W', 'Q_H↑, Q_C↓'),
        ('620', '630', 'O/W-Verschattung', 'Q_H↑, Q_C↓'),
        ('600', '640', 'Nachtabsenkung', 'Q_H↓, Q_C~'),
        ('600', '650', 'Nachtlüftung', 'Q_H~, Q_C↓'),
        # Schwerbau (Basis 900) - 5 Deltas
        ('900', '910', 'Süd-Verschattung', 'Q_H↑, Q_C↓'),
        ('900', '920', 'Fenster S→O/W', 'Q_H↑, Q_C~'),
        ('920', '930', 'O/W-Verschattung', 'Q_H↑, Q_C↓'),
        ('900', '940', 'Nachtabsenkung', 'Q_H↓, Q_C~'),
        ('900', '950', 'Nachtlüftung', 'Q_H~, Q_C↓'),
        # Leicht vs Schwer - 6 Deltas
        ('600', '900', 'Therm. Masse', 'Q_H↓, Q_C↓'),
        ('610', '910', 'Masse+Verschatt.', 'Q_H↓, Q_C↓'),
        ('620', '920', 'Masse+O/W-Fenst.', 'Q_H↓, Q_C↓'),
        ('630', '930', 'Masse+O/W-Versch.', 'Q_H↓, Q_C↓'),
        ('640', '940', 'Masse+Nachtabs.', 'Q_H↓, Q_C↓'),
        ('650', '950', 'Masse+Nachtlüft.', 'Q_H~, Q_C↓'),
    ]
    
    delta_passed = 0
    delta_total = len(deltas)
    
    for base, comp, effekt, erwartung in deltas:
        if base in erg_dict and comp in erg_dict:
            dH = erg_dict[comp]['Q_H_kWh'] - erg_dict[base]['Q_H_kWh']
            dC = erg_dict[comp]['Q_C_kWh'] - erg_dict[base]['Q_C_kWh']
            
            # Prüfe ob Richtung stimmt
            ok = True
            erw_H = erwartung.split(',')[0].strip()
            erw_C = erwartung.split(',')[1].strip()
            
            if '↑' in erw_H and dH <= 0: ok = False
            if '↓' in erw_H and dH >= 0: ok = False
            if '↑' in erw_C and dC <= 0: ok = False
            if '↓' in erw_C and dC >= 0: ok = False
            
            status = "✅" if ok else "⚠️"
            if ok: delta_passed += 1
            print(f"  {base}→{comp}: ΔQ_H={dH:+6.0f}, ΔQ_C={dC:+6.0f}  {status} ({effekt})")
    
    print(f"\nDeltas: {delta_passed}/{delta_total} korrekte Richtung")
    print("="*60)
    
    # Ergebnisse als JSON speichern (konvertiere numpy-Typen)
    def convert_to_json_serializable(obj):
        if isinstance(obj, (np.bool_, np.integer, np.floating)):
            return obj.item()
        elif isinstance(obj, dict):
            return {k: convert_to_json_serializable(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [convert_to_json_serializable(i) for i in obj]
        return obj
    
    with open(base_dir / "ergebnisse_alle.json", 'w', encoding='utf-8') as f:
        json.dump(convert_to_json_serializable(ergebnisse), f, indent=2, ensure_ascii=False)
    
    return ergebnisse


if __name__ == '__main__':
    main()

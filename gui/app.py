# Copyright (c) 2026 Mario Vukadinovic
# SPDX-License-Identifier: AGPL-3.0-only
# Part of the ISO 52016-1 Room Simulator. See LICENSE.
# Commercial licensing available on request.

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RoomCurve – Raumsimulator nach DIN EN ISO 52016-1 (Streamlit GUI)
================================================
"""

import streamlit as st
import numpy as np
import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Optional
import plotly.graph_objects as go

# Pfad zum Simulator hinzufügen
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

# =============================================================================
# STREAMLIT PAGE CONFIG (muss ganz oben stehen!)
# =============================================================================
st.set_page_config(
    page_title="RoomCurve",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="expanded"
)

# =============================================================================
# BETA DISCLAIMER & FEEDBACK
# =============================================================================
CONTACT_URL = "https://www.linkedin.com/in/mario-vukadinovic/"
# AGPL §13: Nutzer der GEHOSTETEN GUI müssen den Quellcode angeboten
# bekommen. VOR öffentlichem Hosting hier die URL des öffentlichen
# Repositories eintragen; bis dahin verweist der Footer auf die
# beiliegende LICENSE.
QUELLCODE_URL = "https://github.com/m4rio-eng/roomcurve"

st.warning("""
⚠️ **BETA-VERSION – Haftungsausschluss**

Dieses Tool befindet sich in der Entwicklung und dient ausschließlich zu **Test- und Informationszwecken**.
Die Ergebnisse sind **nicht** für Planungen, Nachweise oder behördliche Verfahren geeignet.
Das Tool ist **kein Ersatz für einen normativen Nachweis nach DIN 4108-2**.

**Keine Gewährleistung** für Richtigkeit, Vollständigkeit oder Aktualität der Berechnungen.
Die Nutzung erfolgt auf **eigene Verantwortung**.
""")

# Kontakt-URL für Footer
contact_url = CONTACT_URL

from iso52016 import (
    ClimateData, load_climate, create_constant_climate,
    Gebaeude, Zone, Bauteil, Nutzungsprofil, Randbedingung,
    SimulationsOptionen, simuliere
)

# =============================================================================
# KONSTANTEN & PRESETS
# =============================================================================

U_WERT_PRESETS = {
    "Bestand (vor 1995)": {
        "wand": 1.4, "dach": 0.8, "boden": 1.0, 
        "fenster": 2.8, "g_wert": 0.75
    },
    "GEG 2024": {
        "wand": 0.28, "dach": 0.20, "boden": 0.35, 
        "fenster": 1.3, "g_wert": 0.60
    },
    "KfW 55": {
        "wand": 0.20, "dach": 0.14, "boden": 0.25, 
        "fenster": 1.0, "g_wert": 0.55
    },
    "Passivhaus": {
        "wand": 0.15, "dach": 0.10, "boden": 0.15, 
        "fenster": 0.80, "g_wert": 0.50
    },
}

RANDBEDINGUNGEN = {
    "Außenluft": "AUL",
    "Adiabatisch": "ADIABAT",
    "Erdreich": "ERD",
    # "Nachbar": "NACHBAR",  # TODO Mehrzonen: reaktivieren, sobald die GUI
    #                         # Nachbarraum-Temperaturen abbildet (Rechenkern
    #                         # unterstützt es bereits). Bis dahin deckt
    #                         # "Adiabatisch" den gleich temperierten Nachbarraum ab.
}

# Massenklassen nach ISO 52016-1
MASSENKLASSEN = {
    "Außendämmung (I)": "I",
    "Innendämmung (E)": "E",
    "Kerndämmung (IE)": "IE",
    "Sandwich (M)": "M",
    "Ungedämmt (D)": "D",
}

# Bauschwere nach ISO 52016-1, Tabelle B.14 [kJ/(m²K)]
BAUSCHWERE_ISO = {
    "Sehr leicht (50)": 50.0,
    "Leicht (75)": 75.0,
    "Mittel (110)": 110.0,
    "Schwer (175)": 175.0,
    "Sehr schwer (250)": 250.0,
}

TRY_REGIONEN = {
    "Region A - Rostock (TRY 02)": "02",
    "Region B - Potsdam (TRY 04)": "04",
    "Region C - Mannheim (TRY 12)": "12",
}

TRY_JAHRE = {
    "2010 (Referenz)": "2010",
    "2015 (Referenz)": "2015",
    "2035 (Projektion)": "2035",
    "2045 (Projektion)": "2045",
}

# F_C-Anhaltswerte nach DIN 4108-2:2026-05, Abschnitt 8.6.
# Verwendet werden ausschließlich die "allgemein"-Zeilen der Tabellen 10 bis 13
# (Werte für den Fall, dass keine näheren Kenntnisse über Transmissions-/
# Reflexionseigenschaften der Sonnenschutzvorrichtung vorliegen).
# Struktur: Typ -> g-Klasse ("g_low" = g <= 0,40 / "g_high" = g > 0,40)
#               -> Verglasung -> F_C.
# None = Norm sieht keinen Anhaltswert vor (detaillierte Ermittlung
# erforderlich, vgl. Fußnote a der Tabellen 11/12) -> manuelle Eingabe.
SONNENSCHUTZ_TYPEN = {
    "Ohne": {
        "g_low": {"zweifach": 1.0, "dreifach": 1.0},
        "g_high": {"zweifach": 1.0, "dreifach": 1.0},
    },
    "Außen – Rollladen/Jalousie/Raffstore/Markise (parallel zum Glas)": {
        "g_low": {"zweifach": 0.32, "dreifach": 0.29},
        "g_high": {"zweifach": 0.25, "dreifach": 0.24},
    },
    "Außen – Vordach/Markise nicht parallel/freistehende Lamellen": {
        "g_low": {"zweifach": 0.55, "dreifach": 0.55},
        "g_high": {"zweifach": 0.50, "dreifach": 0.50},
    },
    "Scheibenzwischenraum Isolierglas – Jalousie/drehbare Lamellen": {
        "g_low": None,
        "g_high": {"zweifach": 0.35, "dreifach": 0.31},
    },
    "Scheibenzwischenraum Isolierglas – Folienrollo": {
        "g_low": None,
        "g_high": {"zweifach": 0.27, "dreifach": 0.25},
    },
    "Mehrschalige Konstruktion (Verbund-/Kastenfenster)": {
        # Verglasung bezieht sich auf die innere Scheibe
        # (einfach außen + zweifach/dreifach innen).
        "g_low": None,
        "g_high": {"zweifach": 0.36, "dreifach": 0.31},
    },
    "Innen – Rollo/Plissee/Jalousie/drehbare Lamellen": {
        "g_low": {"zweifach": 0.95, "dreifach": 0.95},
        "g_high": {"zweifach": 0.90, "dreifach": 0.95},
    },
    "Manuell": "MANUELL",  # Sonderwert für manuelle Eingabe
}


def fc_anhaltswert(typ: str, g_wert: float, verglasung: str):
    """F_C-Anhaltswert nach DIN 4108-2:2026-05, 8.6 ("allgemein"-Zeilen).

    Returns None, wenn manuell einzugeben ist (Typ "Manuell" oder Kombination
    ohne Anhaltswert in der Norm).
    """
    eintrag = SONNENSCHUTZ_TYPEN[typ]
    if eintrag == "MANUELL":
        return None
    klasse = "g_low" if g_wert <= 0.40 else "g_high"
    werte = eintrag[klasse]
    if werte is None:
        return None
    return werte[verglasung]

SEITEN = {
    "nord": {"name": "Nord", "azimut": 0, "neigung": 90, "default_fenster": 10},
    "ost": {"name": "Ost", "azimut": 90, "neigung": 90, "default_fenster": 15},
    "sued": {"name": "Süd", "azimut": 180, "neigung": 90, "default_fenster": 30},
    "west": {"name": "West", "azimut": 270, "neigung": 90, "default_fenster": 15},
    "dach": {"name": "Dach", "azimut": 0, "neigung": 0, "default_fenster": 0},
    "boden": {"name": "Boden", "azimut": 0, "neigung": 0, "default_fenster": 0},
}


# =============================================================================
# HILFSFUNKTIONEN
# =============================================================================

def berechne_flaechen(L: float, B: float, H: float) -> Dict[str, float]:
    """Berechnet Flächen für Quader-Gebäude."""
    return {
        "nord": L * H,
        "sued": L * H,
        "ost": B * H,
        "west": B * H,
        "dach": L * B,
        "boden": L * B,
    }


def R_aus_U(U: float) -> float:
    """Berechnet R_c aus U-Wert (ohne Übergangswiderstände)."""
    if U <= 0:
        return 25.0
    R_si, R_se = 0.13, 0.04
    R_total = 1.0 / U
    return max(0.01, R_total - R_si - R_se)


def erstelle_3d_visualisierung(L: float, B: float, H: float, 
                                seiten_config: Dict, flaechen: Dict) -> go.Figure:
    """Erstellt 3D-Visualisierung des Gebäudes mit Plotly."""
    
    fig = go.Figure()
    
    # Farben
    WAND_FARBE = 'rgba(200, 200, 200, 0.7)'      # Hellgrau - Außenwand
    DACH_FARBE = 'rgba(180, 100, 100, 0.7)'      # Rot-braun - Dach
    BODEN_FARBE = 'rgba(150, 150, 100, 0.7)'     # Olive - Boden (Außenluft)
    FENSTER_FARBE = 'rgba(100, 150, 255, 0.9)'   # Blau - Fenster
    ADIABAT_FARBE = 'rgba(180, 130, 200, 0.5)'   # Lila transparent - Adiabatisch
    NACHBAR_FARBE = 'rgba(255, 180, 100, 0.6)'   # Orange - Nachbarzone
    ERDREICH_FARBE = 'rgba(139, 90, 43, 0.7)'    # Braun - Erdreich
    
    # Koordinaten (Gebäude zentriert)
    x0, x1 = -L/2, L/2
    y0, y1 = -B/2, B/2
    z0, z1 = 0, H
    
    walls = {
        'nord': [(x0, y1, z0), (x1, y1, z0), (x1, y1, z1), (x0, y1, z1)],
        'sued': [(x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1)],
        'ost': [(x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1)],
        'west': [(x0, y0, z0), (x0, y1, z0), (x0, y1, z1), (x0, y0, z1)],
        'dach': [(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)],
        'boden': [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0)],
    }
    
    for seite_id, vertices in walls.items():
        config = seiten_config.get(seite_id, {})
        rb = config.get('randbedingung', 'AUL')
        fenster_anteil = config.get('fensteranteil', 0)
        
        # Wandfarbe je nach Randbedingung
        if seite_id == 'dach':
            if rb == 'ADIABAT':
                farbe = ADIABAT_FARBE
            else:
                farbe = DACH_FARBE
        elif seite_id == 'boden':
            if rb == 'ERD':
                farbe = ERDREICH_FARBE
            elif rb == 'ADIABAT':
                farbe = ADIABAT_FARBE
            else:
                farbe = BODEN_FARBE
        elif rb == 'ADIABAT':
            farbe = ADIABAT_FARBE
        elif rb == 'ERD':
            farbe = ERDREICH_FARBE
        elif rb == 'NACHBAR':
            farbe = NACHBAR_FARBE
        else:
            farbe = WAND_FARBE
        
        # Wand zeichnen
        x = [v[0] for v in vertices]
        y = [v[1] for v in vertices]
        z = [v[2] for v in vertices]
        
        fig.add_trace(go.Mesh3d(
            x=x, y=y, z=z,
            i=[0, 0], j=[1, 2], k=[2, 3],
            color=farbe, opacity=0.6,
            name=f"{SEITEN[seite_id]['name']}: {flaechen[seite_id]:.0f}m²",
            hoverinfo='name'
        ))
        
        # Farbige Kanten (sichtbar von beiden Seiten)
        # Geschlossener Linienzug um die Fläche
        kanten_x = x + [x[0]]  # Schließen
        kanten_y = y + [y[0]]
        kanten_z = z + [z[0]]
        
        # Kantenfarbe: gleiche Farbe aber ohne Alpha für bessere Sichtbarkeit
        kanten_farbe = farbe.replace('0.4', '1.0').replace('0.5', '1.0').replace('0.6', '1.0').replace('0.7', '1.0')
        
        fig.add_trace(go.Scatter3d(
            x=kanten_x, y=kanten_y, z=kanten_z,
            mode='lines',
            line=dict(color=kanten_farbe, width=4),
            showlegend=False,
            hoverinfo='skip'
        ))
        
        # Fenster
        if fenster_anteil > 0 and seite_id not in ['dach', 'boden']:
            f_ratio = np.sqrt(fenster_anteil / 100) * 0.7
            
            if seite_id in ['nord', 'sued']:
                fx = f_ratio * L * 0.5
                fz = f_ratio * H * 0.5
                cy = y1 if seite_id == 'nord' else y0
                offset = 0.02 if seite_id == 'nord' else -0.02
                fenster_v = [
                    (-fx, cy+offset, H*0.35), (fx, cy+offset, H*0.35),
                    (fx, cy+offset, H*0.35+fz), (-fx, cy+offset, H*0.35+fz)
                ]
            else:
                fy = f_ratio * B * 0.5
                fz = f_ratio * H * 0.5
                cx = x1 if seite_id == 'ost' else x0
                offset = 0.02 if seite_id == 'ost' else -0.02
                fenster_v = [
                    (cx+offset, -fy, H*0.35), (cx+offset, fy, H*0.35),
                    (cx+offset, fy, H*0.35+fz), (cx+offset, -fy, H*0.35+fz)
                ]
            
            fx = [v[0] for v in fenster_v]
            fy = [v[1] for v in fenster_v]
            fz = [v[2] for v in fenster_v]
            
            A_fenster = flaechen[seite_id] * fenster_anteil / 100
            fig.add_trace(go.Mesh3d(
                x=fx, y=fy, z=fz,
                i=[0, 0], j=[1, 2], k=[2, 3],
                color=FENSTER_FARBE, opacity=0.9,
                name=f"Fenster {SEITEN[seite_id]['name']}: {A_fenster:.1f}m²",
                hoverinfo='name'
            ))
    
    # Nord-Pfeil
    arrow_len = max(L, B) * 0.4
    fig.add_trace(go.Scatter3d(
        x=[0, 0], y=[B/2 + 0.3, B/2 + 0.3 + arrow_len], z=[H/2, H/2],
        mode='lines+text', text=['', 'N'],
        textposition='top center',
        textfont=dict(size=14, color='red'),
        line=dict(color='red', width=6),
        showlegend=False
    ))
    
    fig.update_layout(
        scene=dict(
            aspectmode='data',
            camera=dict(eye=dict(x=1.5, y=1.5, z=1.0)),
            xaxis=dict(visible=False),
            yaxis=dict(visible=False),
            zaxis=dict(visible=False),
        ),
        margin=dict(l=0, r=0, t=0, b=0),
        height=280,
        showlegend=False,
    )
    
    return fig


def erstelle_nutzungsprofil(
    name: str,
    heizen_tag: float, heizen_nacht: float,
    kuehlen_tag: float, kuehlen_nacht: float,
    personen: int, geraete_W: float,
    luftwechsel: float,
    tag_start: int, tag_ende: int,
    nachtlueftung: str
) -> Nutzungsprofil:
    """Erstellt ein Nutzungsprofil aus GUI-Eingaben."""
    
    heizen = [heizen_nacht] * 24
    kuehlen = [kuehlen_tag] * 24
    
    for h in range(tag_start, tag_ende):
        heizen[h] = heizen_tag
    
    personen_W = personen * 80
    gewinne = [0.0] * 24
    for h in range(tag_start, tag_ende):
        gewinne[h] = personen_W + geraete_W
    
    ach = [luftwechsel] * 24
    
    nachtlueftung_aktiv = nachtlueftung != "Aus"
    if nachtlueftung == "Erhöht (2 ACH)":
        nachtlueftung_ach = 2.0
    elif nachtlueftung == "Hoch (5 ACH)":
        nachtlueftung_ach = 5.0
    else:
        nachtlueftung_ach = 0.0
    
    return Nutzungsprofil(
        id=name,
        beschreibung=f"GUI-Profil: {name}",
        heizen_C=heizen,
        kuehlen_C=kuehlen,
        interne_gewinne_W=gewinne,
        luftwechsel_1_h=ach,
        f_int_konv=0.4,
        nachtlueftung_aktiv=nachtlueftung_aktiv,
        nachtlueftung_ach=nachtlueftung_ach,
        nachtlueftung_stunden=list(range(22, 24)) + list(range(0, 6)),
    )


def erstelle_din4108_profil(
    nutzungsart: str,
    A_NGF: float,
    volumen: float,
    nachtlueftung_stufe: str
) -> Nutzungsprofil:
    """
    Erstellt ein DIN 4108-2 konformes Nutzungsprofil.
    
    Fixe Normwerte - NICHT änderbar für normativen Nachweis!
    
    WG: 24h Nutzung, 100 Wh/(m²d), n=0.5, θ_heiz=20°C
    NWG: Mo-Fr 7-18h, 144 Wh/(m²d), n=4×A/V bzw. 0.24, θ_heiz=21°C
    
    Alle internen Gewinne 100% konvektiv (f_int_konv=1.0)
    """
    
    if nutzungsart == "Wohngebäude":
        # WG: 24h Nutzung
        heizen = [20.0] * 24  # Konstant 20°C
        kuehlen = [99.0] * 24  # Kühlung aus für SWS
        
        # 100 Wh/(m²d) konstant über 24h = 4.17 W/m²
        gewinne_W_m2 = 100.0 / 24.0  # = 4.17 W/m²
        gewinne = [gewinne_W_m2 * A_NGF] * 24
        
        # Grundluftwechsel 0.5 h⁻¹
        ach = [0.5] * 24
        
        # Aufenthaltszeit: 6-23h
        aufenthalt_stunden = list(range(6, 23))
        
        # Nachtzeit: 23-6h
        nacht_stunden = list(range(23, 24)) + list(range(0, 6))
        
        beschreibung = "DIN 4108-2 Wohngebäude"
        
    else:  # Nichtwohngebäude
        heizen = [21.0] * 24  # Konstant 21°C (nicht 20!)
        kuehlen = [99.0] * 24  # Kühlung aus für SWS
        
        # 144 Wh/(m²d) NUR während Nutzungszeit (7-18h = 11h)
        # = 144 / 11 = 13.1 W/m² während Nutzung, 0 sonst
        gewinne_W_m2_nutzung = 144.0 / 11.0  # = 13.1 W/m²
        gewinne = [0.0] * 24
        for h in range(7, 18):  # 7-18h
            gewinne[h] = gewinne_W_m2_nutzung * A_NGF
        
        # Luftwechsel: n = 4 × A_NGF / V während Nutzung, 0.24 sonst
        n_nutzung = 4.0 * A_NGF / volumen if volumen > 0 else 0.5
        n_ausserhalb = 0.24
        ach = [n_ausserhalb] * 24
        for h in range(7, 18):  # Mo-Fr 7-18h (Wochenende wird in Simulation behandelt)
            ach[h] = n_nutzung
        
        # Aufenthaltszeit: 7-18h
        aufenthalt_stunden = list(range(7, 18))
        
        # Nachtzeit: 18-7h (+ Wochenende, wird in Simulation behandelt)
        nacht_stunden = list(range(18, 24)) + list(range(0, 7))
        
        beschreibung = "DIN 4108-2 Nichtwohngebäude"
    
    # Nachtlüftung
    nachtlueftung_aktiv = nachtlueftung_stufe != "Aus"
    if nachtlueftung_stufe == "Erhöht (2 ACH)":
        nachtlueftung_ach = 2.0
    elif nachtlueftung_stufe == "Hoch (5 ACH)":
        nachtlueftung_ach = 5.0
    else:
        nachtlueftung_ach = 0.0
    
    return Nutzungsprofil(
        id="DIN4108",
        beschreibung=beschreibung,
        heizen_C=heizen,
        kuehlen_C=kuehlen,
        interne_gewinne_W=gewinne,
        luftwechsel_1_h=ach,
        f_int_konv=1.0,  # 100% konvektiv - NORMVORGABE!
        nachtlueftung_aktiv=nachtlueftung_aktiv,
        nachtlueftung_ach=nachtlueftung_ach,
        nachtlueftung_stunden=nacht_stunden,
        # DIN 4108-2 temperaturgesteuerte Lüftung
        lueftung_modus="din4108",
        aufenthaltszeit_stunden=aufenthalt_stunden,
        taglueftung_erhoht_ach=3.0,
    )


def erstelle_gebaeude(
    name: str,
    L: float, B: float, H: float,
    seiten_config: Dict,
    u_werte_global: Dict,
    nutzungsprofil: Nutzungsprofil,
    kappa_werte: Dict = None  # Nur noch für Rückwärtskompatibilität
) -> Gebaeude:
    """Erstellt ein Gebäude aus GUI-Konfiguration.
    
    Sonnenschutz-Parameter werden aus seiten_config geholt:
    - sonnenschutz_steuerung: "statisch", "manuell", "automatik"
    - sonnenschutz_grenzwerte: "norm", "eigene"
    - sonnenschutz_schwelle_eigene: float
    - ist_nwg: bool
    
    kappa und massenklasse werden ebenfalls aus seiten_config geholt.
    """
    
    # Fallback für alte Aufrufe ohne kappa/massenklasse in seiten_config
    default_kappa = 110.0  # Mittel nach ISO
    default_massenklasse = 'I'  # Außendämmung
    
    flaechen = berechne_flaechen(L, B, H)
    volumen = L * B * H
    nutzflaeche = L * B
    
    bauteile = []
    randbedingungen = {
        "AUL": Randbedingung(typ="aussenluft"),
        "ADIABAT": Randbedingung(typ="adiabatisch"),
        "ERD": Randbedingung(typ="erdreich", temperatur_C=10.0),
        "NACHBAR": Randbedingung(typ="nachbar", temperatur_C=20.0),
    }
    
    for seite_id, seite_info in SEITEN.items():
        config = seiten_config[seite_id]
        A_gesamt = flaechen[seite_id]
        A_fenster = A_gesamt * config["fensteranteil"] / 100.0
        A_opak = A_gesamt - A_fenster
        
        rb_code = config["randbedingung"]
        
        # kappa und massenklasse aus seiten_config holen
        kappa = config.get("kappa", default_kappa)
        massenklasse = config.get("massenklasse", default_massenklasse)
        
        if seite_id == "dach":
            U_opak = u_werte_global["dach"]
        elif seite_id == "boden":
            U_opak = u_werte_global["boden"]
        else:
            U_opak = u_werte_global["wand"]
        
        if A_opak > 0:
            bauteile.append(Bauteil(
                id=f"BT_{seite_id.upper()}",
                name=f"{seite_info['name']} (opak)",
                typ="opak",
                flaeche_m2=A_opak,
                azimut_deg=seite_info["azimut"],
                neigung_deg=seite_info["neigung"],
                zone_innen="Z1",
                zone_aussen=rb_code,
                R_c_m2K_W=R_aus_U(U_opak),
                kappa_m_kJ_m2K=kappa,
                alpha_sol=0.6 if rb_code == "AUL" else 0.0,
                massenklasse=massenklasse,
            ))
        
        if A_fenster > 0 and rb_code == "AUL" and seite_id not in ["dach", "boden"]:
            U_fenster = config.get("U_fenster", u_werte_global["fenster"])
            g_wert = config.get("g_wert", u_werte_global["g_wert"])
            Fc = config.get("Fc", 1.0)
            
            # Sonnenschutz-Parameter aus seiten_config
            ss_steuerung = config.get("sonnenschutz_steuerung", "statisch")
            ss_grenzwerte = config.get("sonnenschutz_grenzwerte", "norm")
            ss_schwelle_eigene = config.get("sonnenschutz_schwelle_eigene", 200.0)
            ist_nwg = config.get("ist_nwg", False)
            
            # g-Werte und Fc für Bauteil bestimmen
            if ss_steuerung == "statisch":
                # Statisch: g_wert bereits mit Fc multipliziert
                g_eff = g_wert * Fc
                g_basis = g_wert
                Fc_akt = Fc
                Fc_off = 1.0
            else:
                # Manuell oder Automatik: g_wert_basis rein, Fc wird in Simulation berechnet
                g_eff = g_wert  # Wird in Simulation nicht direkt verwendet
                g_basis = g_wert
                Fc_akt = Fc  # Fc wenn Sonnenschutz aktiviert
                Fc_off = 1.0  # Fc wenn Sonnenschutz offen
            
            bauteile.append(Bauteil(
                id=f"FE_{seite_id.upper()}",
                name=f"Fenster {seite_info['name']}",
                typ="transparent",
                flaeche_m2=A_fenster,
                azimut_deg=seite_info["azimut"],
                neigung_deg=90,
                zone_innen="Z1",
                zone_aussen="AUL",
                U_W_m2K=U_fenster,
                g_wert=g_eff,
                rahmenanteil=0.2,
                sonnenschutz_steuerung=ss_steuerung,
                sonnenschutz_grenzwerte=ss_grenzwerte,
                sonnenschutz_schwelle_eigene=ss_schwelle_eigene,
                ist_nwg=ist_nwg,
                g_wert_basis=g_basis,
                Fc_aktiviert=Fc_akt,
                Fc_offen=Fc_off,
            ))
    
    zone = Zone(
        id="Z1",
        name="Hauptzone",
        volumen_m3=volumen,
        nutzflaeche_m2=nutzflaeche,
        nutzungsprofil=nutzungsprofil.id,
        bauteile=bauteile,
    )
    
    zone.berechne_A_tot()
    
    return Gebaeude(
        name=name,
        beschreibung="Erstellt mit ISO 52016-1 GUI",
        zonen={"Z1": zone},
        randbedingungen=randbedingungen,
        nutzungsprofile={nutzungsprofil.id: nutzungsprofil},
    )


# =============================================================================
# STREAMLIT APP
# =============================================================================

st.title("🏠 RoomCurve")
st.caption("Raumsimulator nach DIN EN ISO 52016-1:2018-04 · sommerlicher Wärmeschutz nach DIN 4108-2:2026-05")

# =============================================================================
# SIDEBAR
# =============================================================================
with st.sidebar:
    st.header("⚙️ Einstellungen")
    
    # ERST: Was für Nachweis?
    st.subheader("📋 DIN 4108-2")
    din_nachweis = st.checkbox("Sommernachweis prüfen", value=True)
    if din_nachweis:
        nutzungsart = st.radio("Nutzung", ["Wohngebäude", "Nichtwohngebäude"])
    else:
        nutzungsart = "Wohngebäude"  # Default wenn SWS aus
    
    st.divider()
    
    # DANN: Klimadaten (bei SWS: 2010 fix)
    st.subheader("🌤️ Klimadaten")
    klimaregion = st.selectbox("TRY Region", list(TRY_REGIONEN.keys()), index=1)
    
    if din_nachweis:
        # SWS: Bezugsjahr fix auf 2010 (Referenz) - normkonform
        klimajahr = "2010 (Referenz)"
        st.text_input("Bezugsjahr", value=klimajahr, disabled=True)
        st.caption("ℹ️ DIN 4108-2: Referenzjahr 2010")
    else:
        klimajahr = st.selectbox("Bezugsjahr", list(TRY_JAHRE.keys()), index=1)
        if "2010" not in klimajahr:
            st.caption(
                "ℹ️ Abweichende Klimadaten (z. B. Zukunfts-TRY): Bewertung des "
                "sommerlichen Wärmeverhaltens mit individuellen Randbedingungen "
                "nach DIN 4108-2:2026-05, Anhang B (informativ) – "
                "kein Ersatz für den Nachweis nach Abschnitt 8.5."
            )
    
    uploaded_klima = st.file_uploader(
        "Eigene TRY-Datei", type=['dat', 'txt', 'csv'],
        help=(
            "Erwartet wird ein stündlicher Jahresdatensatz (8 760 Zeilen) im "
            "TRY-Textformat des DWD, wie er über das BBSR-Klimaberatungsmodul "
            "bereitgestellt wird. Formatdetails: klimadaten/README.md im "
            "GitHub-Repository."
        )
    )
    st.caption(
        "TRY-Daten: entwickelt vom DWD für das BBSR · "
        "kostenfreier Bezug über das [TRY-Portal des BBSR]"
        "(https://www.bbsr-geg.bund.de/GEGPortal/DE/Praxishilfen/"
        "Testreferenzjahre/TRY_node.html)"
    )
    
    st.divider()
    
    # Kühlung nur anzeigen wenn NICHT im SWS-Modus
    if not din_nachweis:
        st.subheader("❄️ Kühlung")
        kuehlung_aktiv = st.checkbox("Aktive Kühlung", value=False)
        if kuehlung_aktiv:
            st.caption("Kühlsollwert siehe Nutzungsprofil")
        st.divider()
    else:
        kuehlung_aktiv = False
    
    # Primärenergie nur anzeigen wenn NICHT im SWS-Modus
    if not din_nachweis:
        st.subheader("⚡ Primärenergie")
        pe_preset = st.selectbox("Energieträger", ["Gas-Brennwert + Strom", "Wärmepumpe + PV", "Fernwärme", "Manuell"])
        
        if pe_preset == "Gas-Brennwert + Strom":
            fp_H_default, fp_C_default = 1.1, 2.4
        elif pe_preset == "Wärmepumpe + PV":
            fp_H_default, fp_C_default = 0.5, 0.5
        elif pe_preset == "Fernwärme":
            fp_H_default, fp_C_default = 0.7, 2.4
        else:
            fp_H_default, fp_C_default = 1.0, 1.0
        
        col_fp1, col_fp2 = st.columns(2)
        with col_fp1:
            fp_H = st.number_input("f_P Heizen", 0.0, 3.0, fp_H_default, 0.1, format="%.1f")
        with col_fp2:
            fp_C = st.number_input("f_P Kühlen", 0.0, 3.0, fp_C_default, 0.1, format="%.1f")
        
        st.divider()
    else:
        # Für SWS-Modus: PE nicht relevant
        fp_H, fp_C = 1.0, 1.0
    
    run_button = st.button("🚀 Simulation starten", type="primary", width="stretch")


# =============================================================================
# HAUPTBEREICH
# =============================================================================

# Kubatur und 3D
col_kubatur, col_3d = st.columns([1, 1])

with col_kubatur:
    st.subheader("📐 Kubatur")
    c1, c2, c3 = st.columns(3)
    with c1:
        laenge = st.number_input("Länge [m]", 1.0, 100.0, 10.0, 0.5)
    with c2:
        breite = st.number_input("Breite [m]", 1.0, 100.0, 8.0, 0.5)
    with c3:
        hoehe = st.number_input("Höhe [m]", 2.0, 20.0, 3.0, 0.1)
    
    flaechen = berechne_flaechen(laenge, breite, hoehe)
    volumen = laenge * breite * hoehe
    
    st.info(f"**V:** {volumen:.0f} m³ | **A_NGF:** {laenge*breite:.0f} m² | **A_Hülle:** {sum(flaechen.values()):.0f} m²")

# Gebäudehülle (U-Werte + Seiten kombiniert)
st.subheader("🧱 Gebäudehülle")

# Baustandard-Preset + Bauschwere + Massenverteilung
col_preset, col_bauschwere, col_masse = st.columns([1, 1, 1])
with col_preset:
    preset_name = st.selectbox("Baustandard", list(U_WERT_PRESETS.keys()), index=1)
    preset = U_WERT_PRESETS[preset_name].copy()
with col_bauschwere:
    bauschwere_name = st.selectbox("Bauschwere", list(BAUSCHWERE_ISO.keys()), index=2)  # Default: Mittel
    kappa_global = BAUSCHWERE_ISO[bauschwere_name]
with col_masse:
    massenverteilung_name = st.selectbox("Massenverteilung", list(MASSENKLASSEN.keys()), index=0)  # Default: Außendämmung
    massenklasse_global = MASSENKLASSEN[massenverteilung_name]

# U-Werte
col_wand, col_dach, col_boden = st.columns([1, 1, 1])
with col_wand:
    preset["wand"] = st.number_input("U Wand", 0.1, 3.0, preset["wand"], 0.01, format="%.2f", help="W/m²K")
with col_dach:
    preset["dach"] = st.number_input("U Dach", 0.1, 2.0, preset["dach"], 0.01, format="%.2f", help="W/m²K")
with col_boden:
    preset["boden"] = st.number_input("U Boden", 0.1, 2.0, preset["boden"], 0.01, format="%.2f", help="W/m²K")

# Anpassung pro Bauteil
anpassung_pro_bauteil = st.checkbox("Anpassung pro Bauteil", value=False, 
    help="Ermöglicht individuelle Massenklasse und Bauschwere pro Seite")

seiten_config = {}

# Seiten-Tabs
tabs = st.tabs(["🔼 Nord", "▶️ Ost", "🔽 Süd", "◀️ West", "⬆️ Dach", "⬇️ Boden"])

for i, (seite_id, seite_info) in enumerate(SEITEN.items()):
    with tabs[i]:
        A_seite = flaechen[seite_id]
        
        col1, col2 = st.columns([1, 1])
        
        with col1:
            default_rb = "Erdreich" if seite_id == "boden" else "Außenluft"
            rb = st.selectbox(
                "Randbedingung",
                list(RANDBEDINGUNGEN.keys()),
                index=list(RANDBEDINGUNGEN.keys()).index(default_rb),
                key=f"rb_{seite_id}"
            )
            rb_code = RANDBEDINGUNGEN[rb]
            
            # Massenklasse und Bauschwere - abhängig von Randbedingung und Checkbox
            if rb_code == "ADIABAT":
                # ADIABAT: Massenklasse fest I, ausgeblendet
                seite_massenklasse = "I"
                if anpassung_pro_bauteil:
                    # Nur Bauschwere-Override zeigen
                    bs_optionen = [f"Vorgabe ({int(kappa_global)})"] + list(BAUSCHWERE_ISO.keys())
                    bs_wahl = st.selectbox("Bauschwere", bs_optionen, index=0, key=f"bs_{seite_id}")
                    seite_kappa = kappa_global if bs_wahl.startswith("Vorgabe") else BAUSCHWERE_ISO[bs_wahl]
                else:
                    seite_kappa = kappa_global
            elif rb_code == "NACHBAR":
                # Nachbar: Massenklasse fest D, ausgeblendet
                seite_massenklasse = "D"
                if anpassung_pro_bauteil:
                    bs_optionen = [f"Vorgabe ({int(kappa_global)})"] + list(BAUSCHWERE_ISO.keys())
                    bs_wahl = st.selectbox("Bauschwere", bs_optionen, index=0, key=f"bs_{seite_id}")
                    seite_kappa = kappa_global if bs_wahl.startswith("Vorgabe") else BAUSCHWERE_ISO[bs_wahl]
                else:
                    seite_kappa = kappa_global
            else:
                # AUL, ERD: Beide Override-Optionen verfügbar
                if anpassung_pro_bauteil:
                    mk_optionen = [f"Vorgabe ({massenklasse_global})"] + list(MASSENKLASSEN.keys())
                    mk_wahl = st.selectbox("Massenklasse", mk_optionen, index=0, key=f"mk_{seite_id}")
                    seite_massenklasse = massenklasse_global if mk_wahl.startswith("Vorgabe") else MASSENKLASSEN[mk_wahl]
                    
                    bs_optionen = [f"Vorgabe ({int(kappa_global)})"] + list(BAUSCHWERE_ISO.keys())
                    bs_wahl = st.selectbox("Bauschwere", bs_optionen, index=0, key=f"bs_{seite_id}")
                    seite_kappa = kappa_global if bs_wahl.startswith("Vorgabe") else BAUSCHWERE_ISO[bs_wahl]
                else:
                    seite_massenklasse = massenklasse_global
                    seite_kappa = kappa_global
            
            if seite_id in ["nord", "ost", "sued", "west"]:
                # Bei Adiabatisch/Erdreich: keine Fenster möglich
                if RANDBEDINGUNGEN[rb] in ["ADIABAT", "ERD"]:
                    fenster_pct = 0
                    fenster_m2 = 0.0
                    st.caption("ℹ️ Keine Fenster bei Adiabatisch/Erdreich")
                else:
                    # Eingabemodus wählen
                    eingabe_modus = st.radio(
                        "Eingabe als", ["Prozent", "m²"], 
                        horizontal=True, key=f"mode_{seite_id}"
                    )
                    
                    if eingabe_modus == "Prozent":
                        fenster_pct = st.slider(
                            "Fensteranteil [%]", 0, 80, seite_info["default_fenster"],
                            key=f"fenster_{seite_id}"
                        )
                        fenster_m2 = A_seite * fenster_pct / 100
                        st.caption(f"= **{fenster_m2:.1f} m²** Fensterfläche")
                    else:
                        default_m2 = A_seite * seite_info["default_fenster"] / 100
                        fenster_m2 = st.number_input(
                            "Fensterfläche [m²]", 0.0, A_seite * 0.8, default_m2, 0.5,
                            key=f"fenster_m2_{seite_id}"
                        )
                        fenster_pct = (fenster_m2 / A_seite * 100) if A_seite > 0 else 0
                        st.caption(f"= **{fenster_pct:.0f}%** der Wandfläche")
            else:
                fenster_pct = 0
                fenster_m2 = 0.0
        
        with col2:
            if fenster_pct > 0 and RANDBEDINGUNGEN[rb] == "AUL":
                st.markdown(f"**Fenster ({fenster_m2:.1f} m²)**")
                U_fenster = st.number_input(
                    "U [W/m²K]", 0.5, 4.0, preset["fenster"], 0.1,
                    key=f"U_f_{seite_id}"
                )
                g_wert = st.number_input(
                    "g [-]", 0.2, 0.85, preset["g_wert"], 0.05,
                    key=f"g_{seite_id}"
                )
                
                # Sonnenschutz (Anhaltswerte DIN 4108-2:2026-05, Abschn. 8.6)
                sonnenschutz = st.selectbox(
                    "Sonnenschutz", list(SONNENSCHUTZ_TYPEN.keys()),
                    key=f"ss_{seite_id}"
                )
                
                if sonnenschutz not in ("Ohne", "Manuell"):
                    verglasung = st.radio(
                        "Verglasung", ["zweifach", "dreifach"],
                        horizontal=True, key=f"vg_{seite_id}"
                    )
                else:
                    verglasung = "zweifach"
                
                if sonnenschutz == "Manuell":
                    Fc = None
                else:
                    Fc = fc_anhaltswert(sonnenschutz, g_wert, verglasung)
                    if Fc is None:
                        st.warning(
                            "Für Sonnenschutz im Scheibenzwischenraum bzw. in "
                            "mehrschaliger Konstruktion mit g ≤ 0,40 nennt "
                            "DIN 4108-2:2026-05 keine Anhaltswerte "
                            "(detaillierte Ermittlung erforderlich) – bitte "
                            "F_C manuell eingeben."
                        )
                
                if Fc is None:
                    Fc = st.number_input(
                        "F_C manuell", 0.05, 1.0, 0.5, 0.05,
                        key=f"fc_{seite_id}",
                        help=(
                            "F_C-Wert der Sonnenschutzvorrichtung. "
                            "Detail-Anhaltswerte nach Reflexions- und "
                            "Lichttransmissionsklasse: DIN 4108-2:2026-05, "
                            "Abschnitt 8.6. Liegt stattdessen ein g_tot nach "
                            "DIN EN ISO 52022 bzw. Herstellerangabe vor: "
                            "F_C = g_tot / g eintragen."
                        ),
                    )
                
                g_eff = g_wert * Fc
                st.info(f"**F_C = {Fc:.2f}** → g_eff = {g_eff:.2f}")
            else:
                U_fenster = preset["fenster"]
                g_wert = preset["g_wert"]
                Fc = 1.0
        
        seiten_config[seite_id] = {
            "randbedingung": rb_code,
            "fensteranteil": fenster_pct,
            "U_fenster": U_fenster,
            "g_wert": g_wert,
            "Fc": Fc,
            "massenklasse": seite_massenklasse,
            "kappa": seite_kappa,
            # Sonnenschutz-Steuerung (wird nach Tabs global gesetzt)
            "sonnenschutz_steuerung": "automatik",  # Placeholder
            "sonnenschutz_grenzwerte": "norm",  # Placeholder
            "sonnenschutz_schwelle_eigene": 200.0,  # Placeholder
            "ist_nwg": nutzungsart == "Nichtwohngebäude",
        }
        
        A = flaechen[seite_id]
        A_f = A * fenster_pct / 100
        st.caption(f"Gesamt: {A:.1f}m² | Opak: {A-A_f:.1f}m² | Fenster: {A_f:.1f}m²")

# Sonnenschutz-Steuerung (nach den Tabs, gilt für alle Fenster)
# Prüfen ob irgendwo Sonnenschutz aktiv (Fc < 1.0)
hat_sonnenschutz = any(
    seiten_config[s].get("Fc", 1.0) < 1.0 
    for s in ["nord", "ost", "sued", "west"]
)

st.markdown("**Sonnenschutz-Steuerung**")
if not hat_sonnenschutz:
    st.caption("ℹ️ Kein Sonnenschutz aktiv (alle Fc=1.0) – Steuerung irrelevant")

col_ss1, col_ss2, col_ss3 = st.columns([1, 1, 1])
with col_ss1:
    sonnenschutz_steuerung = st.selectbox(
        "Steuerung",
        ["Automatik (Sensor)", "Manuell (Nutzer)", "Statisch (fest)"],
        index=2 if not hat_sonnenschutz else 0,  # Default Statisch wenn kein SS
        help="Automatik: immer wenn I > Schwelle | Manuell: I > Schwelle, NWG-WE → Fc=1 | Statisch: Fc gilt immer",
        disabled=not hat_sonnenschutz
    )
with col_ss2:
    if "Statisch" not in sonnenschutz_steuerung and hat_sonnenschutz:
        sonnenschutz_grenzwerte = st.selectbox(
            "Grenzwerte",
            ["Norm (DIN 4108-2)", "Eigene"],
            index=0,
            help="Norm: WG 300/200, NWG 200/150 W/m²"
        )
    else:
        sonnenschutz_grenzwerte = "Norm (DIN 4108-2)"
        if hat_sonnenschutz:
            st.caption("ℹ️ Fc gilt immer")
with col_ss3:
    if "Statisch" not in sonnenschutz_steuerung and sonnenschutz_grenzwerte == "Eigene" and hat_sonnenschutz:
        sonnenschutz_schwelle_eigene = st.number_input(
            "Schwelle [W/m²]", 50, 500, 200, 25
        )
    else:
        sonnenschutz_schwelle_eigene = 200.0
        if "Statisch" not in sonnenschutz_steuerung and hat_sonnenschutz:
            if nutzungsart == "Nichtwohngebäude":
                st.caption("NWG: 200/150 W/m²")
            else:
                st.caption("WG: 300/200 W/m²")

if "Manuell" in sonnenschutz_steuerung and nutzungsart == "Nichtwohngebäude" and hat_sonnenschutz:
    st.caption("⚠️ NWG + Manuell: Am Wochenende inaktiv (Fc=1.0)")

# seiten_config mit Sonnenschutz-Steuerung aktualisieren
ss_steuerung_code = "automatik" if "Automatik" in sonnenschutz_steuerung else ("statisch" if "Statisch" in sonnenschutz_steuerung else "manuell")
ss_grenzwerte_code = "norm" if "Norm" in sonnenschutz_grenzwerte else "eigene"

for seite_id in seiten_config:
    seiten_config[seite_id]["sonnenschutz_steuerung"] = ss_steuerung_code
    seiten_config[seite_id]["sonnenschutz_grenzwerte"] = ss_grenzwerte_code
    seiten_config[seite_id]["sonnenschutz_schwelle_eigene"] = sonnenschutz_schwelle_eigene

# 3D
with col_3d:
    st.subheader("🔲 3D-Vorschau")
    fig_3d = erstelle_3d_visualisierung(laenge, breite, hoehe, seiten_config, flaechen)
    st.plotly_chart(fig_3d, width="stretch")

# Nutzung
st.subheader("👥 Nutzung")

if din_nachweis:
    # DIN 4108-2 Modus: Fixe Normwerte anzeigen
    st.info("📋 **DIN 4108-2 Modus** - Normwerte werden verwendet")
    
    col1, col2 = st.columns(2)
    with col1:
        if nutzungsart == "Wohngebäude":
            st.markdown("""
            **Wohngebäude (fix):**
            - Nutzung: 0-24 Uhr (ganzjährig)
            - Interne Gewinne: 100 Wh/(m²d) = 4,17 W/m²
            - Luftwechsel: n = 0,5 h⁻¹
            - Heiz-Solltemp: 20°C
            - Aufenthaltszeit: 6-23 Uhr
            - Nachtzeit: 23-6 Uhr
            """)
        else:
            A_NGF_temp = laenge * breite
            V_temp = laenge * breite * hoehe
            n_nutz = 4.0 * A_NGF_temp / V_temp if V_temp > 0 else 0.5
            st.markdown(f"""
            **Nichtwohngebäude (fix):**
            - Nutzung: Mo-Fr 7-18 Uhr
            - Interne Gewinne: 144 Wh/(m²d) = 13,1 W/m²
            - Luftwechsel: n = {n_nutz:.2f} h⁻¹ (Nutzung), 0,24 h⁻¹ (sonst)
            - Heiz-Solltemp: 21°C
            - Nachtzeit: 18-7 Uhr + Wochenende
            """)
    
    with col2:
        nachtlueftung = st.selectbox("Nachtlüftung", ["Aus", "Erhöht (2 ACH)", "Hoch (5 ACH)"])
        if nachtlueftung != "Aus":
            st.warning("⚠️ Nachtlüftung nur zulässig wenn g_tot ≤ 0,40!")
    
    # Dummy-Werte für nicht-verwendete Variablen
    heizen_tag, heizen_nacht = 20.0, 18.0
    kuehlen = 99.0
    tag_start, tag_ende = 7, 22
    luftwechsel = 0.5
    personen, geraete = 2, 150

else:
    # Normaler Modus: Freie Eingabe
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("**Temperatur**")
        heizen_tag = st.number_input("Heizen Tag [°C]", 15.0, 25.0, 20.0, 0.5)
        heizen_nacht = st.number_input("Heizen Nacht [°C]", 10.0, 22.0, 18.0, 0.5)
        if kuehlung_aktiv:
            kuehlen = st.number_input("Kühlen [°C]", 24.0, 30.0, 26.0, 0.5)
        else:
            kuehlen = 99.0  # Effektiv aus
            st.caption("Kühlung: aus")
    
    with col2:
        st.markdown("**Nutzungszeit**")
        col_von, col_bis = st.columns(2)
        with col_von:
            tag_start = st.number_input("von", 0, 12, 7, format="%d", help="Uhr")
        with col_bis:
            tag_ende = st.number_input("bis", 12, 24, 22, format="%d", help="Uhr")
        st.caption(f"= {tag_ende - tag_start}h Nutzung/Tag")
        luftwechsel = st.number_input("Luftwechsel [1/h]", 0.1, 2.0, 0.5, 0.1)
    
    with col3:
        st.markdown("**Interne Gewinne**")
        personen = st.number_input("Personen", 0, 20, 2)
        personen_W = personen * 80
        st.caption(f"× 80 W = {personen_W} W")
        geraete = st.number_input("Geräte [W]", 0, 2000, 150, 50)
        gesamt_W = personen_W + geraete
        st.caption(f"**Gesamt: {gesamt_W} W**")
        nachtlueftung = st.selectbox("Nachtlüftung", ["Aus", "Erhöht (2 ACH)", "Hoch (5 ACH)"])


# =============================================================================
# SIMULATION
# =============================================================================

if run_button:
    with st.spinner("Simulation läuft..."):
        try:
            A_NGF = laenge * breite
            volumen = laenge * breite * hoehe
            
            # Profil erstellen - DIN 4108-2 oder frei
            if din_nachweis:
                profil = erstelle_din4108_profil(
                    nutzungsart, A_NGF, volumen, nachtlueftung
                )
            else:
                profil = erstelle_nutzungsprofil(
                    "GUI", heizen_tag, heizen_nacht, kuehlen, kuehlen,
                    personen, geraete, luftwechsel, tag_start, tag_ende, nachtlueftung
                )
            
            # Sonnenschutz-Parameter sind jetzt in seiten_config
            gebaeude = erstelle_gebaeude(
                "GUI_Raum", laenge, breite, hoehe,
                seiten_config, preset, profil
            )
            
            # Klimadaten
            klima = None
            if uploaded_klima:
                import tempfile
                with tempfile.NamedTemporaryFile(delete=False, suffix='.txt') as tmp:
                    tmp.write(uploaded_klima.getvalue())
                    tmp_path = tmp.name
                st.info(f"📂 {uploaded_klima.name}")
                klima = load_climate(tmp_path, format='try')
                os.unlink(tmp_path)
            
            if klima is None:
                klimadaten_dir = Path(__file__).parent.parent / "klimadaten"
                try_datei = klimadaten_dir / f"TRY{TRY_JAHRE[klimajahr]}-{TRY_REGIONEN[klimaregion]}-Jahr.txt"
                
                if try_datei.exists():
                    st.info(f"📂 {try_datei.name}")
                    klima = load_climate(str(try_datei), format='try')
                else:
                    st.warning("⚠️ Demo-Klimadaten")
                    klima = create_constant_climate(8760, 10.0, 200.0)
            
            # Simulation
            ergebnisse = simuliere(gebaeude, klima, SimulationsOptionen(klimadatei="gui"))
            
            # ===== ERGEBNISSE =====
            st.success("✅ Simulation abgeschlossen!")
            st.header("📊 Ergebnisse")
            
            Q_H = ergebnisse['gesamt']['Q_H_kWh']
            Q_C = ergebnisse['gesamt']['Q_C_kWh']
            A_NGF = laenge * breite
            Q_PE = Q_H * fp_H + Q_C * fp_C
            
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Heizwärmebedarf", f"{Q_H:,.0f} kWh/a", f"{Q_H/A_NGF:.1f} kWh/m²a")
            c2.metric("Kühlbedarf", f"{Q_C:,.0f} kWh/a", f"{Q_C/A_NGF:.1f} kWh/m²a")
            c3.metric("Primärenergie", f"{Q_PE:,.0f} kWh/a", f"{Q_PE/A_NGF:.1f} kWh/m²a")
            c4.metric("Nutzfläche", f"{A_NGF:.0f} m²")
            
            # Monatliche Werte
            if 'zonen' in ergebnisse and 'Z1' in ergebnisse['zonen']:
                zone_erg = ergebnisse['zonen']['Z1']
                
                with st.expander("📅 Monatswerte"):
                    import pandas as pd
                    monate_namen = ['Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun', 
                                   'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez']
                    
                    if 'monate' in zone_erg:
                        monate = zone_erg['monate']
                        df_mon = pd.DataFrame({
                            'Monat': monate_namen,
                            'Q_H [kWh]': [m.get('Q_H_kWh', 0) for m in monate],
                            'Q_C [kWh]': [m.get('Q_C_kWh', 0) for m in monate],
                            'θ_max [°C]': [m.get('theta_op_max', 0) for m in monate],
                            'θ_min [°C]': [m.get('theta_op_min', 0) for m in monate],
                        })
                        st.dataframe(df_mon, hide_index=True, width="stretch")
                        
                        # Monatlicher Heiz-/Kühlbedarf als Balkendiagramm
                        st.bar_chart(df_mon.set_index('Monat')[['Q_H [kWh]', 'Q_C [kWh]']])
            
            # Temperaturverlauf
            if 'zonen' in ergebnisse and 'Z1' in ergebnisse['zonen']:
                theta_op = np.array(ergebnisse['zonen']['Z1'].get('theta_op', []))
                
                if len(theta_op) >= 8760:
                    # Sommerwoche
                    wochen_mittel = [np.mean(theta_op[i*168:(i+1)*168]) for i in range(52)]
                    sw = np.argmax(wochen_mittel)
                    
                    import pandas as pd
                    st.subheader("🌡️ Wärmste Woche")
                    st.caption(f"Kalenderwoche {sw+1}")
                    df = pd.DataFrame({
                        'Raum [°C]': theta_op[sw*168:(sw+1)*168],
                        'Außen [°C]': klima.theta_e[sw*168:(sw+1)*168]
                    })
                    st.line_chart(df)
                    
                    # Stündliche Werte als Expander
                    with st.expander("📈 Stündliche Werte (Download)"):
                        df_stunden = pd.DataFrame({
                            'Stunde': range(1, 8761),
                            'θ_op [°C]': theta_op,
                            'θ_e [°C]': klima.theta_e[:8760],
                        })
                        st.dataframe(df_stunden.head(168), hide_index=True, width="stretch")
                        st.caption("Zeige erste 168 Stunden (1 Woche)")
                        
                        # Download-Button
                        csv = df_stunden.to_csv(index=False)
                        st.download_button(
                            "💾 CSV herunterladen",
                            csv,
                            "stundenwerte.csv",
                            "text/csv"
                        )
                    
                    # DIN 4108-2
                    if din_nachweis:
                        st.subheader("📋 DIN 4108-2 Sommerlicher Wärmeschutz")
                        
                        # Bezugstemperatur nach Region
                        if "Region A" in klimaregion:
                            theta_ref = 25.0
                            region_name = "A"
                        elif "Region C" in klimaregion:
                            theta_ref = 27.0
                            region_name = "C"
                        else:  # Region B (Default)
                            theta_ref = 26.0
                            region_name = "B"
                        
                        # Grenzwert nach Nutzungsart
                        grenzwert = 1200 if "Wohn" in nutzungsart else 500
                        
                        # Nutzungsstunden für Überschreitungshäufigkeit
                        if "Wohn" in nutzungsart:
                            # WG: 8760h (24h × 365d)
                            nutzungsstunden = 8760
                            theta_op_nutzung = theta_op  # Alle Stunden
                        else:
                            # NWG: 2871h (11h × 261d = Mo-Fr 7-18h)
                            nutzungsstunden = 2871
                            # Nur Nutzungsstunden filtern (Mo-Fr 7-18h)
                            # Simulation startet 1.1. Montag
                            nutzungs_maske = np.zeros(8760, dtype=bool)
                            for tag in range(365):
                                wochentag = tag % 7  # 0=Mo, 6=So
                                if wochentag < 5:  # Mo-Fr
                                    for h in range(7, 18):  # 7-18h
                                        stunde = tag * 24 + h
                                        if stunde < 8760:
                                            nutzungs_maske[stunde] = True
                            theta_op_nutzung = theta_op[nutzungs_maske]
                        
                        # Gh über Bezugstemperatur
                        Gh = np.sum(np.maximum(0, theta_op_nutzung - theta_ref))
                        h_ueber = np.sum(theta_op_nutzung > theta_ref)
                        
                        # Hauptergebnis
                        st.markdown(f"**Bezugstemperatur:** θ_ref = {theta_ref:.0f}°C (Region {region_name})")
                        
                        if Gh <= grenzwert:
                            st.success(f"✅ **Nachweis ERFÜLLT** | Gh = {Gh:.0f} Kh ≤ {grenzwert} Kh ({Gh/grenzwert*100:.0f}%)")
                        else:
                            st.error(f"❌ **NICHT erfüllt** | Gh = {Gh:.0f} Kh > {grenzwert} Kh (+{(Gh/grenzwert-1)*100:.0f}%)")
                            st.info("💡 Sonnenschutz verbessern, Nachtlüftung aktivieren, g-Wert reduzieren")
                        
                        # Überschreitungshäufigkeit Kat I/II/III
                        # HINWEIS: Bei adaptivem Komfort sind die Grenzwerte variabel,
                        # daher hier nur Kategorie-Namen ohne feste Temperaturwerte
                        st.markdown("---")
                        st.markdown(f"**Überschreitungshäufigkeit** (Anteil an {nutzungsstunden}h Jahresnutzung)")
                        
                        h_kat1 = np.sum(theta_op_nutzung > 26)  # Kat I
                        h_kat2 = np.sum(theta_op_nutzung > 27)  # Kat II
                        h_kat3 = np.sum(theta_op_nutzung > 28)  # Kat III
                        
                        p_kat1 = h_kat1 / nutzungsstunden * 100
                        p_kat2 = h_kat2 / nutzungsstunden * 100
                        p_kat3 = h_kat3 / nutzungsstunden * 100
                        
                        c1, c2, c3 = st.columns(3)
                        c1.metric("Kat I", f"{p_kat1:.1f}%", f"{h_kat1}h")
                        c2.metric("Kat II", f"{p_kat2:.1f}%", f"{h_kat2}h")
                        c3.metric("Kat III", f"{p_kat3:.1f}%", f"{h_kat3}h")
                        
                        st.caption(f"θ_max = {np.max(theta_op_nutzung):.1f}°C | θ_min = {np.min(theta_op_nutzung):.1f}°C")
                        
        except Exception as e:
            st.error(f"❌ {e}")
            import traceback
            st.code(traceback.format_exc())

st.divider()

col1, col2 = st.columns([3, 1])
with col1:
    _quelle = (f"[Quellcode]({QUELLCODE_URL})" if QUELLCODE_URL
               else "Quellcode: siehe LICENSE im Programmpaket")
    st.caption(f"RoomCurve **BETA** | BESTEST-verifiziert nach ISO 52016-1 Kap. 7.2 | AGPL-3.0 · {_quelle} | © 2026 Mario Vukadinovic")
with col2:
    st.markdown(f"[💬 Kontakt]({contact_url})")

with st.expander("🔒 Datenschutz"):
    st.markdown("""
Diese App wird auf der **Streamlit Community Cloud** (Betreiber: Snowflake Inc., USA)
gehostet; beim Aufruf können durch den Hosting-Anbieter technische Zugriffsdaten
(z. B. IP-Adresse) verarbeitet werden. Die in der App gemachten **Eingaben und
Berechnungsergebnisse werden nicht gespeichert** und nicht an Dritte weitergegeben.
Kontakt für Anfragen: über den Kontakt-Link (LinkedIn) in der Fußzeile.
""")

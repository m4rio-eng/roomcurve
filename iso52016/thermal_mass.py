# Copyright (c) 2026 Mario Vukadinovic
# SPDX-License-Identifier: AGPL-3.0-only
# Part of the ISO 52016-1 Room Simulator. See LICENSE.
# Commercial licensing available on request.

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ISO 52016-1 / ISO 13786: Wirksame Wärmekapazität κ_m
====================================================

Berechnung der flächenbezogenen wirksamen Wärmekapazität κ_m aus dem
Schichtaufbau eines Bauteils nach DIN EN ISO 13786 (Anhang C).

Die Massenverteilung auf die 5 Rechenknoten erfolgt nach 
DIN EN ISO 52016-1, Tabelle A.13/B.13.

Referenzen:
- DIN EN ISO 52016-1:2018-04, Abschnitt 6.5.7
- DIN EN ISO 13786:2017, Anhang C (vereinfachtes Verfahren)
"""

import math
from dataclasses import dataclass, field
from typing import List, Tuple, Optional
from enum import Enum


# =============================================================================
# KONSTANTEN
# =============================================================================

# Maximale wirksame Dicke [m] - ISO 13786, für Tagesperiode (T = 86400s)
D_T_MAX = 0.10  # 100 mm

# Grenzwert für Wärmedämmschicht [W/(m·K)] - typisch < 0.1
LAMBDA_DAEMMUNG_GRENZE = 0.1

# Standardwerte für κ_m falls keine Schichtdaten [J/(m²·K)]
# ISO 52016-1, Tabelle B.14
KAPPA_M_PAUSCHAL = {
    'sehr_leicht': 50000,
    'leicht': 75000,
    'mittel': 110000,
    'schwer': 175000,
    'sehr_schwer': 250000,
}


# =============================================================================
# DATENKLASSEN
# =============================================================================

class Massenklasse(Enum):
    """
    Massenverteilungsklassen nach ISO 52016-1, Tabelle A.13/B.13
    
    Bestimmt, wie κ_m auf die 5 Rechenknoten verteilt wird.
    """
    I = "I"      # Masse INNEN (Außendämmung) → Knoten 5
    E = "E"      # Masse AUSSEN (Innendämmung) → Knoten 1
    IE = "IE"    # Masse BEIDSEITIG (Kerndämmung) → Knoten 1 + 5
    D = "D"      # GLEICHMÄSSIG verteilt (ungedämmt) → alle Knoten
    M = "M"      # Masse in MITTE → Knoten 3


@dataclass
class Schicht:
    """
    Eine Materialschicht im Bauteilaufbau
    
    Reihenfolge: von INNEN nach AUSSEN
    """
    name: str
    dicke_m: float              # Schichtdicke [m]
    lambda_W_mK: float          # Wärmeleitfähigkeit [W/(m·K)]
    rho_kg_m3: float            # Rohdichte [kg/m³]
    c_J_kgK: float              # spezifische Wärmekapazität [J/(kg·K)]
    
    @property
    def R_m2K_W(self) -> float:
        """Wärmedurchlasswiderstand der Schicht [m²K/W]"""
        if self.lambda_W_mK > 0:
            return self.dicke_m / self.lambda_W_mK
        return 0.0
    
    @property
    def kappa_J_m2K(self) -> float:
        """Flächenbezogene Wärmekapazität der Schicht [J/(m²·K)]"""
        return self.rho_kg_m3 * self.c_J_kgK * self.dicke_m
    
    @property
    def ist_daemmung(self) -> bool:
        """Prüft ob Schicht eine Wärmedämmschicht ist"""
        return self.lambda_W_mK < LAMBDA_DAEMMUNG_GRENZE


@dataclass
class BauteilAufbau:
    """
    Vollständiger Bauteilaufbau mit Schichten
    
    Schichten von INNEN nach AUSSEN geordnet!
    """
    name: str
    schichten: List[Schicht] = field(default_factory=list)
    
    @property
    def dicke_gesamt_m(self) -> float:
        """Gesamtdicke des Bauteils [m]"""
        return sum(s.dicke_m for s in self.schichten)
    
    @property
    def R_gesamt_m2K_W(self) -> float:
        """Gesamter Wärmedurchlasswiderstand [m²K/W]"""
        return sum(s.R_m2K_W for s in self.schichten)
    
    @property
    def U_wert_W_m2K(self) -> float:
        """U-Wert mit Standardübergangskoeffizienten [W/(m²·K)]"""
        R_si = 0.13  # Innen
        R_se = 0.04  # Außen
        R_total = R_si + self.R_gesamt_m2K_W + R_se
        return 1.0 / R_total if R_total > 0 else 0.0


# =============================================================================
# KERNFUNKTIONEN
# =============================================================================

def finde_erste_daemmschicht(schichten: List[Schicht]) -> Optional[int]:
    """
    Findet den Index der ersten Dämmschicht (von innen gezählt).
    
    Args:
        schichten: Liste der Schichten (von innen nach außen)
    
    Returns:
        Index der ersten Dämmschicht oder None
    """
    for i, schicht in enumerate(schichten):
        if schicht.ist_daemmung:
            return i
    return None


def berechne_wirksame_dicke(schichten: List[Schicht]) -> Tuple[float, int]:
    """
    Berechnet die wirksame Dicke d_T nach ISO 13786.
    
    d_T = min(d_tot/2, d_bis_dämmung, d_T_max)
    
    Args:
        schichten: Liste der Schichten (von innen nach außen)
    
    Returns:
        (d_T in Metern, Anzahl wirksamer Schichten)
        
    Referenz:
        ISO 13786:2017, Anhang C.2
    """
    d_tot = sum(s.dicke_m for s in schichten)
    
    # Kriterium 1: Halbe Gesamtdicke
    d_1 = 0.5 * d_tot
    
    # Kriterium 2: Dicke bis zur ersten Dämmschicht
    idx_daemmung = finde_erste_daemmschicht(schichten)
    if idx_daemmung is not None:
        d_2 = sum(s.dicke_m for s in schichten[:idx_daemmung])
    else:
        d_2 = d_tot  # Keine Dämmung → volle Dicke
    
    # Kriterium 3: Maximale wirksame Dicke (100mm für Tagesperiode)
    d_3 = D_T_MAX
    
    # Minimum der drei Kriterien
    d_T = min(d_1, d_2, d_3)
    
    # Zähle wirksame Schichten
    d_kumuliert = 0.0
    n_wirksam = 0
    for schicht in schichten:
        if d_kumuliert >= d_T:
            break
        d_kumuliert += schicht.dicke_m
        n_wirksam += 1
    
    return d_T, n_wirksam


def berechne_kappa_m(schichten: List[Schicht]) -> float:
    """
    Berechnet die wirksame Wärmekapazität κ_m.
    
    κ_m = Σ (ρ_i × c_i × d_i) für d ≤ d_T
    
    Args:
        schichten: Liste der Schichten (von innen nach außen)
    
    Returns:
        κ_m in J/(m²·K)
        
    Referenz:
        ISO 13786:2017, Anhang C, Gleichung C.4
    """
    d_T, _ = berechne_wirksame_dicke(schichten)
    
    kappa_m = 0.0
    d_kumuliert = 0.0
    
    for schicht in schichten:
        if d_kumuliert >= d_T:
            break
        
        # Wie viel von dieser Schicht ist wirksam?
        d_rest = d_T - d_kumuliert
        d_wirksam = min(schicht.dicke_m, d_rest)
        
        # Beitrag dieser Schicht
        kappa_i = schicht.rho_kg_m3 * schicht.c_J_kgK * d_wirksam
        kappa_m += kappa_i
        
        d_kumuliert += schicht.dicke_m
    
    return kappa_m


def bestimme_massenklasse(schichten: List[Schicht]) -> Massenklasse:
    """
    Bestimmt die Massenverteilungsklasse aus dem Schichtaufbau.
    
    Die Klasse hängt davon ab, wo sich die MASSE relativ zur DÄMMUNG befindet.
    Entscheidend ist die Wärmekapazität der Schichten vor/nach der Dämmung.
    
    Args:
        schichten: Liste der Schichten (von innen nach außen)
    
    Returns:
        Massenklasse (I, E, IE, D, M)
        
    Referenz:
        DIN EN ISO 52016-1:2018-04, Tabelle A.13/B.13
    """
    if not schichten:
        return Massenklasse.D
    
    # Finde erste Dämmschicht
    idx_daemmung = finde_erste_daemmschicht(schichten)
    
    if idx_daemmung is None:
        # Keine Dämmung → gleichmäßig verteilt
        return Massenklasse.D
    
    if idx_daemmung == 0:
        # Dämmung ganz innen → Masse außen
        return Massenklasse.E
    
    # Berechne Wärmekapazität vor und nach der Dämmung
    kappa_innen = sum(s.kappa_J_m2K for s in schichten[:idx_daemmung])
    kappa_aussen = sum(s.kappa_J_m2K for s in schichten[idx_daemmung+1:])
    
    # Schwellwert: Wenn eine Seite >80% der Masse hat → einseitig
    kappa_total = kappa_innen + kappa_aussen
    if kappa_total < 1000:  # Sehr wenig Masse → gleichmäßig
        return Massenklasse.D
    
    anteil_innen = kappa_innen / kappa_total
    
    if anteil_innen > 0.8:
        # Masse hauptsächlich innen (>80%)
        return Massenklasse.I
    elif anteil_innen < 0.2:
        # Masse hauptsächlich außen (>80%)
        return Massenklasse.E
    else:
        # Masse beidseitig
        return Massenklasse.IE


def verteile_kapazitaet_auf_knoten(kappa_m_J_m2K: float, 
                                   klasse: Massenklasse) -> List[float]:
    """
    Verteilt κ_m auf die 5 Rechenknoten nach ISO 52016-1.
    
    Knoten: [1, 2, 3, 4, 5] wobei 1=außen, 5=innen
    
    Args:
        kappa_m_J_m2K: Wirksame Wärmekapazität [J/(m²·K)]
        klasse: Massenverteilungsklasse
    
    Returns:
        Liste mit 5 Kapazitätswerten [J/(m²·K)]
        
    Referenz:
        DIN EN ISO 52016-1:2018-04, Tabelle A.13 (Gleichungen 44-47)
    """
    kappa = kappa_m_J_m2K
    
    if klasse == Massenklasse.I:
        # Gleichung 44: Masse innen konzentriert
        return [0.0, 0.0, 0.0, 0.0, kappa]
    
    elif klasse == Massenklasse.E:
        # Gleichung 45: Masse außen konzentriert
        return [kappa, 0.0, 0.0, 0.0, 0.0]
    
    elif klasse == Massenklasse.IE:
        # Gleichung 46: Masse beidseitig
        return [kappa/2, 0.0, 0.0, 0.0, kappa/2]
    
    elif klasse == Massenklasse.D:
        # Gleichung 47a: Gleichmäßig verteilt
        return [kappa/8, kappa/4, kappa/4, kappa/4, kappa/8]
    
    elif klasse == Massenklasse.M:
        # Gleichung 47b: Masse in Mitte
        return [0.0, 0.0, kappa, 0.0, 0.0]
    
    else:
        # Fallback: gleichmäßig
        return [kappa/8, kappa/4, kappa/4, kappa/4, kappa/8]


# =============================================================================
# KOMFORTFUNKTION
# =============================================================================

def analysiere_bauteil(aufbau: BauteilAufbau) -> dict:
    """
    Vollständige Analyse eines Bauteilaufbaus.
    
    Args:
        aufbau: BauteilAufbau mit Schichten
    
    Returns:
        Dict mit allen berechneten Werten
    """
    d_T, n_wirksam = berechne_wirksame_dicke(aufbau.schichten)
    kappa_m = berechne_kappa_m(aufbau.schichten)
    klasse = bestimme_massenklasse(aufbau.schichten)
    kappa_knoten = verteile_kapazitaet_auf_knoten(kappa_m, klasse)
    
    return {
        'name': aufbau.name,
        'dicke_gesamt_m': aufbau.dicke_gesamt_m,
        'R_gesamt_m2K_W': aufbau.R_gesamt_m2K_W,
        'U_wert_W_m2K': aufbau.U_wert_W_m2K,
        'd_T_m': d_T,
        'n_schichten_wirksam': n_wirksam,
        'kappa_m_J_m2K': kappa_m,
        'kappa_m_kJ_m2K': kappa_m / 1000,
        'massenklasse': klasse.value,
        'kappa_knoten_J_m2K': kappa_knoten,
    }


# =============================================================================
# BESTEST KONSTRUKTIONEN
# =============================================================================

def erstelle_bestest_schwerbau_wand() -> BauteilAufbau:
    """
    Erstellt BESTEST Case 900 Schwerbau-Außenwand.
    
    Aufbau von INNEN nach AUSSEN:
    1. Concrete Block (tragend, massiv)
    2. Foam Insulation (Dämmung)
    3. Wood Siding (Bekleidung)
    
    Returns:
        BauteilAufbau mit 3 Schichten, U ≈ 0.51 W/m²K, κ_m ≈ 100 kJ/m²K
    
    Reference:
        ASHRAE 140-2023, Table 5-3
    """
    return BauteilAufbau(
        name="BESTEST Schwerbau-Außenwand (Case 900)",
        schichten=[
            Schicht(
                name="Concrete Block",
                dicke_m=0.100,
                lambda_W_mK=0.510,
                rho_kg_m3=1400,
                c_J_kgK=1000
            ),
            Schicht(
                name="Foam Insulation",
                dicke_m=0.0615,
                lambda_W_mK=0.040,
                rho_kg_m3=10,
                c_J_kgK=1400
            ),
            Schicht(
                name="Wood Siding",
                dicke_m=0.009,
                lambda_W_mK=0.140,
                rho_kg_m3=530,
                c_J_kgK=900
            ),
        ]
    )


def erstelle_bestest_schwerbau_boden() -> BauteilAufbau:
    """
    Erstellt BESTEST Case 900 Schwerbau-Boden (Raised Floor).
    
    Aufbau von INNEN (oben) nach AUSSEN (unten):
    1. Concrete Slab (tragend, massiv)
    2. Insulation (sehr dick, minimale Dichte)
    
    Returns:
        BauteilAufbau mit 2 Schichten, U ≈ 0.04 W/m²K, κ_m ≈ 112 kJ/m²K
    
    Reference:
        ASHRAE 140-2023, Table 5-5
    """
    return BauteilAufbau(
        name="BESTEST Schwerbau-Boden (Case 900)",
        schichten=[
            Schicht(
                name="Concrete Slab",
                dicke_m=0.080,
                lambda_W_mK=1.130,
                rho_kg_m3=1400,
                c_J_kgK=1000
            ),
            Schicht(
                name="Floor Insulation",
                dicke_m=1.007,  # Sehr dick für hohen R-Wert
                lambda_W_mK=0.040,
                rho_kg_m3=10,   # Minimal
                c_J_kgK=1400
            ),
        ]
    )


def erstelle_bestest_leichtbau_wand() -> BauteilAufbau:
    """
    Erstellt BESTEST Case 600 Leichtbau-Außenwand.
    
    Aufbau von INNEN nach AUSSEN:
    1. Plasterboard (Gipskarton)
    2. Fiberglass Insulation (Dämmung)
    3. Wood Siding (Bekleidung)
    
    Returns:
        BauteilAufbau mit 3 Schichten, U ≈ 0.51 W/m²K, κ_m ≈ 9.6 kJ/m²K
    
    Reference:
        ASHRAE 140-2023, Table 5-1
    """
    return BauteilAufbau(
        name="BESTEST Leichtbau-Außenwand (Case 600)",
        schichten=[
            Schicht(
                name="Plasterboard",
                dicke_m=0.012,
                lambda_W_mK=0.160,
                rho_kg_m3=950,
                c_J_kgK=840
            ),
            Schicht(
                name="Fiberglass Insulation",
                dicke_m=0.066,
                lambda_W_mK=0.040,
                rho_kg_m3=12,
                c_J_kgK=840
            ),
            Schicht(
                name="Wood Siding",
                dicke_m=0.009,
                lambda_W_mK=0.140,
                rho_kg_m3=530,
                c_J_kgK=900
            ),
        ]
    )


# =============================================================================
# TEST
# =============================================================================

if __name__ == '__main__':
    print("=" * 70)
    print("ISO 52016-1 / ISO 13786: Wirksame Wärmekapazität κ_m")
    print("=" * 70)
    
    # Test 1: BESTEST Schwerbau-Wand
    print("\n--- BESTEST Schwerbau-Wand (Case 900) ---")
    wand_schwer = erstelle_bestest_schwerbau_wand()
    
    print("\nSchichtaufbau (innen → außen):")
    for i, s in enumerate(wand_schwer.schichten, 1):
        print(f"  {i}. {s.name:20s}: d={s.dicke_m*1000:5.1f}mm, "
              f"λ={s.lambda_W_mK:.3f} W/mK, ρ={s.rho_kg_m3} kg/m³")
        if s.ist_daemmung:
            print(f"     → DÄMMSCHICHT (λ < {LAMBDA_DAEMMUNG_GRENZE} W/mK)")
    
    analyse = analysiere_bauteil(wand_schwer)
    
    print("\nErgebnis:")
    print(f"  Gesamtdicke:      {analyse['dicke_gesamt_m']*1000:.1f} mm")
    print(f"  R-Wert:           {analyse['R_gesamt_m2K_W']:.3f} m²K/W")
    print(f"  U-Wert:           {analyse['U_wert_W_m2K']:.3f} W/m²K")
    print(f"  Wirksame Dicke:   {analyse['d_T_m']*1000:.1f} mm")
    print(f"  Wirksame Schichten: {analyse['n_schichten_wirksam']}")
    print(f"  Massenklasse:     {analyse['massenklasse']}")
    print(f"  κ_m:              {analyse['kappa_m_J_m2K']:.0f} J/m²K")
    print(f"                  = {analyse['kappa_m_kJ_m2K']:.1f} kJ/m²K")
    print(f"  Knotenverteilung: {[f'{k/1000:.1f}' for k in analyse['kappa_knoten_J_m2K']]} kJ/m²K")
    
    # Test 2: BESTEST Schwerbau-Boden
    print("\n--- BESTEST Schwerbau-Boden (Case 900) ---")
    boden_schwer = erstelle_bestest_schwerbau_boden()
    analyse_boden = analysiere_bauteil(boden_schwer)
    
    print(f"  κ_m:              {analyse_boden['kappa_m_J_m2K']:.0f} J/m²K")
    print(f"                  = {analyse_boden['kappa_m_kJ_m2K']:.1f} kJ/m²K")
    print(f"  Massenklasse:     {analyse_boden['massenklasse']}")
    
    # Test 3: BESTEST Leichtbau-Wand
    print("\n--- BESTEST Leichtbau-Wand (Case 600) ---")
    wand_leicht = erstelle_bestest_leichtbau_wand()
    analyse_leicht = analysiere_bauteil(wand_leicht)
    
    print(f"  κ_m:              {analyse_leicht['kappa_m_J_m2K']:.0f} J/m²K")
    print(f"                  = {analyse_leicht['kappa_m_kJ_m2K']:.1f} kJ/m²K")
    print(f"  Massenklasse:     {analyse_leicht['massenklasse']}")
    
    # Vergleich
    print("\n" + "=" * 70)
    print("EINORDNUNG: ISO-13786-Variante (Kappung auf wirksame Dicke)")
    print("=" * 70)
    print("\nDie hier ausgegebenen κ_m-Werte sind die ISO-13786-Variante")
    print("(periodische Eindringtiefe / wirksame Dicke). Projektdefault ist")
    print("die VOLLE Schichtsumme Σρ·c·d — gedeckt durch die normeigenen")
    print("Prüffalltabellen 23/24 der ISO 52016-1 (z. B. Holzboden")
    print("19 500 J/m²K = 0,025·650·1200). Die 13786-Kappung ist als")
    print("dokumentierter Schalter (kappa_13786_kappung) eine Sensitivität,")
    print("kein 'korrekterer' Wert.")
    print("\nSchwerbau-Wand:")
    print(f"  Volle Schichtsumme (Default): siehe Loader (Σρ·c·d)")
    print(f"  ISO-13786-Variante:  {analyse['kappa_m_kJ_m2K']:.1f} kJ/m²K")
    print("\nSchwerbau-Boden:")
    print(f"  ISO-13786-Variante:  {analyse_boden['kappa_m_kJ_m2K']:.1f} kJ/m²K")

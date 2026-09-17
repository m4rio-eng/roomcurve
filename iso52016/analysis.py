# Copyright (c) 2026 Mario Vukadinovic
# SPDX-License-Identifier: AGPL-3.0-only
# Part of the ISO 52016-1 Room Simulator. See LICENSE.
# Commercial licensing available on request.

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Analyse und Auswertung von Simulationsergebnissen
==================================================

Implementiert:
- DIN EN 16798-1: Adaptiver Komfort mit gleitendem Außentemperatur-Mittel
- Übertemperaturgradstunden (feste Schwellen 25-30°C)
- Überschreitungsstunden

Reference:
    DIN EN 16798-1:2022, Anhang B (Adaptives Komfortmodell)
"""

import numpy as np
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple


# ============================================================================
# KONSTANTEN nach DIN EN 16798-1
# ============================================================================

# Exponentieller Gewichtungsfaktor für gleitendes Mittel (Anhang B.2.2)
ALPHA = 0.8

# Koeffizienten für oberen Komfort-Grenzwert (Gleichung B.3)
# θ_max = 0.33 × θ_rm + 18.8 + Δθ
COEFF_A = 0.33
COEFF_B = 18.8

# Kategorie-Offsets Δθ (Tabelle B.3)
KATEGORIE_OFFSET = {
    'I':   2.0,   # Hohe Erwartungen (PPD < 6%)
    'II':  3.0,   # Normale Erwartungen (PPD < 10%)
    'III': 4.0,   # Moderate Erwartungen (PPD < 15%)
}

# Gültigkeitsbereich für θ_rm (10-30°C, Anhang B.2.1)
THETA_RM_MIN = 10.0
THETA_RM_MAX = 30.0


# ============================================================================
# GLEITENDES MITTEL DER AUSSENTEMPERATUR
# ============================================================================

def berechne_tagesmittel(theta_e_stunden: np.ndarray) -> np.ndarray:
    """
    Berechnet Tagesmittelwerte der Außentemperatur.
    
    Args:
        theta_e_stunden: Stündliche Außentemperaturen [°C], Shape (8760,)
    
    Returns:
        Tagesmittelwerte [°C], Shape (365,)
    """
    # Reshape zu (365, 24) und Mittelwert über Stunden
    return theta_e_stunden[:8760].reshape(365, 24).mean(axis=1)


def berechne_gleitendes_mittel(theta_ed: np.ndarray, alpha: float = ALPHA) -> np.ndarray:
    """
    Berechnet exponentiell gewichtetes gleitendes Mittel der Außentemperatur.
    
    Formel nach DIN EN 16798-1, Gleichung B.2:
    θ_rm,n = (1-α) × (θ_ed,n-1 + α×θ_ed,n-2 + α²×θ_ed,n-3 + ... + α^13×θ_ed,n-14)
    
    Args:
        theta_ed: Tagesmittelwerte [°C], Shape (365,)
        alpha: Gewichtungsfaktor (Standard: 0.8)
    
    Returns:
        Gleitendes Mittel θ_rm [°C], Shape (365,)
        
    Note:
        Elegante Lösung mit zyklischem Index statt Array-Erweiterung.
        Für die ersten 14 Tage wird das Vorjahr (Ende des Arrays) verwendet.
    """
    n_tage = len(theta_ed)
    theta_rm = np.zeros(n_tage)
    
    # Gewichte vorberechnen: (1-α) × α^(i-1) für i=1..14
    gewichte = (1 - alpha) * alpha ** np.arange(14)
    
    for tag in range(n_tage):
        # Zyklische Indizes für die letzten 14 Tage (nicht aktueller Tag!)
        # Tag 0 braucht Tage -1..-14, also 364..351
        indizes = [(tag - 1 - i) % n_tage for i in range(14)]
        theta_rm[tag] = np.sum(gewichte * theta_ed[indizes])
    
    return theta_rm


def berechne_theta_rm_stuendlich(theta_e_stunden: np.ndarray) -> np.ndarray:
    """
    Berechnet θ_rm für jede Stunde des Jahres.
    
    Args:
        theta_e_stunden: Stündliche Außentemperaturen [°C], Shape (8760,)
    
    Returns:
        θ_rm für jede Stunde [°C], Shape (8760,)
    """
    # Tagesmittel berechnen
    theta_ed = berechne_tagesmittel(theta_e_stunden)
    
    # Gleitendes Mittel (täglich)
    theta_rm_taeglich = berechne_gleitendes_mittel(theta_ed)
    
    # Auf Stunden erweitern (jeder Tag hat gleichen Wert)
    theta_rm_stuendlich = np.repeat(theta_rm_taeglich, 24)
    
    return theta_rm_stuendlich


# ============================================================================
# KOMFORT-GRENZWERTE
# ============================================================================

def berechne_komfort_grenzwert(theta_rm: float, kategorie: str = 'II') -> Optional[float]:
    """
    Berechnet oberen Komfort-Grenzwert nach DIN EN 16798-1.
    
    Formel: θ_max = 0.33 × θ_rm + 18.8 + Δθ_kategorie
    
    Args:
        theta_rm: Gleitendes Mittel der Außentemperatur [°C]
        kategorie: 'I', 'II', oder 'III'
    
    Returns:
        Oberer Komfort-Grenzwert [°C], oder None wenn außerhalb Gültigkeitsbereich
    """
    # Gültigkeitsbereich prüfen
    if theta_rm < THETA_RM_MIN or theta_rm > THETA_RM_MAX:
        return None
    
    offset = KATEGORIE_OFFSET.get(kategorie, KATEGORIE_OFFSET['II'])
    return COEFF_A * theta_rm + COEFF_B + offset


def berechne_alle_grenzwerte(theta_rm: np.ndarray) -> Dict[str, np.ndarray]:
    """
    Berechnet Komfort-Grenzwerte für alle Kategorien.
    
    Args:
        theta_rm: Array mit θ_rm-Werten [°C]
    
    Returns:
        Dict mit Arrays für jede Kategorie, NaN außerhalb Gültigkeitsbereich
    """
    grenzwerte = {}
    
    for kat, offset in KATEGORIE_OFFSET.items():
        grenz = COEFF_A * theta_rm + COEFF_B + offset
        # Außerhalb Gültigkeitsbereich auf NaN setzen
        maske = (theta_rm < THETA_RM_MIN) | (theta_rm > THETA_RM_MAX)
        grenz[maske] = np.nan
        grenzwerte[kat] = grenz
    
    return grenzwerte


# ============================================================================
# ÜBERTEMPERATUR-AUSWERTUNG
# ============================================================================

@dataclass
class UebertemperaturErgebnis:
    """Ergebnis der Übertemperatur-Auswertung für eine Zone."""
    
    # Feste Schwellen (25-30°C)
    gradstunden_fest: Dict[int, float] = field(default_factory=dict)  # {25: 123.4, 26: 45.6, ...}
    stunden_fest: Dict[int, float] = field(default_factory=dict)      # {25: 50.0, 26: 20.0, ...}
    
    # Adaptive Grenzwerte nach 16798-1
    gradstunden_adaptiv: Dict[str, float] = field(default_factory=dict)  # {'I': 10.0, 'II': 5.0, 'III': 0.0}
    stunden_adaptiv: Dict[str, float] = field(default_factory=dict)
    
    # Maximalwerte
    theta_op_max: float = 0.0
    theta_op_max_stunde: int = 0
    
    def __repr__(self):
        return (f"Übertemperatur(GH26={self.gradstunden_fest.get(26, 0):.1f} Kh, "
                f"GH_KatII={self.gradstunden_adaptiv.get('II', 0):.1f} Kh)")


def berechne_uebertemperatur(
    theta_op: np.ndarray,
    theta_rm: np.ndarray,
    nutzungszeit: Optional[np.ndarray] = None,
    dt: float = 1.0
) -> UebertemperaturErgebnis:
    """
    Wertet Übertemperaturen aus.
    
    Args:
        theta_op: Operative Temperatur [°C], Shape (8760,)
        theta_rm: Gleitendes Mittel Außentemperatur [°C], Shape (8760,)
        nutzungszeit: Maske für Nutzungszeit (True=auswerten), optional
        dt: Zeitschrittweite [h], Standard 1.0
    
    Returns:
        UebertemperaturErgebnis mit allen Auswertungen
    """
    erg = UebertemperaturErgebnis()
    
    # Standard: Alle Stunden auswerten
    if nutzungszeit is None:
        nutzungszeit = np.ones(len(theta_op), dtype=bool)
    
    # Nur Nutzungszeit betrachten
    theta_op_nutz = theta_op[nutzungszeit]
    theta_rm_nutz = theta_rm[nutzungszeit]
    
    # =========================================
    # 1. Feste Schwellen (25-30°C)
    # =========================================
    for schwelle in range(25, 31):
        ueberschreitung = theta_op_nutz > schwelle
        if np.any(ueberschreitung):
            delta_t = theta_op_nutz[ueberschreitung] - schwelle
            erg.gradstunden_fest[schwelle] = float(np.sum(delta_t) * dt)
            erg.stunden_fest[schwelle] = float(np.sum(ueberschreitung) * dt)
        else:
            erg.gradstunden_fest[schwelle] = 0.0
            erg.stunden_fest[schwelle] = 0.0
    
    # =========================================
    # 2. Adaptive Grenzwerte (16798-1)
    # =========================================
    grenzwerte = berechne_alle_grenzwerte(theta_rm_nutz)
    
    for kat in ['I', 'II', 'III']:
        grenz = grenzwerte[kat]
        # Nur auswerten wo Grenzwert gültig (nicht NaN)
        gueltig = ~np.isnan(grenz)
        if np.any(gueltig):
            ueberschreitung = gueltig & (theta_op_nutz > grenz)
            if np.any(ueberschreitung):
                delta_t = theta_op_nutz[ueberschreitung] - grenz[ueberschreitung]
                erg.gradstunden_adaptiv[kat] = float(np.sum(delta_t) * dt)
                erg.stunden_adaptiv[kat] = float(np.sum(ueberschreitung) * dt)
            else:
                erg.gradstunden_adaptiv[kat] = 0.0
                erg.stunden_adaptiv[kat] = 0.0
        else:
            erg.gradstunden_adaptiv[kat] = 0.0
            erg.stunden_adaptiv[kat] = 0.0
    
    # =========================================
    # 3. Maximum-Tracking
    # =========================================
    idx_max = np.argmax(theta_op)
    erg.theta_op_max = float(theta_op[idx_max])
    erg.theta_op_max_stunde = int(idx_max)
    
    return erg


# ============================================================================
# INTEGRATION IN SIMULATOR
# ============================================================================

def erstelle_nutzungszeit_maske(
    nutzung_start: int = 7,
    nutzung_ende: int = 18,
    nur_werktage: bool = False
) -> np.ndarray:
    """
    Erstellt Maske für Nutzungszeit.
    
    Args:
        nutzung_start: Beginn Nutzungszeit (Stunde, 0-23)
        nutzung_ende: Ende Nutzungszeit (Stunde, 0-23)
        nur_werktage: Wenn True, nur Mo-Fr
    
    Returns:
        Boolean-Array (8760,)
    """
    maske = np.zeros(8760, dtype=bool)
    
    for tag in range(365):
        # Wochentag (0=Mo, 6=So) - Jahr beginnt mit Montag (vereinfacht)
        wochentag = tag % 7
        
        if nur_werktage and wochentag >= 5:
            continue
        
        for stunde in range(24):
            if nutzung_start <= stunde < nutzung_ende:
                maske[tag * 24 + stunde] = True
    
    return maske


# ============================================================================
# TEST
# ============================================================================

if __name__ == '__main__':
    print("=" * 60)
    print("Test: Thermischer Komfort nach DIN EN 16798-1")
    print("=" * 60)
    
    # Synthetische Außentemperaturen (Jahresgang)
    stunden = np.arange(8760)
    tage = stunden / 24
    theta_e = 10 + 10 * np.sin(2 * np.pi * (tage - 90) / 365)  # Min ~0°C, Max ~20°C
    theta_e += 5 * np.sin(2 * np.pi * stunden / 24)  # Tagesgang
    
    print("\n1. Außentemperatur:")
    print(f"   Min: {theta_e.min():.1f}°C, Max: {theta_e.max():.1f}°C")
    
    # Gleitendes Mittel berechnen
    theta_rm = berechne_theta_rm_stuendlich(theta_e)
    
    print("\n2. Gleitendes Mittel θ_rm:")
    print(f"   Min: {theta_rm.min():.1f}°C, Max: {theta_rm.max():.1f}°C")
    
    # Grenzwerte
    print("\n3. Komfort-Grenzwerte bei θ_rm=20°C:")
    for kat in ['I', 'II', 'III']:
        grenz = berechne_komfort_grenzwert(20.0, kat)
        print(f"   Kategorie {kat}: {grenz:.1f}°C")
    
    # Simulierte operative Temperatur (mit Überhitzung im Sommer)
    theta_op = 22 + 3 * np.sin(2 * np.pi * (tage - 90) / 365)
    theta_op += 2 * np.sin(2 * np.pi * stunden / 24)
    # Spitzen im Sommer
    sommer = (tage > 150) & (tage < 250)
    theta_op[sommer] += 4
    
    print("\n4. Operative Temperatur (simuliert):")
    print(f"   Min: {theta_op.min():.1f}°C, Max: {theta_op.max():.1f}°C")
    
    # Nutzungszeit 8-18 Uhr
    nutzungszeit = erstelle_nutzungszeit_maske(8, 18)
    
    # Auswertung
    erg = berechne_uebertemperatur(theta_op, theta_rm, nutzungszeit)
    
    print("\n5. Übertemperatur-Auswertung (8-18 Uhr):")
    print(f"   θ_op,max: {erg.theta_op_max:.1f}°C (Stunde {erg.theta_op_max_stunde})")
    print("\n   Feste Schwellen:")
    for schwelle in [25, 26, 27, 28, 29, 30]:
        gh = erg.gradstunden_fest[schwelle]
        n = erg.stunden_fest[schwelle]
        print(f"   {schwelle}°C: {gh:>7.1f} Kh, {n:>5.0f} h")
    
    print("\n   Adaptive Grenzwerte (16798-1):")
    for kat in ['I', 'II', 'III']:
        gh = erg.gradstunden_adaptiv[kat]
        n = erg.stunden_adaptiv[kat]
        print(f"   Kategorie {kat}: {gh:>7.1f} Kh, {n:>5.0f} h")


# =============================================================================
# ENGLISH API (aliases)
# =============================================================================

# Classes
OverheatingResult = UebertemperaturErgebnis

# Functions
calculate_running_mean_temperature = berechne_theta_rm_stuendlich
calculate_overheating = berechne_uebertemperatur
calculate_comfort_limit = berechne_komfort_grenzwert
calculate_all_limits = berechne_alle_grenzwerte
create_occupancy_mask = erstelle_nutzungszeit_maske


# =============================================================================
# DIN 4108-2 EVALUATION
# =============================================================================

@dataclass
class DIN4108Result:
    """Result of DIN 4108-2 evaluation."""
    usage_type: str
    climate_region: str
    reference_temperature: float
    limit_value: float
    overheating_degree_hours: float
    exceedance_hours: float
    max_operative_temperature: float
    max_temperature_hour: int
    requirement_met: bool
    reserve_kh: float
    reserve_percent: float
    
    def __repr__(self):
        status = "✅ PASSED" if self.requirement_met else "❌ FAILED"
        return (f"DIN 4108-2: {status}\n"
                f"  Kh/a: {self.overheating_degree_hours:.0f} (Limit: {self.limit_value:.0f})\n"
                f"  Reserve: {self.reserve_kh:.0f} Kh ({self.reserve_percent:.1f}%)")


def evaluate_din4108_2(theta_op: np.ndarray, profile) -> DIN4108Result:
    """
    Evaluate DIN 4108-2 summer thermal protection.
    
    Args:
        theta_op: Operative temperature [°C], array (8760,)
        profile: DIN4108Profile from profiles module
    
    Returns:
        DIN4108Result with verification status
    """
    theta_ref = profile.reference_temperature
    is_occupied = profile.is_occupied
    limit = profile.limit_value
    
    # Filter to occupied hours
    theta_occupied = theta_op[is_occupied]
    
    # Calculate exceedance
    exceedance = theta_occupied > theta_ref
    if np.any(exceedance):
        delta_t = theta_occupied[exceedance] - theta_ref
        degree_hours = float(np.sum(delta_t))
        exceedance_hours = float(np.sum(exceedance))
    else:
        degree_hours = 0.0
        exceedance_hours = 0.0
    
    # Maximum
    idx_max = int(np.argmax(theta_op))
    max_temp = float(theta_op[idx_max])
    
    # Evaluation
    passed = degree_hours <= limit
    reserve = limit - degree_hours
    reserve_pct = (reserve / limit * 100) if limit > 0 else 0
    
    return DIN4108Result(
        usage_type=profile.usage_type.value,
        climate_region=profile.climate_region.value,
        reference_temperature=theta_ref,
        limit_value=limit,
        overheating_degree_hours=degree_hours,
        exceedance_hours=exceedance_hours,
        max_operative_temperature=max_temp,
        max_temperature_hour=idx_max,
        requirement_met=passed,
        reserve_kh=reserve,
        reserve_percent=reserve_pct,
    )

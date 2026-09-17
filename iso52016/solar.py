# Copyright (c) 2026 Mario Vukadinovic
# SPDX-License-Identifier: AGPL-3.0-only
# Part of the ISO 52016-1 Room Simulator. See LICENSE.
# Commercial licensing available on request.

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ISO 52010-1: Sonnenstand und solare Einstrahlung
=================================================

Berechnung von Sonnenposition und solarer Bestrahlungsstärke auf 
geneigte Flächen nach DIN EN ISO 52010-1:2017.

Dieses Modul kombiniert:
- Teil 1: Sonnenstandsberechnung (Position, Winkel)
- Teil 2: Solare Einstrahlung (Perez-Modell)

Funktionsumfang:
- Sonnendeklination, Zeitgleichung
- Sonnenhöhenwinkel, Sonnenazimut
- Einfallswinkel auf geneigte Flächen
- Direkt-, Diffus- und Reflexionsstrahlung (Perez-Modell)

Referenzen:
    DIN EN ISO 52010-1:2017 - Klimadaten für die Gebäudeenergieberechnung
    Perez et al. (1990) - Modeling daylight availability
"""

import math
import numpy as np
from dataclasses import dataclass
from typing import Tuple, List, Optional


# =============================================================================
# KONSTANTEN
# =============================================================================

# Solarkonstante G_sol;c [W/m²] nach ISO 52010-1, Tabelle 9
# (Tab. 9; ein früherer Wert 1367 war normfremd)
I_SC = 1370.0

# Perez-Modell Konstante K [rad⁻³] nach ISO 52010-1, Tabelle 9
# (verwendet in Gleichung 30)
K_PEREZ = 1.014

# Standard-Bodenalbedo [-] nach ISO 52010-1
RHO_GROUND_DEFAULT = 0.2

# Perez-Helligkeitskoeffizienten nach ISO 52010-1, Tabelle 8
# Format: (ε_min, ε_max, f11, f12, f13, f21, f22, f23)
# Untergrenze Klasse 1 = 1,000: Tabelle 8 druckt für Klasse 1 KEINE
# Untergrenze ("ε < 1,065"); die 1,000 hier ist die analytische Schranke:
# Gl. (30) ε = [(G_d+G_b)/G_d + K·(π·α_sol/180)³] / [1 + K·(π·α_sol/180)³]
# mit (G_d+G_b)/G_d ≥ 1 ⇒ ε ≥ 1 — als Tupelwert ohne Codewirkung
# (Gl. 30 Zwei-Quellen-verifiziert Textlayer+OCR, 07/2026).
# Obergrenze Klasse 8: die
# gedruckte Bedingung "ε < 6,200" ist als Anmerkung im Normtext-Register 52010-1 dokumentiert,
# intendiert und hier umgesetzt ist ε ≥ 6,200.
PEREZ_KOEFFIZIENTEN = {
    1: (1.000, 1.065, -0.008,  0.588, -0.062, -0.060,  0.072, -0.022),  # bedeckt
    2: (1.065, 1.230,  0.130,  0.683, -0.151, -0.019,  0.066, -0.029),
    3: (1.230, 1.500,  0.330,  0.487, -0.221,  0.055, -0.064, -0.026),
    4: (1.500, 1.950,  0.568,  0.187, -0.295,  0.109, -0.152, -0.014),
    5: (1.950, 2.800,  0.873, -0.392, -0.362,  0.226, -0.462,  0.001),
    6: (2.800, 4.500,  1.132, -1.237, -0.412,  0.288, -0.823,  0.056),
    7: (4.500, 6.200,  1.060, -1.600, -0.359,  0.264, -1.127,  0.131),
    8: (6.200, 999.9,  0.678, -0.327, -0.250,  0.156, -1.377,  0.251),  # klar
}


# =============================================================================
# DATENKLASSEN
# =============================================================================

@dataclass
class Standort:
    """
    Geografischer Standort für Sonnenstandsberechnung.
    
    Attributes:
        name: Bezeichnung des Standorts
        breitengrad: Geografische Breite φ [°], positiv = Nord
        laengengrad: Geografische Länge λ [°], positiv = Ost, negativ = West
        zeitzone: Zeitzone relativ zu UTC [h], z.B. -7 für Denver, +1 für MEZ
        hoehe_m: Höhe über Normalnull [m]
    """
    name: str
    breitengrad: float
    laengengrad: float
    zeitzone: float
    hoehe_m: float = 0.0


# Vordefinierte Standorte für BESTEST
DENVER = Standort(
    name="Denver, Colorado (BESTEST)",
    breitengrad=39.76,
    laengengrad=-104.86,
    zeitzone=-7,
    hoehe_m=1609
)


@dataclass
class SonnenstandErgebnis:
    """
    Ergebnis der Sonnenstandsberechnung für einen Zeitpunkt.
    
    Attributes:
        stunde: Stunde des Tages (0-23)
        tag: Tag im Jahr (1-365)
        alpha_sol: Sonnenhöhenwinkel [°], 0 = Horizont, 90 = Zenit
        phi_sol: Sonnenazimut [°], Süd=0, Ost=+90, West=-90
        delta: Sonnendeklination [°]
        omega: Stundenwinkel [°]
        ist_tag: True wenn Sonne über Horizont
    """
    stunde: int
    tag: int
    alpha_sol: float
    phi_sol: float
    delta: float
    omega: float
    ist_tag: bool


@dataclass
class SurfaceIrradiance:
    """
    Solare Bestrahlungsstärke auf geneigte Fläche [W/m²].
    
    Attributes:
        I_dir: Direkte Strahlung (ohne Circumsolar)
        I_dif: Diffuse Himmelsstrahlung (isotrop + Horizontaufhellung)
        I_circum: Circumsolarstrahlung (verhält sich wie Direktstrahlung)
        I_ground: Vom Boden reflektierte Strahlung
        I_tot: Gesamtstrahlung
        I_dir_tot: Direkt + Circumsolar (für Verschattung)
        I_dif_tot: Diffus + Bodenreflexion (für Verschattung)
    """
    I_dir: float
    I_dif: float
    I_circum: float
    I_ground: float
    I_tot: float
    I_dir_tot: float
    I_dif_tot: float


# =============================================================================
# TEIL 1: SONNENSTAND
# =============================================================================

def deg_to_rad(deg: float) -> float:
    """Konvertiert Grad zu Radiant."""
    return deg * math.pi / 180.0


def rad_to_deg(rad: float) -> float:
    """Konvertiert Radiant zu Grad."""
    return rad * 180.0 / math.pi


def berechne_sonnendeklination(n_day: int) -> float:
    """
    Berechnet die Sonnendeklination δ.
    
    Die Deklination ist der Winkel zwischen Sonnenstrahl und Äquatorebene.
    Sie variiert von -23.45° (Wintersonnenwende) bis +23.45° (Sommersonnenwende).
    
    Args:
        n_day: Tag im Jahr (1-365)
    
    Returns:
        Sonnendeklination [°]
    
    Reference:
        ISO 52010-1:2017, Gleichung 1-2
    """
    R_dc = 360.0 / 365.0 * n_day
    R_dc_rad = deg_to_rad(R_dc)
    
    delta = (0.33281 
             - 22.984 * math.cos(R_dc_rad)
             - 0.3499 * math.cos(2 * R_dc_rad)
             - 0.1398 * math.cos(3 * R_dc_rad)
             + 3.7872 * math.sin(R_dc_rad)
             + 0.03205 * math.sin(2 * R_dc_rad)
             + 0.07187 * math.sin(3 * R_dc_rad))
    
    return delta


def berechne_zeitgleichung(n_day: int) -> float:
    """
    Berechnet die Zeitgleichung t_eq.
    
    Die Zeitgleichung korrigiert die Differenz zwischen wahrer und 
    mittlerer Sonnenzeit aufgrund der elliptischen Erdbahn.
    
    Args:
        n_day: Tag im Jahr (1-365)
    
    Returns:
        Zeitgleichung [min]
    
    Reference:
        ISO 52010-1:2017, Gleichungen 3-7
    """
    if n_day < 21:
        t_eq = 2.6 + 0.44 * n_day
    elif n_day < 136:
        t_eq = 5.2 + 9.0 * math.cos(deg_to_rad((n_day - 43) * 0.0357 * 180 / math.pi))
    elif n_day < 241:
        t_eq = 1.4 - 5.0 * math.cos(deg_to_rad((n_day - 135) * 0.0449 * 180 / math.pi))
    elif n_day < 336:
        t_eq = -6.3 - 10.0 * math.cos(deg_to_rad((n_day - 306) * 0.036 * 180 / math.pi))
    else:
        t_eq = 0.45 * (n_day - 359)
    
    return t_eq


def berechne_sonnenzeit(n_hour: float, n_day: int, standort: Standort) -> float:
    """
    Berechnet die wahre Sonnenzeit t_sol.
    
    Die Sonnenzeit berücksichtigt den Längengrad des Standorts und 
    die Zeitgleichung.
    
    Args:
        n_hour: GANZZAHLIGE Tagesstunde nach Norm-Konvention (Stunden-
            abschnitt N = 1..24 für das Intervall (N-1)h..(N)h), Gl. (9).
            NICHT die Stundenmitte übergeben — die halbe Stunde entsteht
            ausschließlich über die Konstante 12,5 in Gl. (10); eine
            Übergabe von z.B. 12,5 würde sie doppelt zählen.
        n_day: Tag im Jahr (1-365)
        standort: Standortdaten
    
    Returns:
        Wahre Sonnenzeit [h]
    
    Reference:
        ISO 52010-1:2017, Gleichungen 8-9; Anmerkung 2 zu Gl. (10)
    """
    t_eq = berechne_zeitgleichung(n_day)
    t_shift = standort.zeitzone - standort.laengengrad / 15.0
    t_sol = n_hour - t_eq / 60.0 - t_shift
    
    return t_sol


def berechne_stundenwinkel(t_sol: float) -> float:
    """
    Berechnet den Sonnenstundenwinkel ω.
    
    Der Stundenwinkel gibt die Position der Sonne relativ zum Meridian an.
    ω = 0° bei Sonnenhöchststand (12:30 Sonnenzeit), ±15° pro Stunde.
    
    Args:
        t_sol: Wahre Sonnenzeit [h]
    
    Returns:
        Stundenwinkel [°], -180 bis +180
    
    Reference:
        ISO 52010-1:2017, Gleichung 10
    """
    omega = (180.0 / 12.0) * (12.5 - t_sol)
    
    while omega > 180:
        omega -= 360
    while omega < -180:
        omega += 360
    
    return omega


def berechne_sonnenhoehe(delta: float, phi_w: float, omega: float) -> float:
    """
    Berechnet den Sonnenhöhenwinkel α_sol.
    
    Der Höhenwinkel ist der Winkel zwischen Sonnenstrahl und Horizont.
    α = 0° am Horizont, α = 90° im Zenit.
    
    Args:
        delta: Sonnendeklination [°]
        phi_w: Geografische Breite [°]
        omega: Stundenwinkel [°]
    
    Returns:
        Sonnenhöhenwinkel [°], 0 wenn unter Horizont
    
    Reference:
        ISO 52010-1:2017, Gleichung 11
    """
    delta_rad = deg_to_rad(delta)
    phi_rad = deg_to_rad(phi_w)
    omega_rad = deg_to_rad(omega)
    
    sin_alpha = (math.sin(delta_rad) * math.sin(phi_rad) 
                 + math.cos(delta_rad) * math.cos(phi_rad) * math.cos(omega_rad))
    
    sin_alpha = max(-1.0, min(1.0, sin_alpha))
    alpha_sol = rad_to_deg(math.asin(sin_alpha))
    
    if alpha_sol < 0.0001:
        alpha_sol = 0.0
    
    return alpha_sol


def berechne_sonnenazimut(delta: float, phi_w: float, omega: float, alpha_sol: float) -> float:
    """
    Berechnet den Sonnenazimutwinkel φ_sol.
    
    Konvention nach ISO 52010-1:
    - Süd = 0°
    - Ost = +90° (Vormittag)
    - West = -90° (Nachmittag)
    - Nord = ±180°
    
    Args:
        delta: Sonnendeklination [°]
        phi_w: Geografische Breite [°]
        omega: Stundenwinkel [°]
        alpha_sol: Sonnenhöhenwinkel [°]
    
    Returns:
        Sonnenazimut [°], -180 bis +180
    
    Reference:
        ISO 52010-1:2017, Gleichungen 13-16 (atan2-Formulierung; für
        alpha_sol > 0 mathematisch äquivalent zur Norm-Fallunterscheidung,
        numerische Äquivalenznachweise 07/2026: max. 1,4e-11 bzw.
        4,4e-6 Grad. In Stunden mit geklemmter
        Sonnenhöhe (Gl. 11: wahre Höhe < 0 -> alpha = 0) ist die
        Äquivalenz NICHT gegeben; Wirkung vernachlässigbar)
    """
    # Normfremdes Gate "alpha_sol <= 0.5 -> 0.0" entfernt;
    # Gl. (13)-(16) sind für jede Sonnenhöhe auswertbar (Nenner cos(alpha)
    # ist in Horizontnähe ~1). Die [-1,1]-Clamps unten sind reiner
    # Gleitkomma-Schutz (analytisch im Bereich; kritisch nur der Zenit).
    delta_rad = deg_to_rad(delta)
    phi_rad = deg_to_rad(phi_w)
    alpha_rad = deg_to_rad(alpha_sol)
    
    sin_phi_sol = math.cos(delta_rad) * math.sin(deg_to_rad(omega)) / math.cos(alpha_rad)
    sin_phi_sol = max(-1.0, min(1.0, sin_phi_sol))
    
    cos_phi_sol = ((math.sin(alpha_rad) * math.sin(phi_rad) - math.sin(delta_rad)) / 
                   (math.cos(alpha_rad) * math.cos(phi_rad)))
    cos_phi_sol = max(-1.0, min(1.0, cos_phi_sol))
    
    phi_sol = rad_to_deg(math.atan2(sin_phi_sol, cos_phi_sol))
    
    return phi_sol


def berechne_einfallswinkel(alpha_sol: float, phi_sol: float, 
                            beta: float, gamma: float) -> float:
    """
    Berechnet den solaren Einfallswinkel θ auf eine geneigte Fläche.
    
    Der Einfallswinkel ist der Winkel zwischen Sonnenstrahl und 
    Flächennormale. θ = 0° bei senkrechtem Einfall.
    
    Args:
        alpha_sol: Sonnenhöhenwinkel [°]
        phi_sol: Sonnenazimut [°], ISO-Konvention (Süd=0)
        beta: Flächenneigung [°], 0 = horizontal, 90 = vertikal
        gamma: Flächenazimut [°], ISO-Konvention (Süd=0, Ost=+90, West=-90)
    
    Returns:
        Einfallswinkel [°], 0-180
    
    Reference:
        ISO 52010-1:2017, Gleichung 17 (kompakte sphärische Form; für
        alpha_sol > 0 mathematisch äquivalent zur 5-Term-Formel der Norm,
        numerische Äquivalenznachweise 07/2026: max. 1,7e-12 bzw.
        3,6e-12 Grad. In Stunden mit geklemmter
        Sonnenhöhe (Gl. 11: wahre Höhe < 0 -> alpha = 0) weicht die
        Kompaktform von der wörtlichen Gl. 17 ab, die δ, φ_w, ω direkt
        verwendet und von der Klemme unberührt bleibt;
        betroffen nur die a=max(0,cosθ)-Zuordnung des Zirkumsolaranteils
        bei DHI > 0 unter Horizont, Jahreswirkung vernachlässigbar)
    """
    # Normfremder Kurzschluss "alpha_sol <= 0 -> 90.0"
    # entfernt — bei alpha = 0 kann cos(theta) > 0 sein (steile Flächen),
    # Gl. (17) ist uneingeschränkt auswertbar.
    alpha_rad = deg_to_rad(alpha_sol)
    beta_rad = deg_to_rad(beta)
    delta_gamma_rad = deg_to_rad(phi_sol - gamma)
    
    cos_theta = (math.sin(alpha_rad) * math.cos(beta_rad) 
                 + math.cos(alpha_rad) * math.sin(beta_rad) * math.cos(delta_gamma_rad))
    
    # [-1,1]-Clamp: reiner Gleitkomma-Schutz vor acos-Domänenfehler.
    # Vorher wurde auf [0,1] gekappt (theta <= 90 erzwungen); normexakt kann
    # theta > 90 sein — Gl. (26)/(28) kappen cos(theta) < 0 selbst auf 0.
    cos_theta = max(-1.0, min(1.0, cos_theta))
    theta = rad_to_deg(math.acos(cos_theta))
    
    return theta


def berechne_sonnenstand(stunde: int, tag: int, standort: Standort) -> SonnenstandErgebnis:
    """
    Berechnet den kompletten Sonnenstand für einen Zeitpunkt.
    
    Diese Funktion kombiniert alle Einzelberechnungen und liefert
    den vollständigen Sonnenstand für die Stundenmitte.
    
    Args:
        stunde: Stunde des Tages (0-23)
        tag: Tag im Jahr (1-365)
        standort: Standortdaten
    
    Returns:
        SonnenstandErgebnis mit allen Winkeln
    
    Example:
        >>> erg = berechne_sonnenstand(12, 172, DENVER)
        >>> print(f"Sonnenhöhe: {erg.alpha_sol:.1f}°")
        Sonnenhöhe: 73.5°
    """
    # ISO 52010-1 Gl. (9): t_sol aus der GANZZAHLIGEN Tagesstunde n_hour;
    # die Stundenmitte entsteht erst in Gl. (10) durch die Konstante 12,5.
    # Aufrufkonvention hier: 'stunde' ist 0-basiert (0..23) -> n_hour = stunde+1.
    # (Vorher stunde+0,5: wertete den Stunden-ANFANG aus, ~0,5 h zu frueh.)
    n_hour = stunde + 1
    
    delta = berechne_sonnendeklination(tag)
    t_sol = berechne_sonnenzeit(n_hour, tag, standort)
    omega = berechne_stundenwinkel(t_sol)
    alpha_sol = berechne_sonnenhoehe(delta, standort.breitengrad, omega)
    phi_sol = berechne_sonnenazimut(delta, standort.breitengrad, omega, alpha_sol)
    
    return SonnenstandErgebnis(
        stunde=stunde,
        tag=tag,
        alpha_sol=alpha_sol,
        phi_sol=phi_sol,
        delta=delta,
        omega=omega,
        ist_tag=(alpha_sol > 0)
    )


def berechne_jahres_sonnenstand(standort: Standort) -> List[SonnenstandErgebnis]:
    """
    Berechnet den Sonnenstand für alle 8760 Stunden eines Jahres.
    
    Args:
        standort: Standortdaten
    
    Returns:
        Liste mit 8760 SonnenstandErgebnis-Objekten
    """
    ergebnisse = []
    for tag in range(1, 366):
        for stunde in range(24):
            erg = berechne_sonnenstand(stunde, tag, standort)
            ergebnisse.append(erg)
    return ergebnisse


# =============================================================================
# AZIMUT-KONVERTIERUNG
# =============================================================================

def azimut_iso_zu_bestest(gamma_iso: float) -> float:
    """
    Konvertiert ISO-Azimut zu BESTEST-Konvention.
    
    ISO:     Süd=0, Ost=+90, West=-90, Nord=±180
    BESTEST: Nord=0, Ost=90, Süd=180, West=270
    
    Args:
        gamma_iso: Azimut in ISO-Konvention [°]
    
    Returns:
        Azimut in BESTEST-Konvention [°]
    """
    return (180 - gamma_iso) % 360


def azimut_bestest_zu_iso(gamma_bestest: float) -> float:
    """
    Konvertiert BESTEST-Azimut zu ISO-Konvention.
    
    BESTEST: Nord=0, Ost=90, Süd=180, West=270
    ISO:     Süd=0, Ost=+90, West=-90, Nord=±180
    
    Args:
        gamma_bestest: Azimut in BESTEST-Konvention [°]
    
    Returns:
        Azimut in ISO-Konvention [°]
    """
    gamma_iso = 180 - gamma_bestest
    if gamma_iso > 180:
        gamma_iso -= 360
    return gamma_iso


# =============================================================================
# TEIL 2: SOLARE EINSTRAHLUNG (PEREZ-MODELL)
# =============================================================================

def berechne_extraterrestrische_strahlung(n_day: int) -> float:
    """
    Berechnet die extraterrestrische Bestrahlungsstärke I_ext.
    
    Die extraterrestrische Strahlung variiert mit dem Abstand 
    Erde-Sonne im Jahresverlauf um ±3.3%.
    
    Args:
        n_day: Tag im Jahr (1-365)
    
    Returns:
        Extraterrestrische Bestrahlungsstärke [W/m²]
    
    Reference:
        ISO 52010-1:2017, Gleichung 27
    """
    angle = math.radians(360.0 * n_day / 365.0)
    I_ext = I_SC * (1.0 + 0.033 * math.cos(angle))
    return I_ext


def berechne_luftmasse(alpha_sol_deg: float) -> float:
    """
    Berechnet die relative optische Luftmasse m.
    
    Die Luftmasse beschreibt die Weglänge der Strahlung durch die 
    Atmosphäre relativ zum Zenitweg. m = 1 im Zenit.
    
    Args:
        alpha_sol_deg: Sonnenhöhenwinkel [°] (nach Gl. 11 stets >= 0)
    
    Returns:
        Relative Luftmasse [-]
    
    Reference:
        ISO 52010-1:2017, Gleichungen 20 und 21:
        alpha_sol >= 10:  m = 1 / sin(alpha_sol)                       (Gl. 20)
        alpha_sol < 10:   m = 1 / [sin(alpha_sol)
                              + 0,15 * (alpha_sol + 3,885)^(-1,253)]   (Gl. 21)
    
    Hinweis: Eine frühere Fassung nutzte Kasten & Young (1989) mit
    min(m, 40) und Nachtwert 40 — alles normfremd. Gl. 21 ist bei
    alpha = 0 endlich (m ≈ 36,5), Guards sind nicht erforderlich.
    """
    if alpha_sol_deg >= 10.0:
        return 1.0 / math.sin(math.radians(alpha_sol_deg))
    
    return 1.0 / (math.sin(math.radians(alpha_sol_deg)) 
                  + 0.15 * (alpha_sol_deg + 3.885) ** (-1.253))


def berechne_klarheitsparameter(G_sol_b: float, G_sol_d: float, 
                                 alpha_sol_deg: float) -> float:
    """
    Berechnet den Klarheitsparameter ε (epsilon).
    
    Der Klarheitsparameter klassifiziert den Himmelszustand:
    - ε ≈ 1: Bedeckter Himmel
    - ε > 6: Klarer Himmel
    
    Args:
        G_sol_b: Direkte Normalstrahlung DNI [W/m²]
        G_sol_d: Diffuse Horizontalstrahlung DHI [W/m²]
        alpha_sol_deg: Sonnenhöhenwinkel [°]
    
    Returns:
        Klarheitsparameter ε [-]
    
    Reference:
        ISO 52010-1:2017, Gleichung 30; Sonderfall wörtlich:
        "wenn G_sol;d = 0, ε = 999"
    """
    # Bedingung exakt G_d = 0 (Norm) statt Schwelle <= 0,1.
    if G_sol_d == 0.0:
        return 999.0
    
    alpha_rad = math.radians(alpha_sol_deg)
    k_term = K_PEREZ * (alpha_rad ** 3)
    
    numerator = (G_sol_d + G_sol_b) / G_sol_d + k_term
    denominator = 1.0 + k_term
    epsilon = numerator / denominator
    
    return epsilon


def berechne_helligkeitsparameter(G_sol_d: float, alpha_sol_deg: float,
                                   n_day: int) -> float:
    """
    Berechnet den Helligkeitsparameter Δ (Delta).
    
    Der Helligkeitsparameter beschreibt die atmosphärische Trübung
    und beeinflusst die anisotrope Verteilung der Diffusstrahlung.
    
    Args:
        G_sol_d: Diffuse Horizontalstrahlung DHI [W/m²]
        alpha_sol_deg: Sonnenhöhenwinkel [°]
        n_day: Tag im Jahr (1-365)
    
    Returns:
        Helligkeitsparameter Δ [-]
    
    Reference:
        ISO 52010-1:2017, Gleichung 31 (ohne Bedingungen)
    """
    # Normfremde Guards (G_d <= 0,1 -> 0; alpha <= 0 -> 0) entfernt —
    # Gl. (31) ist bedingungsfrei; bei G_d = 0 wird Δ von selbst 0,
    # m ist per Gl. (21) auch bei alpha = 0 endlich.
    m = berechne_luftmasse(alpha_sol_deg)
    I_ext = berechne_extraterrestrische_strahlung(n_day)
    delta = m * G_sol_d / I_ext
    
    return delta


def waehle_perez_koeffizienten(epsilon: float) -> Tuple[float, float, float, 
                                                         float, float, float]:
    """
    Wählt die Perez-Koeffizienten basierend auf dem Klarheitsparameter.
    
    Die Koeffizienten f11-f23 wurden empirisch für 8 Himmelszustände
    bestimmt und beschreiben die Verteilung der Diffusstrahlung.
    
    Args:
        epsilon: Klarheitsparameter ε
    
    Returns:
        Tuple (f11, f12, f13, f21, f22, f23)
    
    Reference:
        ISO 52010-1:2017, Tabelle 8
    """
    # Z1: Untergrenze Klasse 1 = 1,000 (Tabelle 8); ε >= 1 gilt analytisch.
    # Schutz gegen Gleitkomma-Unterschreitung: knapp unter 1,000 -> Klasse 1
    # (vorher fiel alles Unzugeordnete auf Klasse 8 "klar" — falsche Richtung).
    if epsilon < PEREZ_KOEFFIZIENTEN[1][1]:
        return PEREZ_KOEFFIZIENTEN[1][2:8]
    
    for idx, (eps_min, eps_max, f11, f12, f13, f21, f22, f23) in PEREZ_KOEFFIZIENTEN.items():
        if eps_min <= epsilon < eps_max:
            return f11, f12, f13, f21, f22, f23
    
    # ε >= 6,200 (inkl. Sonderwert 999): Klasse 8 "klar" — intendierte
    # Lesart der Tabelle 8 (Anmerkung N2 im Normtext-Register, s. Konstantendefinition).
    return PEREZ_KOEFFIZIENTEN[8][2:8]


def berechne_F1_F2(epsilon: float, delta: float, 
                   theta_z_deg: float) -> Tuple[float, float]:
    """
    Berechnet die Perez-Koeffizienten F1 und F2.
    
    F1 beschreibt den circumsolaren Anteil (Aufhellung um die Sonne).
    F2 beschreibt die Horizontaufhellung.
    
    Args:
        epsilon: Klarheitsparameter
        delta: Helligkeitsparameter
        theta_z_deg: Sonnenzenitwinkel [°]
    
    Returns:
        Tuple (F1, F2)
    
    Reference:
        ISO 52010-1:2017, Gleichungen 32-33
    """
    f11, f12, f13, f21, f22, f23 = waehle_perez_koeffizienten(epsilon)
    theta_z_rad = math.radians(theta_z_deg)
    
    F1 = f11 + f12 * delta + f13 * theta_z_rad
    F1 = max(0.0, F1)
    
    F2 = f21 + f22 * delta + f23 * theta_z_rad
    
    return F1, F2


def berechne_diffusstrahlung_geneigt(G_sol_d: float, F1: float, F2: float,
                                      a: float, b: float, 
                                      beta_deg: float) -> Tuple[float, float]:
    """
    Berechnet die diffuse Himmelsstrahlung auf geneigte Fläche.
    
    Die Diffusstrahlung setzt sich zusammen aus:
    - Isotroper Anteil (gleichmäßig vom Himmel)
    - Circumsolarstrahlung (Aufhellung um Sonne)
    - Horizontaufhellung (Streuung am Horizont)
    
    Args:
        G_sol_d: Diffuse Horizontalstrahlung DHI [W/m²]
        F1: Circumsolarer Koeffizient
        F2: Horizontaler Koeffizient
        a: cos(θ) für geneigte Fläche
        b: cos(θ_z) begrenzt
        beta_deg: Flächenneigung [°]
    
    Returns:
        Tuple (I_dif, I_circum) [W/m²]
    
    Reference:
        ISO 52010-1:2017, Gleichungen 34 und 36.
        ACHTUNG Größenzuordnung: Der Rückgabewert I_dif ist NICHT
        I_dif nach Gl. (34), sondern dessen Isotrop- + Horizontanteil
        OHNE den zirkumsolaren Term F1*a/b; dieser wird separat als
        I_circum (Gl. 36) zurückgegeben. Die Summengrößen der Gl. (37)-(39)
        ergeben sich in der Hauptfunktion algebraisch identisch zur Norm:
        I_dif_tot = (Code-I_dif) + I_ground = Gl.-34-I_dif - I_circum
        + I_dif;grnd = Gl. (38).
    """
    # Normfremde Schwelle G_d <= 0,1 -> (0, 0) entfernt;
    # alle Terme skalieren mit G_d, bei G_d = 0 werden sie von selbst 0.
    beta_rad = math.radians(beta_deg)
    F_sky = (1.0 + math.cos(beta_rad)) / 2.0
    
    # b >= cos(85°) ≈ 0,0872 per Gl. (29) — ein Divisionsschutz ist
    # nicht erforderlich (der frühere b>0,001-Zweig war toter Code).
    I_circum = G_sol_d * F1 * a / b
    
    I_iso = G_sol_d * (1.0 - F1) * F_sky
    I_horiz = G_sol_d * F2 * math.sin(beta_rad)
    # Kappung max(0, I_dif) entfernt — Gl. (34) kappt nicht;
    # ein negativer Horizontterm (F2 < 0 möglich) darf das Ergebnis
    # rechnerisch mindern, Gl. (38) verrechnet den Wert weiter.
    I_dif = I_iso + I_horiz
    
    return I_dif, I_circum


def berechne_bodenreflexion(G_sol_b: float, G_sol_d: float,
                             alpha_sol_deg: float, beta_deg: float,
                             rho_ground: float = RHO_GROUND_DEFAULT) -> float:
    """
    Berechnet die vom Boden reflektierte Strahlung.
    
    Der Boden reflektiert einen Teil der auftreffenden Globalstrahlung
    isotrop. Der Anteil hängt von der Bodenalbedo ab (0.2 = Gras).
    
    Args:
        G_sol_b: Direkte Normalstrahlung DNI [W/m²]
        G_sol_d: Diffuse Horizontalstrahlung DHI [W/m²]
        alpha_sol_deg: Sonnenhöhenwinkel [°]
        beta_deg: Flächenneigung [°]
        rho_ground: Bodenalbedo [-], Standard 0.2
    
    Returns:
        Bodenreflexion [W/m²]
    
    Reference:
        ISO 52010-1:2017, Gleichung 35 (ohne Bedingungen)
    """
    # Gl. (11) garantiert alpha_sol >= 0 (nachts exakt 0, dann sin = 0) —
    # die frühere Fallunterscheidung und die max(0,·)-Kappung waren
    # wirkungslos und sind entfernt.
    beta_rad = math.radians(beta_deg)
    alpha_rad = math.radians(alpha_sol_deg)
    
    G_hor = G_sol_d + G_sol_b * math.sin(alpha_rad)
    F_ground = (1.0 - math.cos(beta_rad)) / 2.0
    
    return G_hor * rho_ground * F_ground


def berechne_direktstrahlung_geneigt(G_sol_b: float, 
                                      theta_sol_ic_deg: float) -> float:
    """
    Berechnet die Direktstrahlung auf geneigte Fläche.
    
    Die Direktstrahlung wird mit dem Kosinus des Einfallswinkels
    auf die Flächennormale projiziert.
    
    Args:
        G_sol_b: Direkte Normalstrahlung DNI [W/m²]
        theta_sol_ic_deg: Einfallswinkel [°]
    
    Returns:
        Direktstrahlung auf Fläche [W/m²]
    """
    if theta_sol_ic_deg >= 90.0 or G_sol_b <= 0:
        return 0.0
    
    cos_theta = math.cos(math.radians(theta_sol_ic_deg))
    I_dir = G_sol_b * cos_theta
    
    return max(0.0, I_dir)


def berechne_strahlung_geneigte_flaeche(
    G_sol_b: float,
    G_sol_d: float,
    alpha_sol_deg: float,
    gamma_sol_deg: float,
    beta_deg: float,
    gamma_surf_deg: float,
    n_day: int,
    rho_ground: float = RHO_GROUND_DEFAULT
) -> SurfaceIrradiance:
    """
    Berechnet die solare Bestrahlungsstärke auf eine geneigte Fläche.
    
    Diese Hauptfunktion implementiert das vereinfachte Perez-Modell
    nach ISO 52010-1 und berechnet alle Strahlungskomponenten.
    
    Args:
        G_sol_b: Direkte Normalstrahlung DNI [W/m²]
        G_sol_d: Diffuse Horizontalstrahlung DHI [W/m²]
        alpha_sol_deg: Sonnenhöhenwinkel [°]
        gamma_sol_deg: Sonnenazimut [°], ISO-Konvention (Süd=0)
        beta_deg: Flächenneigung [°], 0=horizontal, 90=vertikal
        gamma_surf_deg: Flächenazimut [°], ISO-Konvention (Süd=0)
        n_day: Tag im Jahr (1-365)
        rho_ground: Bodenalbedo [-], Standard 0.2
    
    Returns:
        SurfaceIrradiance mit allen Strahlungskomponenten
    
    Example:
        >>> result = berechne_strahlung_geneigte_flaeche(
        ...     G_sol_b=800, G_sol_d=150, alpha_sol_deg=60,
        ...     gamma_sol_deg=0, beta_deg=90, gamma_surf_deg=0, n_day=172)
        >>> print(f"Gesamtstrahlung: {result.I_tot:.0f} W/m²")
    
    Reference:
        DIN EN ISO 52010-1:2017, Abschnitt 6.4, Gleichungen 26-39
        (Gl. 22-25 aus 6.4.2 nicht einschlägig: DNI/DHI sind Eingaben)
    """
    # Normfremdes Gate "alpha_sol <= 0 -> alles 0" entfernt.
    # Die Norm kennt keine Tagbedingung: Gl. (11) liefert nachts alpha = 0,
    # damit sind Gl. (26)-(39) uneingeschränkt auswertbar. Insbesondere
    # bleiben in Auf-/Untergangsstunden (Stundenmitte alpha = 0) vorhandene
    # G_d/G_b-Werte wirksam (Diffus-, Boden-, ggf. Direktanteil auf steilen
    # Flächen) statt verworfen zu werden. Bei G_d = G_b = 0 (echte Nacht)
    # werden alle Komponenten von selbst 0.
    theta_sol_ic = berechne_einfallswinkel(alpha_sol_deg, gamma_sol_deg, 
                                            beta_deg, gamma_surf_deg)
    theta_z_deg = 90.0 - alpha_sol_deg
    
    a = max(0.0, math.cos(math.radians(theta_sol_ic)))
    cos_85 = math.cos(math.radians(85.0))
    b = max(cos_85, math.cos(math.radians(theta_z_deg)))
    
    epsilon = berechne_klarheitsparameter(G_sol_b, G_sol_d, alpha_sol_deg)
    delta = berechne_helligkeitsparameter(G_sol_d, alpha_sol_deg, n_day)
    F1, F2 = berechne_F1_F2(epsilon, delta, theta_z_deg)
    
    I_dir = berechne_direktstrahlung_geneigt(G_sol_b, theta_sol_ic)
    I_dif, I_circum = berechne_diffusstrahlung_geneigt(G_sol_d, F1, F2, a, b, beta_deg)
    I_ground = berechne_bodenreflexion(G_sol_b, G_sol_d, alpha_sol_deg, beta_deg, rho_ground)
    
    I_dir_tot = I_dir + I_circum
    I_dif_tot = I_dif + I_ground
    I_tot = I_dir_tot + I_dif_tot
    
    return SurfaceIrradiance(
        I_dir=I_dir,
        I_dif=I_dif,
        I_circum=I_circum,
        I_ground=I_ground,
        I_tot=I_tot,
        I_dir_tot=I_dir_tot,
        I_dif_tot=I_dif_tot
    )


def berechne_jahresstrahlung(
    DNI: np.ndarray,
    DHI: np.ndarray,
    alpha_sol: np.ndarray,
    gamma_sol: np.ndarray,
    beta_deg: float,
    gamma_surf_deg: float,
    rho_ground: float = RHO_GROUND_DEFAULT
) -> dict:
    """
    Berechnet die Jahresstrahlung auf eine geneigte Fläche.
    
    Wendet berechne_strahlung_geneigte_flaeche auf alle 8760 Stunden an.
    
    Args:
        DNI: Direkte Normalstrahlung [W/m²], Array mit 8760 Werten
        DHI: Diffuse Horizontalstrahlung [W/m²], Array mit 8760 Werten
        alpha_sol: Sonnenhöhe [°], Array mit 8760 Werten
        gamma_sol: Sonnenazimut [°], Array mit 8760 Werten (ISO-Konvention)
        beta_deg: Flächenneigung [°]
        gamma_surf_deg: Flächenazimut [°] (ISO-Konvention)
        rho_ground: Bodenalbedo [-]
    
    Returns:
        Dictionary mit Arrays: I_dir, I_dif, I_circum, I_ground, I_tot, 
        I_dir_tot, I_dif_tot (je 8760 Werte)
    """
    n = len(DNI)
    
    I_dir = np.zeros(n)
    I_dif = np.zeros(n)
    I_circum = np.zeros(n)
    I_ground = np.zeros(n)
    I_tot = np.zeros(n)
    I_dir_tot = np.zeros(n)
    I_dif_tot = np.zeros(n)
    
    for h in range(n):
        n_day = h // 24 + 1
        
        result = berechne_strahlung_geneigte_flaeche(
            G_sol_b=DNI[h],
            G_sol_d=DHI[h],
            alpha_sol_deg=alpha_sol[h],
            gamma_sol_deg=gamma_sol[h],
            beta_deg=beta_deg,
            gamma_surf_deg=gamma_surf_deg,
            n_day=n_day,
            rho_ground=rho_ground
        )
        
        I_dir[h] = result.I_dir
        I_dif[h] = result.I_dif
        I_circum[h] = result.I_circum
        I_ground[h] = result.I_ground
        I_tot[h] = result.I_tot
        I_dir_tot[h] = result.I_dir_tot
        I_dif_tot[h] = result.I_dif_tot
    
    return {
        'I_dir': I_dir,
        'I_dif': I_dif,
        'I_circum': I_circum,
        'I_ground': I_ground,
        'I_tot': I_tot,
        'I_dir_tot': I_dir_tot,
        'I_dif_tot': I_dif_tot
    }

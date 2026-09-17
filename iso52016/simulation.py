# Copyright (c) 2026 Mario Vukadinovic
# SPDX-License-Identifier: AGPL-3.0-only
# Part of the ISO 52016-1 Room Simulator. See LICENSE.
# Commercial licensing available on request.

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ISO 52016-1 Thermische Gebäudesimulation (Normkonform)
=====================================================================
Stündliches Berechnungsverfahren nach DIN EN ISO 52016-1:2018-04

- Wärmebrücken (H_tr;tb) nach Gleichung 38 implementiert
- Himmelsstrahlung nach 6.5.13.3 mit F_sky und Emissionsgrad
- Erdreichkopplung nach ISO 13370 (monatliche Variation)
- Verschattung erweitert (Direkt/Diffus-Trennung)
- Mehrzonenventilation vorbereitet (Anhang D)

Referenzen:
- DIN EN ISO 52016-1:2018-04
- DIN EN ISO 13789:2017 (Wärmeübergangskoeffizienten)
- DIN EN ISO 13370:2018 (Erdreich)
- ASHRAE Standard 140 (BESTEST)
"""

import json
import warnings
import numpy as np
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Dict, List, Tuple, Any
from datetime import datetime
import csv
import math

# Internal imports
from .solar import berechne_sonnenstand, DENVER, Standort
from .analysis import berechne_theta_rm_stuendlich, berechne_uebertemperatur
# Climate (now includes loaders)
from .climate import ClimateData, load_climate, ergaenze_orientierung
from .erdreich import (BODEN_KATEGORIE_DEFAULT, berechne_erdreich_parameter,
                       berechne_theta_vi_monate, theta_vi_fallback_sinus)


# =============================================================================
# NORMKONFORME STÜNDLICHE VERSCHATTUNGSBERECHNUNG (ISO 52016-1 Anhang F)
# =============================================================================

def berechne_F_sh_horizont_stuendlich(stunde, tag, standort,
                                      horizont_winkel_deg: float) -> float:
    """
    Horizontverschattung des Direktanteils (Fernhindernis-Grenzfall von Gl. F.10).

    Grenzfall "fernes Hindernis" von Gl. (F.10), ISO 52016-1 Anhang F:
    h_obst = max(0; H_obst − H_0 − L·tan α_sol). Für ein Hindernis in
    großem Abstand L bei festem Horizontwinkel α_hor = arctan((H_obst −
    H_0)/L) wird der Übergang scharf: α_sol ≤ α_hor ⇒ Schattenhöhe
    übersteigt jede Fassadenhöhe (voll verschattet, Kappung Gl. F.16),
    α_sol > α_hor ⇒ kein Schatten. Ein Segment über das Sichtfeld der
    Fassade (Norm verlangt n_segm ≥ 1). Diffusanteil bleibt nach
    Anhang-F-Verfahren 1 unverschattet; die langwellige F_sky-Wirkung
    des Horizonts ist separat in _berechne_F_sky umgesetzt.

    Returns:
        0,0 (Direktanteil blockiert) oder 1,0 (frei).
    """
    if horizont_winkel_deg <= 0:
        return 1.0
    erg = berechne_sonnenstand(stunde, tag, standort)
    if erg.alpha_sol <= 0:
        return 1.0  # Nacht: kein Direktanteil vorhanden
    return 0.0 if erg.alpha_sol <= horizont_winkel_deg else 1.0


def berechne_F_sh_ueberhang_stuendlich(
    stunde: int, tag: int, standort: Standort,
    azimut_iso: float, H_fenster: float, 
    D_ovh: float, L_ovh: float
) -> float:
    """
    Berechnet F_sh_dir für einen Überhang zu einer bestimmten Stunde.
    
    Normkonform nach ISO 52016-1 Anhang F - STÜNDLICH berechnet!
    
    Args:
        stunde: Stunde des Tages (0-23)
        tag: Tag im Jahr (1-365)
        standort: Standortdaten
        azimut_iso: Flächen-Azimut in ISO-Konvention (Süd=0°)
        H_fenster: Fensterhöhe [m]
        D_ovh: Überhangtiefe [m]
        L_ovh: Abstand Überhang zu Fensteroberkante [m]
    
    Returns:
        F_sh_dir für diese Stunde (0=voll verschattet, 1=unverschattet)
    """
    if D_ovh <= 0:
        return 1.0  # Kein Überhang
    
    erg = berechne_sonnenstand(stunde, tag, standort)
    
    if erg.alpha_sol <= 0:
        return 1.0  # Nacht
    
    # Winkel zwischen Sonne und Flächennormale
    delta_phi = abs(erg.phi_sol - azimut_iso)
    if delta_phi > 180:
        delta_phi = 360 - delta_phi
    
    if delta_phi >= 90:
        return 1.0  # Sonne von hinten/Seite
    
    alpha_rad = math.radians(erg.alpha_sol)
    cos_delta = math.cos(math.radians(delta_phi))

    # Grenzfallabsicherung: Bei streifendem Einfall (Δφ → 90°) divergiert Gl. (F.4)
    # (h_schatten → ∞), was physikalisch VOLLE Verschattung bedeutet —
    # die Kappung auf die Fensterhöhe unten bildet diesen Grenzwert
    # korrekt ab. Der Nenner wird daher nur numerisch abgesichert
    # (kein Guard mehr, der fälschlich 1,0 = „unverschattet" lieferte).
    cos_delta = max(cos_delta, 1e-9)

    # Schattenlänge auf der Wand (ISO 52016-1 Anhang F)
    h_schatten = D_ovh * math.tan(alpha_rad) / cos_delta
    
    # Wie viel davon trifft das Fenster?
    schatten_auf_fenster = max(0, h_schatten - L_ovh)
    schatten_auf_fenster = min(schatten_auf_fenster, H_fenster)
    
    F_sh = 1.0 - schatten_auf_fenster / H_fenster
    return max(0.0, min(1.0, F_sh))

def berechne_F_sh_fin_stuendlich(
    stunde: int, tag: int, standort: Standort,
    azimut_iso: float, W_fenster: float,
    D_fin: float, G_fin: float
) -> float:
    """
    Berechnet F_sh_dir für seitliche Fins zu einer bestimmten Stunde.
    
    Normkonform nach ISO 52016-1 Anhang F - analog zu Überhang, aber horizontal.
    
    Args:
        stunde: Stunde des Tages (0-23)
        tag: Tag im Jahr (1-365)
        standort: Standortdaten
        azimut_iso: Flächen-Azimut in ISO-Konvention (Süd=0°)
        W_fenster: Fensterbreite [m]
        D_fin: Fin-Tiefe (Projektion von Wand) [m]
        G_fin: Abstand Fin zur Fensterkante [m] (gap)
    
    Returns:
        F_sh_dir für diese Stunde (0=voll verschattet, 1=unverschattet)
    """
    if D_fin <= 0:
        return 1.0  # Keine Fins
    
    erg = berechne_sonnenstand(stunde, tag, standort)
    
    if erg.alpha_sol <= 0:
        return 1.0  # Nacht
    
    # Winkel zwischen Sonne und Flächennormale (Azimut)
    delta_phi = erg.phi_sol - azimut_iso
    # Normieren auf -180 bis +180
    while delta_phi > 180:
        delta_phi -= 360
    while delta_phi < -180:
        delta_phi += 360
    
    # Sonne von hinten
    if abs(delta_phi) >= 90:
        return 1.0
    
    # Horizontale Schattenlänge durch Fins
    # Projektion auf horizontale Ebene
    alpha_rad = math.radians(erg.alpha_sol)
    delta_phi_rad = math.radians(delta_phi)
    
    # Schattenlänge auf der Wand (horizontal)
    # Der Schatten wird bei flachem Sonnenwinkel (horizontal) länger
    # Früherer Sonderfall |Δφ| < 1° → F = 1 entfernt:
    # entfernt. Er war nur für G_fin > 0 redundant; bei G_fin = 0
    # (u. a. BESTEST 630/930) maskierte er Schattenbreiten bis
    # tan(1°)·D_fin. Die Formel ist bei Δφ → 0 stetig (F → 1).

    # Schattenlänge = Fin-Tiefe * tan(|delta_phi|) / sin(alpha)
    # Vereinfachte Formel für vertikale Fins:
    # Horizontale Schattenlänge auf der Wand
    tan_delta = abs(math.tan(delta_phi_rad))
    w_schatten = D_fin * tan_delta
    
    # Beide Fins (links und rechts) - der Schatten kommt von einer Seite
    # Je nach Vorzeichen von delta_phi kommt Schatten von links oder rechts
    schatten_auf_fenster = max(0, w_schatten - G_fin)
    schatten_auf_fenster = min(schatten_auf_fenster, W_fenster)
    
    F_sh = 1.0 - schatten_auf_fenster / W_fenster
    return max(0.0, min(1.0, F_sh))


# ============================================================================
# KONSTANTEN
# ============================================================================

STEFAN_BOLTZMANN = 5.67e-8  # W/(m²·K⁴)
DELTA_T = 3600.0            # Zeitschritt in Sekunden (1 Stunde)
RHO_LUFT = 1.204            # kg/m³, ρ_a bei 20 °C, Tab. 20
C_LUFT = 1006.0             # J/(kg·K), c_a Tab. 20 (vorher 1000)


def hoehenfaktor_luftdichte(hoehe_m: float) -> float:
    """Dichtekorrektur Tab. 20 Fußnote b:
    ρ_a = ρ_a;sea · (1 − 0,00651·h/288)^4,255.
    Zwei-Quellen-verifiziert 27.07.2026 (Textlayer + OCR-Struktur +
    unabhängige Zweitlesung; Standardatmosphäre-Plausibilität)."""
    return (1.0 - 0.00651 * hoehe_m / 288.0) ** 4.255

# Standardwerte nach ISO 52016-1
F_INT_C_DEFAULT = 0.4       # Konvektiver Anteil interne Gewinne
F_SOL_C_DEFAULT = 0.1       # Konvektiver Anteil solare Gewinne
F_HC_C_DEFAULT = 0.4        # Konvektiver Anteil Heiz-/Kühlleistung

# Himmelsstrahlung nach Tabelle B.19 (6.5.13.3)
DELTA_THETA_SKY_SUBPOLAR = 9.0   # K
DELTA_THETA_SKY_TROPEN = 13.0   # K
DELTA_THETA_SKY_ZWISCHEN = 11.0  # K (Standardwert)

# Wärmeübergangskoeffizienten nach ISO 13789:2017, Tabelle 7
H_CI_HORIZONTAL_UP = 5.0    # Wärmestrom aufwärts (Decke/Dach von innen)
H_CI_HORIZONTAL_DOWN = 0.7  # Wärmestrom abwärts (Boden von innen)
H_CI_VERTIKAL = 2.5         # Vertikale Flächen
H_RI_DEFAULT = 5.13         # Strahlung innen, h_lr;i Tab. 25
                            # (richtungsunabhängig laut Tabelle)
H_CE_DEFAULT = 20.0         # Konvektion außen, h_c;e Tab. 25
H_RE_DEFAULT = 4.14         # Strahlung außen, h_lr;e Tab. 25

# Emissionsgrad Standardwert nach ISO 52016-1

# Erdreich nach ISO 13370
THETA_GR_MEAN_DEFAULT = 10.0  # Mittlere Erdreichtemperatur °C

# Kalendermonat je Jahresstunde (Standardjahr 365 Tage, für die
# monatliche virtuelle Erdreichtemperatur θ_gr;vi;m)
_MONATSTAGE = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
_MONAT_JE_STUNDE = []
for _m, _tage in enumerate(_MONATSTAGE):
    _MONAT_JE_STUNDE.extend([_m] * (_tage * 24))
THETA_GR_AMPLITUDE = 3.0      # Amplitude der Jahresschwankung K


# ============================================================================
# DATENSTRUKTUREN
# ============================================================================

@dataclass
class Waermebruecke:
    """
    Wärmebrücke nach ISO 13789:2017.
    
    Linienförmige Wärmebrücken: ψ [W/(m·K)] × L [m]
    Punktförmige Wärmebrücken: χ [W/K]
    """
    id: str
    typ: str                    # 'linear' oder 'punkt'
    zone_id: str                # Zugehörige Zone
    psi_W_mK: float = 0.0       # Längenbezogener Wärmedurchgangskoeffizient
    laenge_m: float = 0.0       # Länge der Wärmebrücke
    chi_W_K: float = 0.0        # Punktförmiger Wärmedurchgangskoeffizient
    beschreibung: str = ""
    
    @property
    def H_tb(self) -> float:
        """Wärmebrücken-Wärmeübergangskoeffizient [W/K]"""
        if self.typ == 'linear':
            return self.psi_W_mK * self.laenge_m
        else:
            return self.chi_W_K


@dataclass
class Bauteil:
    """
    Repräsentiert ein opakes oder transparentes Bauteil.
    
    Opake Bauteile: 5 Knoten (pl1=außen bis pl5=innen)
    Transparente Bauteile: 2 Knoten (pl1=außen, pl2=innen)
    """
    id: str
    name: str
    typ: str                    # 'opak' oder 'transparent'
    flaeche_m2: float
    azimut_deg: float           # 0=Nord, 90=Ost, 180=Süd, 270=West
    neigung_deg: float          # 0=horizontal, 90=vertikal
    zone_innen: str             # Zone-ID
    zone_aussen: str            # Zone-ID, 'AUL', 'ADIABAT', 'ERD'
    
    # Thermische Eigenschaften (opak)
    R_c_m2K_W: float = 1.0      # Wärmedurchlasswiderstand
    kappa_m_kJ_m2K: float = 50.0  # Wirksame Wärmekapazität
    massenklasse: str = 'D'     # I, E, IE, D, M
    alpha_sol: float = 0.6      # Absorptionsgrad
    
    # Thermische Eigenschaften (transparent)
    U_W_m2K: float = 1.0        # Wärmedurchgangskoeffizient
    g_wert: float = 0.6         # Gesamtenergiedurchlassgrad (bei statisch: bereits mit Fc multipliziert)
    rahmenanteil: float = 0.25  # Anteil Rahmen an Gesamtfläche
                                # (F_fr-Standardwert Tab. B.21)
    F_w: float = 0.9            # Winkelkorrekturfaktor nach ISO 52016-1 (Standardwert)
    
    # Sonnenschutz (DIN 4108-2)
    # Steuerung: "statisch" (Fc fest), "manuell" (Nutzer), "automatik" (Sensor)
    sonnenschutz_steuerung: str = "statisch"
    # Grenzwerte: "norm" (WG/NWG abhängig), "eigene" (ein Wert für alle Richtungen)
    sonnenschutz_grenzwerte: str = "norm"
    # Eigene Schwelle in W/m² (nur wenn grenzwerte="eigene")
    sonnenschutz_schwelle_eigene: float = 200.0
    # Ist WG oder NWG? (für Norm-Grenzwerte und WE-Logik)
    ist_nwg: bool = False
    
    # Rückwärtskompatibilität: alte Modi werden in __post_init__ konvertiert
    sonnenschutz_modus: str = "statisch"  # "statisch", "automatik_wg", "automatik_nwg"
    
    g_wert_basis: float = 0.6   # Reiner g-Wert ohne Fc (für Automatik/Manuell)
    Fc_aktiviert: float = 1.0   # Fc wenn Sonnenschutz aktiv
    Fc_offen: float = 1.0       # Fc wenn Sonnenschutz offen
    
    # Wärmeübergangskoeffizienten
    h_ci: Optional[float] = None  # None = Automatik nach Tab. 25
                                  # (Richtungslogik n. Tab. 25)
    h_ri: float = H_RI_DEFAULT
    h_ce: float = H_CE_DEFAULT
    h_re: float = H_RE_DEFAULT
    
    # Verschattung (nur Direktanteil; Anhang F Verfahren 1: F_sh,dif = 1,0 fest)
    F_sh_obst: float = 1.0      # Gesamtverschattungsfaktor (Rückwärtskompatibilität)
    F_sh_obst_dir: float = 1.0  # Verschattung Direktstrahlung

    # Exakter Orientierungs-Key ("A{azimut}_T{neigung}") für
    # Elemente abseits des N/E/S/W/H-Rasters; wird in simuliere() gesetzt,
    # wenn die Klimadaten DNI/DHI liefern. None = Raster-Zuordnung.
    orientierung_key: Optional[str] = None
    
    # Stündliche Verschattungsfaktoren (8760 Werte, optional)
    F_sh_stundenwerte: Optional[np.ndarray] = None
    
    # Horizontverschattung nach Anhang F
    horizont_winkel_deg: float = 0.0  # Horizontverschattungswinkel
    
    # Überhang-Geometrie für normkonforme stündliche Berechnung (ISO 52016-1 Anhang F)
    ueberhang_tiefe_m: float = 0.0      # D_ovh: Tiefe des Überhangs [m]
    ueberhang_abstand_m: float = 0.0    # L_ovh: Abstand Überhang zu Fenster-OK [m]
    fenster_hoehe_m: float = 2.0        # H: Fensterhöhe für Verschattungsberechnung [m]

    # Erdreich-Eingaben (ISO-13370-Ableitung).
    # Rohdaten aus dem JSON; ausgewertet in bereite_erdreich_vor().
    erdreich_daten: Optional[Dict[str, Any]] = None
    # Zur Laufzeit gesetzt (nur Knotenmodell): 12 Monatswerte θ_gr;vi;m
    theta_gr_vi_monat: Optional[List[float]] = None
    
    # Fin-Geometrie (seitliche Lamellen) - ISO 52016-1 Anhang F
    fin_tiefe_m: float = 0.0            # D_fin: Tiefe des Fins [m]
    fin_abstand_m: float = 0.0          # G_fin: Abstand zur Fensterkante [m]
    fenster_breite_m: float = 3.0       # W: Fensterbreite [m]
    
    # Berechnete Größen (werden zur Laufzeit gefüllt)
    h_pl: List[float] = field(default_factory=list)     # Leitwerte
    kappa_pl: List[float] = field(default_factory=list) # Kapazitäten pro Knoten
    n_knoten: int = 5           # Anzahl Knoten
    theta_pl: np.ndarray = field(default_factory=lambda: np.zeros(5))
    
    # Sichtfaktor zum Himmel (wird berechnet)
    F_sky: float = 0.5
    
    def __post_init__(self):
        """Berechne Leitwerte und Kapazitäten nach Initialisierung"""
        # Richtungsabhängige h_ci nach ISO 13789:2017
        self._setze_h_ci_nach_richtung()
        
        # Sichtfaktor zum Himmel nach Neigung (6.5.13.3)
        self._berechne_F_sky()
        
        if self.typ == 'opak':
            self.n_knoten = 5
            self._berechne_leitwerte_opak()
            self._berechne_kapazitaeten()
        else:  # transparent
            self.n_knoten = 2
            self._berechne_leitwerte_transparent()
            self.kappa_pl = [0.0, 0.0]  # Keine thermische Masse
        
        self.theta_pl = np.ones(self.n_knoten) * 20.0  # Starttemperatur
    
    def konfiguriere_erdreich_knotenmodell(self, R_gr_m2K_W: float,
                                           kappa_gr_J_m2K: float,
                                           R_vi_m2K_W: float):
        """Verdrahtet dieses ERD-Bauteil auf das normeigene
        Erdreich-Knotenmodell der ISO 52016-1 (Gl. 48–50).

        Gl. (48), Knotenkonvention pl1 = außen … pl5 = innen,
        h_pl[i] = Leitwert zwischen Knoten i und i+1
        (Lesart A / M4: R_c ist die REINE Konstruktion):
          h_pl1 = 2/R_gr | h_pl2 = 1/(R_c/4 + R_gr/2)
          h_pl3 = 2/R_c  | h_pl4 = 4/R_c
        Gl. (50): κ_pl1 = 0 (virtuell), κ_pl2 = κ_gr, Elementmasse
        nach Klasse auf pl3…pl5. Gl. (49): h_ce + h_re = 1/R_gr;vi —
        umgesetzt als h_ce = 1/R_vi, h_re = 0, womit Φ_sky (Gl. 70)
        automatisch entfällt.
        """
        R_c = max(self.R_c_m2K_W, 0.001)
        self.h_pl = [2.0 / R_gr_m2K_W,
                     1.0 / (R_c / 4.0 + R_gr_m2K_W / 2.0),
                     2.0 / R_c,
                     4.0 / R_c]
        km = self.kappa_m_kJ_m2K * 1000 / 3600     # kJ -> Wh
        kgr = kappa_gr_J_m2K / 3600                # J  -> Wh
        if self.massenklasse == 'I':      # Gl. (50a): κ_pl5 = κ_m
            rest = [0.0, 0.0, km]
        elif self.massenklasse == 'E':    # Gl. (50b): κ_pl3 = κ_m
            rest = [km, 0.0, 0.0]
        elif self.massenklasse == 'IE':   # Gl. (50c)
            rest = [km / 2, 0.0, km / 2]
        elif self.massenklasse == 'M':    # Gl. (50e): κ_pl4 = κ_m
            rest = [0.0, km, 0.0]
        else:                             # Gl. (50d), Klasse D
            rest = [km / 4, km / 2, km / 4]
        self.kappa_pl = [0.0, kgr] + rest
        self.h_ce = 1.0 / R_vi_m2K_W
        self.h_re = 0.0

    def _setze_h_ci_nach_richtung(self):
        """
        h_ci-Automatik nach Tabelle 25 (Zwei-Quellen-verifiziert
        27.07.: h_c;i = 5,0 / 2,5 / 0,7 für Wärmestrom aufwärts /
        horizontal / abwärts; laut Norm-Anmerkung aus ISO 13789).

        Greift NUR bei h_ci = None (kein expliziter Wert). Konvention
        Wärmestromrichtung = Verlustfall entlang der Bauteilnormalen
        (Neigung 0° = Normale aufwärts/Dach, 180° = abwärts/Boden),
        unabhängig von der Randbedingung — gilt damit auch für
        ADIABAT-/Nachbarzonen-Decken und -Böden richtungsabhängig
        statt pauschal vertikal.
        Frühere Fassung: Sentinel h_ci == 2,5 (explizite 2,5 wurde
        überschrieben), nur Neigung < 45° und nur AUL/ERD behandelt.
        """
        if self.h_ci is None:
            if self.zone_aussen == 'ERD':
                # Erdreich = per Definition Wärmestrom abwärts; hat
                # Vorrang vor der Neigung, weil Bestandsmodelle (GUI,
                # Fixtures) Erdböden mit Neigung 0 eintragen.
                self.h_ci = H_CI_HORIZONTAL_DOWN
            elif self.neigung_deg <= 45:
                self.h_ci = H_CI_HORIZONTAL_UP      # Wärmestrom aufwärts
            elif self.neigung_deg < 135:
                self.h_ci = H_CI_VERTIKAL           # horizontal
            else:
                self.h_ci = H_CI_HORIZONTAL_DOWN    # Wärmestrom abwärts
    
    def _berechne_F_sky(self):
        """
        Berechnet Sichtfaktor zum Himmel nach Tabelle B.18 (6.5.13.3).
        
        F_sky = (1 + cos(β)) / 2
        β = Neigungswinkel (0° = horizontal, 90° = vertikal)
        """
        beta_rad = math.radians(self.neigung_deg)
        self.F_sky = (1 + math.cos(beta_rad)) / 2
        # F_sky ist nach Gl. (70) i. V. m. Tabelle B.18 rein neigungs-
        # bestimmt (1,0 horizontal / 0,5 vertikal). Der Horizontwinkel
        # wirkt ausschließlich auf die solare Direktstrahlung (Anhang F);
        # eine langwellige Horizontkorrektur kennt der Normtext nicht.
    
    def _berechne_leitwerte_opak(self):
        """Gleichung 43: Leitwerte aus R_c für 5-Knoten-Modell"""
        R_c = max(self.R_c_m2K_W, 0.001)  # Schutz vor Division durch 0
        h1 = 6.0 / R_c
        h2 = 3.0 / R_c
        # h_pl[i] ist Leitwert zwischen Knoten i und i+1
        self.h_pl = [h1, h2, h2, h1]  # 4 Leitwerte für 5 Knoten
    
    def _berechne_leitwerte_transparent(self):
        """Leitwerte für 2-Knoten-Fenstermodell.

        ISO 52016-1 Gl. (51): h_pl1 = 1/R_c
        mit Gl. (53): R_c = 1/U_W - R_si;v - R_se;v  (R_si;v = 0,13; R_se;v = 0,04)
        Die Oberflächenübergänge sitzen separat an den Endknoten (h_ci/h_ri, h_ce/h_re);
        U_W direkt als Knotenleitwert würde die Übergangswiderstände doppelt zählen.
        """
        # Klemme max(..., 1e-6): normfremd gegenüber dem Wortlaut von
        # Gl. (53), aber nur die Definitionsgrenze der Gl.-53-Zerlegung
        # selbst — für U_W ≥ 1/(0,13+0,04) ≈ 5,88 W/(m²K) wird R_c ≤ 0,
        # d. h. die Zerlegung in R_c + Übergangswiderstände bricht
        # physikalisch zusammen; reale Verglasungen liegen weit darunter
        # (Klemme bleibt, dokumentiert).
        R_c = max(1.0 / self.U_W_m2K - 0.13 - 0.04, 1e-6)
        self.h_pl = [1.0 / R_c]
    
    def _berechne_kapazitaeten(self):
        """Gleichung 44-47: Kapazitätsverteilung nach Massenklasse"""
        kappa = self.kappa_m_kJ_m2K * 1000 / 3600  # kJ -> Wh
        
        if self.massenklasse == 'D':      # Gleichmäßig verteilt (Gl. 47a)
            self.kappa_pl = [kappa/8, kappa/4, kappa/4, kappa/4, kappa/8]
        elif self.massenklasse == 'I':    # Innen konzentriert (Gl. 44)
            self.kappa_pl = [0, 0, 0, 0, kappa]
        elif self.massenklasse == 'E':    # Außen konzentriert (Gl. 45)
            self.kappa_pl = [kappa, 0, 0, 0, 0]
        elif self.massenklasse == 'IE':   # Beidseitig verteilt (Gl. 46)
            self.kappa_pl = [kappa/2, 0, 0, 0, kappa/2]
        elif self.massenklasse == 'M':    # Mitte (Gl. 47b)
            self.kappa_pl = [0, 0, kappa, 0, 0]
        else:
            self.kappa_pl = [kappa/8, kappa/4, kappa/4, kappa/4, kappa/8]


@dataclass
class Zone:
    """Thermische Zone mit zugehörigen Bauteilen"""
    id: str
    name: str
    volumen_m3: float
    nutzflaeche_m2: float
    nutzungsprofil: str
    
    # Interne Luftkapazität (Luft + Möbel)
    kapazitaet_Wh_K: float = 0.0  # Wenn 0, wird aus Volumen berechnet
    
    # Wärmebrücken der Zone
    waermebruecken: List[Waermebruecke] = field(default_factory=list)
    
    # Bauteile werden später zugewiesen
    bauteile: List[Bauteil] = field(default_factory=list)
    
    # Berechnete Größen
    theta_air: float = 20.0       # Raumlufttemperatur
    theta_op: float = 20.0        # Operative Temperatur
    theta_rad_mean: float = 20.0  # Mittlere Strahlungstemperatur
    A_tot: float = 0.0            # Gesamte innere Oberfläche
    C_int: float = 0.0            # Interne Kapazität [Wh/K]
    H_tb: float = 0.0             # Gesamter Wärmebrücken-Koeffizient [W/K]
    
    def __post_init__(self):
        """Berechne interne Kapazität"""
        if self.kapazitaet_Wh_K <= 0:
            # ISO 52016-1 Gl. (63): C_int;ztc = kappa_m;int;a * A_use.
            # kappa_m;int;a ist die flaechenbezogene Waermekapazitaet von "Luft UND
            # Moebeln" (6.5.11, Tab. A.17/B.17) - die Luft steckt BEREITS darin.
            # Fuer die Verifizierungsfaelle: kappa_m;int = 10 000 J/(m2K) (7.2.2.5).
            # KEIN separater V*rho*c-Luftterm (sonst wird die Luft doppelt gezaehlt).
            self.C_int = self.nutzflaeche_m2 * 10000.0 / 3600.0
        else:
            self.C_int = self.kapazitaet_Wh_K
    
    def berechne_A_tot(self):
        """Berechne Gesamtfläche aller inneren Oberflächen.

        Gl. (39): A_tot = Summe der Flächen ALLER Gebäudeelemente
        elk = 1…eln der Zone — ohne Ausnahme, auch transparente
        Elemente mit Randbedingung ADIABAT zählen mit
        """
        self.A_tot = sum(bt.flaeche_m2 for bt in self.bauteile)
        # Frühere stille Klemme auf 1 m² entfernt —
        # sie verfälschte Gl. (39) statt den Modellfehler zu melden.
        if self.A_tot <= 0.0:
            raise ValueError(
                f"Zone '{self.id}': A_tot = {self.A_tot} m² — Zone ohne "
                f"Hüllflächen ist kein gültiges 52016-Modell (Gl. 39).")
        if self.A_tot < 1.0:
            warnings.warn(
                f"Zone '{self.id}': A_tot = {self.A_tot:.3f} m² < 1 m² — "
                f"physikalisch fragwürdig, wird unverändert verwendet "
                f"(keine stille Klemme mehr).")
    
    def berechne_H_tb(self):
        """Berechne Gesamt-Wärmebrückenkoeffizient"""
        self.H_tb = sum(wb.H_tb for wb in self.waermebruecken)


@dataclass
class Randbedingung:
    """Definition einer Randbedingung"""
    typ: str                      # 'aussenluft', 'adiabatisch', 'erdreich', 'nachbarzone'
    temperatur_C: float = 10.0    # Für Erdreich: mittlere Jahrestemperatur
    amplitude_K: float = 3.0      # Amplitude der Jahresschwankung (Erdreich)
    phasenverschiebung_monate: float = 1.0  # Phasenverschiebung
    zone_id: str = ""             # Für Nachbarzone: ID der angrenzenden Zone


@dataclass
class Nutzungsprofil:
    """Stündliches Nutzungsprofil"""
    id: str
    beschreibung: str
    
    # 24 Werte für jeden Parameter (Index 0 = Stunde 1, etc.)
    heizen_C: List[float] = field(default_factory=lambda: [20.0]*24)
    kuehlen_C: List[float] = field(default_factory=lambda: [26.0]*24)
    interne_gewinne_W: List[float] = field(default_factory=lambda: [0.0]*24)
    luftwechsel_1_h: List[float] = field(default_factory=lambda: [0.5]*24)
    
    f_int_konv: float = F_INT_C_DEFAULT
    
    # Bedingte Nachtlüftung (BESTEST 650/950)
    nachtlueftung_aktiv: bool = False
    nachtlueftung_ach: float = 7.17  # ACH bei aktiver Nachtlüftung
    nachtlueftung_stunden: List[int] = field(default_factory=lambda: list(range(18,24)) + list(range(0,7)))  # 18-07 Uhr
    
    # DIN 4108-2 temperaturgesteuerte Lüftung
    lueftung_modus: str = "zeitgesteuert"  # "zeitgesteuert" (BESTEST) oder "din4108"
    aufenthaltszeit_stunden: List[int] = field(default_factory=lambda: list(range(6, 23)))  # WG: 6-23h
    taglueftung_erhoht_ach: float = 3.0  # n bei erhöhter Taglüftung
    
    # Leistungsbegrenzung (VDI 6020 Fall 7)
    max_heizleistung_W: float = 1e9   # Unbegrenzt wenn nicht gesetzt
    max_kuehlleistung_W: float = 1e9  # Unbegrenzt wenn nicht gesetzt
    
    # Regelgröße: False = θ_op (Standard ISO 52016), True = θ_air (VDI 6020)
    regelung_nach_luft: bool = False

    # Zweites internes Quellprofil mit EIGENEM Konvektivanteil (
    # VDI-6020-Testbeispiel 5: solare Gewinne "im Raum" mit a_kon = 0,09
    # neben der Personen-/Maschinenlast mit anderem Split). Default None
    # -> Phi_int2 = 0, bestehende Pfade bitidentisch.
    interne_gewinne_2_W: Optional[List[float]] = None
    f_int_2_konv: float = 1.0


@dataclass
class Gebaeude:
    """Container für das gesamte Gebäude"""
    name: str
    beschreibung: str
    zonen: Dict[str, Zone] = field(default_factory=dict)
    bauteile: Dict[str, Bauteil] = field(default_factory=dict)
    randbedingungen: Dict[str, Randbedingung] = field(default_factory=dict)
    nutzungsprofile: Dict[str, Nutzungsprofil] = field(default_factory=dict)
    waermebruecken: Dict[str, Waermebruecke] = field(default_factory=dict)  # NEU


# Alias for backwards compatibility
Klimadaten = ClimateData


@dataclass
class SimulationsOptionen:
    """Steuerparameter für die Simulation"""
    klimadatei: str
    klimaformat: str = 'ISO52016'  # 'ISO52016', 'TRY_DWD_2010', 'TRY_DWD_2015'
    init_tage: int = 31
    
    # Physikalische Parameter
    f_sol_konv: float = F_SOL_C_DEFAULT
    f_HC_konv: float = F_HC_C_DEFAULT
    # Δθ_sky [K]: expliziter Wert hat Vorrang; None = Ableitung aus klimazone (Tab. B.19)
    delta_theta_sky_K: Optional[float] = None
    klimazone: str = 'zwischen'  # 'subpolar', 'tropen', 'zwischen'
    
    # Standort für Sonnenstandsberechnung (normkonforme Verschattung)
    standort: Standort = field(default_factory=lambda: DENVER)

    # OPT-IN-Höhenkorrektur der Luftdichte für
    # den Lüftungsleitwert (Tab. 20 Fn. b). None = aus. BEWUSST nicht
    # automatisch aus dem Klimadatei-Header (TRY-/TMY3-Header führen die Stationshöhe):
    # die BESTEST-Prüffälle korrigieren die Höhe extern über den
    # ACH-Faktor 0,822 (7.2.2.14) — Automatik wäre Doppelkorrektur.
    standort_hoehe_m: Optional[float] = None

    # Erdreichmodell. "knotenmodell" = normeigenes Gl.-48-Modell
    # (Default); "sinus_direkt" =
    # dokumentiertes Altverhalten (Sinustemperatur über normale
    # h_ce/h_re-Kopplung).
    erdreich_modell: str = "knotenmodell"
    
    # Ausgabe
    ausgabe_stunden: bool = True
    ausgabe_monate: bool = True
    ausgabe_datei_csv: str = 'ergebnisse.csv'
    ausgabe_datei_json: str = 'ergebnisse.json'


# ============================================================================
# EINGABE-FUNKTIONEN
# ============================================================================

def lade_gebaeude(pfad_gebaeude: str, pfad_nutzung: str) -> Gebaeude:
    """
    Lädt Gebäudedaten und Nutzungsprofile aus JSON-Dateien.
    
    Args:
        pfad_gebaeude: Pfad zur Gebäude-JSON-Datei (Zonen, Bauteile, etc.)
        pfad_nutzung: Pfad zur Nutzungsprofil-JSON-Datei (Solltemperaturen, etc.)
    
    Returns:
        Vollständig initialisiertes Gebaeude-Objekt
    """
    with open(pfad_gebaeude, 'r', encoding='utf-8') as f:
        daten = json.load(f)
    
    with open(pfad_nutzung, 'r', encoding='utf-8') as f:
        nutzung_daten = json.load(f)
    
    # Gebäude erstellen
    projekt = daten.get('projekt', {})
    gebaeude = Gebaeude(
        name=projekt.get('name', 'Unbenannt'),
        beschreibung=projekt.get('beschreibung', '')
    )
    
    # Randbedingungen laden
    for rb_id, rb_daten in daten.get('randbedingungen', {}).items():
        gebaeude.randbedingungen[rb_id] = Randbedingung(
            typ=rb_daten.get('typ', 'aussenluft'),
            temperatur_C=rb_daten.get('temperatur_C', 10.0),
            amplitude_K=rb_daten.get('amplitude_K', 3.0),
            phasenverschiebung_monate=rb_daten.get('phasenverschiebung_monate', 1.0),
            zone_id=rb_daten.get('zone_id', '')
        )
    
    # Nutzungsprofile laden
    for np_id, np_daten in nutzung_daten.get('profile', {}).items():
        gebaeude.nutzungsprofile[np_id] = Nutzungsprofil(
            id=np_id,
            beschreibung=np_daten.get('beschreibung', ''),
            heizen_C=np_daten.get('solltemperaturen', {}).get('heizen_C', [20.0]*24),
            kuehlen_C=np_daten.get('solltemperaturen', {}).get('kuehlen_C', [26.0]*24),
            interne_gewinne_W=np_daten.get('interne_gewinne_W', [0.0]*24),
            luftwechsel_1_h=np_daten.get('luftwechsel_1_h', [0.5]*24) 
                if isinstance(np_daten.get('luftwechsel_1_h'), list) 
                else [np_daten.get('luftwechsel_1_h', 0.5)]*24,
            f_int_konv=np_daten.get('f_int_konv', F_INT_C_DEFAULT),
            # Zweites internes Quellprofil (dokumentiert-normfremde Erweiterung)
            interne_gewinne_2_W=np_daten.get('interne_gewinne_2_W', None),
            f_int_2_konv=np_daten.get('f_int_2_konv', 1.0),
            # Bedingte Nachtlüftung
            nachtlueftung_aktiv=np_daten.get('nachtlueftung_aktiv', False),
            nachtlueftung_ach=np_daten.get('nachtlueftung_ach', 7.17),
            nachtlueftung_stunden=np_daten.get('nachtlueftung_stunden', 
                list(range(18,24)) + list(range(0,7))),
            # Leistungsbegrenzung (VDI 6020 Fall 7)
            max_heizleistung_W=np_daten.get('max_heizleistung_W', 1e9),
            max_kuehlleistung_W=np_daten.get('max_kuehlleistung_W', 1e9),
            # Regelgröße (VDI 6020: Lufttemperatur)
            regelung_nach_luft=np_daten.get('regelung_nach_luft', False),
            # Zusatzfelder (Defaults = Neutralpfade):
            # Defaults unverändert = Neutralpfade ("zeitgesteuert" =
            # BESTEST-Pfad; "din4108" aktiviert die nationale
            # Tag-/Nachtlüftungslogik).
            lueftung_modus=np_daten.get('lueftung_modus',
                                        'zeitgesteuert'),
            aufenthaltszeit_stunden=np_daten.get(
                'aufenthaltszeit_stunden', list(range(6, 23))),
            taglueftung_erhoht_ach=np_daten.get('taglueftung_erhoht_ach',
                                                3.0)
        )
    
    # Wärmebrücken laden
    for wb_id, wb_daten in daten.get('waermebruecken', {}).items():
        # Überspringe Kommentar-Einträge
        if wb_id.startswith('_') or not isinstance(wb_daten, dict):
            continue
        gebaeude.waermebruecken[wb_id] = Waermebruecke(
            id=wb_id,
            typ=wb_daten.get('typ', 'linear'),
            zone_id=wb_daten.get('zone_id', ''),
            psi_W_mK=wb_daten.get('psi_W_mK', 0.0),
            laenge_m=wb_daten.get('laenge_m', 0.0),
            chi_W_K=wb_daten.get('chi_W_K', 0.0),
            beschreibung=wb_daten.get('beschreibung', '')
        )
    
    # Import für kappa_m Berechnung
    from iso52016.thermal_mass import Schicht, berechne_kappa_m, bestimme_massenklasse
    
    # Bauteile laden
    for bt_daten in daten.get('bauteile', []):
        # Berechne kappa_m und R_c aus Schichten wenn vorhanden
        schichten_daten = bt_daten.get('schichten', [])
        if schichten_daten and 'kappa_m_kJ_m2K' not in bt_daten:
            schichten = [
                Schicht(
                    name=s.get('material', 'Material'),
                    dicke_m=s.get('dicke_m', 0),
                    lambda_W_mK=s.get('lambda_W_mK', 1.0),
                    rho_kg_m3=s.get('rho_kg_m3', 1000),
                    c_J_kgK=s.get('c_J_kgK', 1000)
                )
                for s in schichten_daten if s.get('dicke_m', 0) > 0
            ]
            if schichten:
                # ISO 52016-1, 6.5.7.2: kappa_m;op ist die flaechenbezogene wirksame
                # Waermekapazitaet, die nach Gl. (44)-(47) auf die Knoten verteilt wird.
                # Hier wird die VOLLE Schichtsumme Sigma(rho*c*d) verwendet (statt der
                # ISO-13786-Eindringtiefen-Kappung aus berechne_kappa_m), weil die
                # 52016-Knotenbildung an dieser Stelle keine Tagesperioden-Begrenzung
                # vorsieht - das entspricht den Prueffall-Werten aus Tabelle 23/24.
                # Schalter 'kappa_13786_kappung': True stellt das alte Verhalten wieder her.
                if bt_daten.get('kappa_13786_kappung', False):
                    kappa_m_J = berechne_kappa_m(schichten)
                else:
                    kappa_m_J = sum(s.rho_kg_m3 * s.c_J_kgK * s.dicke_m for s in schichten)
                kappa_m_kJ = kappa_m_J / 1000  # J -> kJ
                # Verwende massenklasse aus JSON wenn vorhanden, sonst berechne
                if 'massenklasse' in bt_daten:
                    massenklasse = bt_daten['massenklasse']
                else:
                    massenklasse = bestimme_massenklasse(schichten).value
                # R_c = Summe(d/lambda) für alle Schichten
                R_c = sum(s.get('dicke_m', 0) / s.get('lambda_W_mK', 1.0) 
                          for s in schichten_daten if s.get('dicke_m', 0) > 0 and s.get('lambda_W_mK', 1.0) > 0)
            else:
                kappa_m_kJ = 50.0
                massenklasse = bt_daten.get('massenklasse', 'D')
                R_c = bt_daten.get('R_c_m2K_W', 1.0)
        else:
            kappa_m_kJ = bt_daten.get('kappa_m_kJ_m2K', 50.0)
            massenklasse = bt_daten.get('massenklasse', 'D')
            R_c = bt_daten.get('R_c_m2K_W', 1.0)
        if 'epsilon' in bt_daten:
            # Feld 'epsilon' entfernt — es wurde geladen,
            # wirkte aber nirgends. Die Normgröße für die langwellige
            # Abstrahlung ist h_re (Gl. 70).
            warnings.warn(
                f"Bauteil '{bt_daten.get('id', '?')}': Eingabefeld "
                f"'epsilon' ist entfernt und wird ignoriert. Für die "
                f"Himmelsabstrahlung h_re_W_m2K setzen (Gl. 70).")
        bt = Bauteil(
            id=bt_daten['id'],
            name=bt_daten.get('name', bt_daten['id']),
            typ=bt_daten.get('typ', 'opak'),
            flaeche_m2=bt_daten['flaeche_m2'],
            azimut_deg=bt_daten.get('azimut_deg', 0),
            neigung_deg=bt_daten.get('neigung_deg', 90),
            zone_innen=bt_daten['zone_innen'],
            zone_aussen=bt_daten.get('zone_aussen', 'AUL'),
            R_c_m2K_W=R_c,
            kappa_m_kJ_m2K=kappa_m_kJ,
            massenklasse=massenklasse,
            alpha_sol=bt_daten.get('alpha_sol', 0.6),
            U_W_m2K=bt_daten.get('U_W_m2K', 1.0),
            g_wert=bt_daten.get('g_wert', 0.6),
            rahmenanteil=bt_daten.get('rahmenanteil', 0.25),
            F_w=bt_daten.get('F_w', 0.9),  # Default = Klassen-Default 0.9 (ISO 52016-1 Tab. B.22); vorher inkonsistent 1.0 (Audit B13)
            h_ci=bt_daten.get('h_ci_W_m2K'),  # None -> Automatik (Tab. 25)
            h_ri=bt_daten.get('h_ri_W_m2K', H_RI_DEFAULT),
            h_ce=bt_daten.get('h_ce_W_m2K', H_CE_DEFAULT),
            h_re=bt_daten.get('h_re_W_m2K', H_RE_DEFAULT),
            F_sh_obst=bt_daten.get('F_sh_obst', 1.0),
            F_sh_obst_dir=bt_daten.get('F_sh_obst_dir', bt_daten.get('F_sh_obst', 1.0)),
            horizont_winkel_deg=bt_daten.get('horizont_winkel_deg', 0.0),
            # Überhang-Geometrie für normkonforme stündliche Berechnung
            ueberhang_tiefe_m=bt_daten.get('ueberhang_tiefe_m', 0.0),
            ueberhang_abstand_m=bt_daten.get('ueberhang_abstand_m', 0.0),
            fenster_hoehe_m=bt_daten.get('fenster_hoehe_m', 2.0),
            # Fin-Geometrie
            fin_tiefe_m=bt_daten.get('fin_tiefe_m', 0.0),
            fin_abstand_m=bt_daten.get('fin_abstand_m', 0.0),
            fenster_breite_m=bt_daten.get('fenster_breite_m', 3.0),
            # Vormals nur programmatisch
            # erreichbare Felder an das JSON angeschlossen. Defaults
            # unverändert = Neutralpfade.
            erdreich_daten=bt_daten.get('erdreich'),
            F_sh_stundenwerte=(np.asarray(bt_daten['F_sh_stundenwerte'],
                                          dtype=float)
                               if bt_daten.get('F_sh_stundenwerte')
                               is not None else None),
            sonnenschutz_steuerung=bt_daten.get('sonnenschutz_steuerung',
                                                'statisch'),
            sonnenschutz_grenzwerte=bt_daten.get('sonnenschutz_grenzwerte',
                                                 'norm'),
            sonnenschutz_schwelle_eigene=bt_daten.get(
                'sonnenschutz_schwelle_eigene', 200.0),
            sonnenschutz_modus=bt_daten.get('sonnenschutz_modus',
                                            'statisch'),
            ist_nwg=bt_daten.get('ist_nwg', False),
            g_wert_basis=bt_daten.get('g_wert_basis', 0.6),
            Fc_aktiviert=bt_daten.get('Fc_aktiviert', 1.0),
            Fc_offen=bt_daten.get('Fc_offen', 1.0)
        )
        gebaeude.bauteile[bt.id] = bt
    
    # Zonen laden und Bauteile/Wärmebrücken zuordnen
    for z_daten in daten.get('zonen', []):
        zone = Zone(
            id=z_daten['id'],
            name=z_daten.get('name', z_daten['id']),
            volumen_m3=z_daten['volumen_m3'],
            # Hinweis: Default nutzflaeche_m2 = Volumen/3
            # (implizite Raumhöhe 3 m). Wirkt STILL auf C_int (Gl. 63,
            # κ_m;int·A_use) und damit auf die Dynamik des Luftknotens.
            # Für belastbare Ergebnisse nutzflaeche_m2 explizit setzen.
            nutzflaeche_m2=z_daten.get('nutzflaeche_m2', z_daten['volumen_m3']/3),
            nutzungsprofil=z_daten.get('nutzungsprofil', ''),
            kapazitaet_Wh_K=z_daten.get('kapazitaet_Wh_K', 0)
        )
        
        # Bauteile der Zone zuordnen
        for bt in gebaeude.bauteile.values():
            if bt.zone_innen == zone.id:
                zone.bauteile.append(bt)
        
        # Wärmebrücken der Zone zuordnen
        for wb in gebaeude.waermebruecken.values():
            if wb.zone_id == zone.id:
                zone.waermebruecken.append(wb)
        
        zone.berechne_A_tot()
        zone.berechne_H_tb()
        gebaeude.zonen[zone.id] = zone
    
    return gebaeude



def lade_klimadaten(pfad: str, format: str = 'ISO52016') -> ClimateData:
    """
    Load climate data from various formats.
    
    This is a wrapper around load_climate() for backwards compatibility.
    
    Args:
        pfad: Path to climate data file
        format: Data format ('ISO52016', 'TMY3', 'TRY_DWD_2015', 'TRY_DWD_2045')
    
    Returns:
        ClimateData object with hourly values
    """
    # Map old format names to new ones
    format_map = {
        'ISO52016': 'csv',
        'TMY3': 'tmy3',
        'TRY': 'try',
        'TRY_DWD_2015': 'try',  # All TRY variants use same loader
        'TRY_DWD_2045': 'try',
    }
    
    new_format = format_map.get(format, format.lower())
    return load_climate(pfad, new_format)


def lade_optionen(pfad: str) -> SimulationsOptionen:
    """
    Lädt Simulationsoptionen aus JSON-Datei.
    
    Args:
        pfad: Pfad zur Optionen-JSON-Datei
    
    Returns:
        SimulationsOptionen mit Klimadatei, Zeitraum, Ausgabeoptionen
    """
    with open(pfad, 'r', encoding='utf-8') as f:
        daten = json.load(f)
    
    sim = daten.get('simulation', {})
    aus = daten.get('ausgabe', {})
    opt = daten.get('optionen', {})

    # Relative Klimapfade gelten relativ zur Steuerungs-JSON (nicht zum
    # Arbeitsverzeichnis) — macht Configs maschinen- und startortunabhängig.
    # Absolute Pfade bleiben unverändert gültig.
    klimadatei = sim.get('klimadatei', '')
    if klimadatei and not Path(klimadatei).is_absolute():
        klimadatei = str((Path(pfad).resolve().parent / klimadatei).resolve())

    return SimulationsOptionen(
        klimadatei=klimadatei,
        klimaformat=sim.get('klimaformat', 'ISO52016'),
        init_tage=sim.get('initialisierung_tage', 31),
        f_sol_konv=opt.get('f_sol_konv', F_SOL_C_DEFAULT),
        f_HC_konv=opt.get('f_HC_konv', F_HC_C_DEFAULT),
        delta_theta_sky_K=opt.get('delta_theta_sky_K', None),
        klimazone=opt.get('klimazone', 'zwischen'),
        ausgabe_stunden=aus.get('stundenwerte', True),
        ausgabe_monate=aus.get('monatswerte', True),
        ausgabe_datei_csv=aus.get('datei_csv', 'ergebnisse.csv'),
        ausgabe_datei_json=aus.get('datei_json', 'ergebnisse.json')
    )


# ============================================================================
# HILFSFUNKTIONEN
# ============================================================================

def orientierung_zu_key(azimut: float, neigung: float) -> str:
    """
    Wandelt Azimut und Neigung in Orientierungs-Key um.
    
    Args:
        azimut: Flächenazimut [°], BESTEST-Konvention (Nord=0, Ost=90, Süd=180)
        neigung: Flächenneigung [°], 0=horizontal, 90=vertikal
    
    Returns:
        Orientierungsschlüssel: 'N', 'E', 'S', 'W' oder 'H' (horizontal)
    """
    if neigung < 45:
        return 'H'
    
    if azimut < 45 or azimut >= 315:
        return 'N'
    elif azimut < 135:
        return 'E'
    elif azimut < 225:
        return 'S'
    else:
        return 'W'


RASTER_AZIMUTE = (0.0, 90.0, 180.0, 270.0)


def orientierung_key_exakt(azimut: float, neigung: float) -> Optional[str]:
    """
    Liefert einen exakten Orientierungs-Key, wenn das Element
    NICHT exakt auf dem 5-Richtungs-Raster liegt, sonst None.

    Raster (Spezialfall, bleibt bitidentisch zur bisherigen Zuordnung):
      - neigung == 0 -> 'H' (Azimut bei horizontaler Fläche irrelevant)
      - neigung == 90 und azimut in {0, 90, 180, 270} -> N/E/S/W

    Alles andere (Zwischenazimute, geneigte Dächer, abwärts weisende
    Flächen) erhält einen eigenen Key und wird — sofern die Klimadaten
    DNI/DHI liefern — über die 52010-1-Kette mit den echten Winkeln
    berechnet (Gl. 41/69: β/γ des Elements aus EPB-Modul M1-13).

    Args:
        azimut: Flächenazimut [°], BESTEST-Konvention (N=0, O=90, S=180)
        neigung: Flächenneigung [°], 0=horizontal, 90=vertikal
    """
    az = azimut % 360.0
    if neigung == 0.0:
        return None
    if neigung == 90.0 and az in RASTER_AZIMUTE:
        return None
    return f"A{az:g}_T{neigung:g}"


def _bt_orientierungs_key(bt, I_sol_dict: Dict[str, float]) -> str:
    """
    Key-Auflösung je Bauteil: exakter Key, wenn gesetzt UND in den
    Strahlungsdaten vorhanden; sonst Raster-Zuordnung (Fallback für
    Direktspalten-CSVs ohne DNI/DHI und für direkte Aufrufe mit
    Raster-Dicts, z. B. in Tests).
    """
    key = getattr(bt, 'orientierung_key', None)
    if key and key in I_sol_dict:
        return key
    return orientierung_zu_key(bt.azimut_deg, bt.neigung_deg)


def hole_solare_einstrahlung(klima: Klimadaten, stunde: int, 
                             azimut: float, neigung: float) -> float:
    """
    Gibt solare Einstrahlung für gegebene Orientierung zurück.
    
    Args:
        klima: Klimadaten-Objekt mit I_sol Dictionary
        stunde: Stunde im Jahr (0-8759)
        azimut: Flächenazimut [°]
        neigung: Flächenneigung [°]
    
    Returns:
        Solare Einstrahlung [W/m²]
    """
    key = orientierung_zu_key(azimut, neigung)
    if stunde < 0 or stunde >= klima.n_stunden:
        return 0.0
    return klima.I_sol[key][stunde]


def berechne_erdreich_temperatur(rb: Randbedingung, stunde: int) -> float:
    """
    Berechnet zeitabhängige Erdreichtemperatur.
    
    Args:
        rb: Randbedingung mit Mitteltemperatur, Amplitude und Phasenverschiebung
        stunde: Stunde im Jahr (0-8759)
    
    Returns:
        Erdreichtemperatur [°C]
    
    Reference:
        ISO 13370 - Sinusförmiger Jahresgang:
        θ_gr(t) = θ_mean + A × sin(2π × (t - φ) / 8760)
    """
    theta_mean = rb.temperatur_C
    amplitude = rb.amplitude_K
    phase_stunden = rb.phasenverschiebung_monate * 730  # Monate -> Stunden
    
    theta_gr = theta_mean + amplitude * math.sin(
        2 * math.pi * (stunde - phase_stunden) / 8760
    )
    
    return theta_gr


def berechne_delta_theta_sky(klimazone: str) -> float:
    """
    Gibt Δθ_sky für Himmelsstrahlung zurück.
    
    Args:
        klimazone: 'subpolar', 'zwischen' oder 'tropen'
    
    Returns:
        Temperaturdifferenz Δθ_sky [K]
    
    Reference:
        DIN EN ISO 52016-1:2018-04, Tabelle B.19
    """
    if klimazone == 'subpolar':
        return DELTA_THETA_SKY_SUBPOLAR
    elif klimazone == 'tropen':
        return DELTA_THETA_SKY_TROPEN
    else:
        return DELTA_THETA_SKY_ZWISCHEN


# ============================================================================
# KERNBERECHNUNG - MATRIXAUFBAU
# ============================================================================

def baue_zonenmatrix(zone: Zone, theta_e: float, I_sol_dict: Dict[str, float],
                     randbedingungen: Dict[str, Randbedingung],
                     nachbar_temps: Dict[str, float],
                     optionen: SimulationsOptionen,
                     nutzung: Nutzungsprofil, stunde_tag: int,
                     stunde_jahr: int,  # NEU für Erdreichberechnung
                     Phi_HC: float = 0.0,
                     I_sol_dir_dict: Dict[str, float] = None,  # Direktstrahlung
                     I_sol_dif_dict: Dict[str, float] = None,  # Diffusstrahlung
                     theta_i_vorher: float = 20.0  # Innentemperatur der vorherigen Stunde
                     ) -> Tuple[np.ndarray, np.ndarray, List[int]]:
    """
    Baut die Systemmatrix A·X=B für eine thermische Zone auf.
    
    Args:
        zone: Zone mit Bauteilen und geometrischen Daten
        theta_e: Außenlufttemperatur [°C]
        I_sol_dict: Solare Einstrahlung pro Orientierung [W/m²]
        randbedingungen: Dict mit Randbedingungen (Erdreich, etc.)
        nachbar_temps: Temperaturen benachbarter Zonen [°C]
        optionen: Simulationsoptionen
        nutzung: Nutzungsprofil mit Solltemperaturen und Gewinnen
        stunde_tag: Stunde innerhalb des Tages (0-23)
        stunde_jahr: Stunde im Jahr (0-8759)
        Phi_HC: Heiz-/Kühlleistung [W], positiv=Heizen
        I_sol_dir_dict: Direktstrahlung pro Orientierung [W/m²]
        I_sol_dif_dict: Diffusstrahlung pro Orientierung [W/m²]
    
    Returns:
        Tuple (A, B, knoten_indices):
        - A: Koeffizientenmatrix [n×n]
        - B: Rechte-Seite-Vektor [n]
        - knoten_indices: Zuordnung Knoten zu Bauteilen
    
    Reference:
        DIN EN ISO 52016-1:2018-04, Abschnitt 6.5, Gleichungen 38-42
    """
    n_knoten_bt = sum(bt.n_knoten for bt in zone.bauteile)
    n_gesamt = n_knoten_bt + 1
    
    A = np.zeros((n_gesamt, n_gesamt))
    B = np.zeros(n_gesamt)
    
    h = stunde_tag % 24
    Phi_int = nutzung.interne_gewinne_W[h]
    # Optionales zweites Quellprofil (Default 0)
    Phi_int2 = (nutzung.interne_gewinne_2_W[h]
                if nutzung.interne_gewinne_2_W is not None else 0.0)
    f_int2_c = nutzung.f_int_2_konv
    n_ach = nutzung.luftwechsel_1_h[h] if isinstance(nutzung.luftwechsel_1_h, list) else nutzung.luftwechsel_1_h
    f_int_c = nutzung.f_int_konv
    f_sol_c = optionen.f_sol_konv
    f_HC_c = optionen.f_HC_konv
    
    # ========================================================================
    # LÜFTUNGSLOGIK
    # ========================================================================
    
    if nutzung.lueftung_modus == "din4108":
        # ====================================================================
        # DIN 4108-2 TEMPERATURGESTEUERTE LÜFTUNG
        # ====================================================================
        # Erhöhte Taglüftung: wenn θ_i > 23°C UND θ_i > θ_e (während Aufenthalt)
        # Nachtlüftung: wenn θ_i > θ_heiz UND θ_i > θ_e (außerhalb Aufenthalt)
        # ====================================================================
        
        ist_aufenthaltszeit = h in nutzung.aufenthaltszeit_stunden
        ist_nachtzeit = h in nutzung.nachtlueftung_stunden
        theta_heiz = nutzung.heizen_C[h]
        
        if ist_aufenthaltszeit:
            # Erhöhte Taglüftung: n = 3.0 wenn θ_i > 23 UND θ_i > θ_e
            if theta_i_vorher > 23.0 and theta_i_vorher > theta_e:
                n_ach = nutzung.taglueftung_erhoht_ach  # Default 3.0
        
        elif ist_nachtzeit and nutzung.nachtlueftung_aktiv:
            # Nachtlüftung: zusätzlich wenn θ_i > θ_heiz UND θ_i > θ_e
            if theta_i_vorher > theta_heiz and theta_i_vorher > theta_e:
                n_ach = n_ach + nutzung.nachtlueftung_ach
    
    else:
        # ====================================================================
        # ZEITGESTEUERTE LÜFTUNG (BESTEST 650/950)
        # ====================================================================
        # BESTEST Case 650 Spezifikation (ASHRAE 140, Section 5.2.2.1.5):
        # - Zeitplan: 18:00-07:00 ON, 07:00-18:00 OFF
        # - Volumenstrom: 1703.16 m³/h ZUSÄTZLICH zur Infiltration
        # - ACH ohne Höhenkorrektur: ~10.8 ACH (Table 5-160)
        # 
        # WICHTIG: KEINE Temperatursteuerung! Rein zeitgesteuert.
        # "Case 650 = Ventilator nach Uhr, nicht nach Hirn"
        # Jede temperaturabhängige Logik wäre NICHT ASHRAE-140-konform.
        if nutzung.nachtlueftung_aktiv:
            richtige_stunde = h in nutzung.nachtlueftung_stunden
            
            if richtige_stunde:
                # ZUSÄTZLICH zur Basis-Infiltration (0.5 ACH bleibt aktiv)
                n_ach = n_ach + nutzung.nachtlueftung_ach
    
    # Δθ_sky: expliziter Optionswert hat Vorrang, sonst nach Klimazone (Tab. B.19)
    if optionen.delta_theta_sky_K is not None:
        delta_theta_sky = optionen.delta_theta_sky_K
    else:
        delta_theta_sky = berechne_delta_theta_sky(optionen.klimazone)
    
    # Lüftungsleitwert (ρ_a·c_a nach Tab. 20; Höhenkorrektur nur bei
    # gesetzter Standorthöhe)
    rho = RHO_LUFT
    if optionen.standort_hoehe_m is not None:
        rho = RHO_LUFT * hoehenfaktor_luftdichte(optionen.standort_hoehe_m)
    H_ve = zone.volumen_m3 * n_ach * rho * C_LUFT / 3600
    
    # Solare Gewinne durch transparente Bauteile
    # NORMKONFORM nach ISO 52016-1: F_sh_dir wird STÜNDLICH aus Geometrie berechnet!
    Phi_sol = 0.0
    tag = stunde_jahr // 24 + 1
    std = stunde_jahr % 24
    
    for bt in zone.bauteile:
        if bt.typ == 'transparent':
            key = _bt_orientierungs_key(bt, I_sol_dict)  # exakt o. Raster
            
            # ============================================================
            # F_sh_dir: Stündlich aus Geometrie berechnen (NORMKONFORM!)
            # Kombiniert Überhang UND Fins (multiplikativ)
            # ============================================================
            F_sh = 1.0
            
            # Azimut in ISO-Konvention umrechnen
            # BESTEST: Nord=0, Ost=90, Süd=180, West=270
            # ISO:     Süd=0, Ost=+90, West=-90, Nord=±180
            azimut_iso = 180 - bt.azimut_deg
            if azimut_iso > 180:
                azimut_iso -= 360
            elif azimut_iso < -180:
                azimut_iso += 360
            
            # 1. Überhang-Verschattung
            if bt.ueberhang_tiefe_m > 0:
                F_sh_ovh = berechne_F_sh_ueberhang_stuendlich(
                    stunde=std, tag=tag, standort=optionen.standort,
                    azimut_iso=azimut_iso,
                    H_fenster=bt.fenster_hoehe_m,
                    D_ovh=bt.ueberhang_tiefe_m,
                    L_ovh=bt.ueberhang_abstand_m
                )
                F_sh *= F_sh_ovh
            
            # 2. Fin-Verschattung (seitliche Lamellen)
            if bt.fin_tiefe_m > 0:
                F_sh_fin = berechne_F_sh_fin_stuendlich(
                    stunde=std, tag=tag, standort=optionen.standort,
                    azimut_iso=azimut_iso,
                    W_fenster=bt.fenster_breite_m,
                    D_fin=bt.fin_tiefe_m,
                    G_fin=bt.fin_abstand_m
                )
                F_sh *= F_sh_fin
            
            # 3. Fallback auf vorberechnete oder konstante Werte
            if bt.ueberhang_tiefe_m <= 0 and bt.fin_tiefe_m <= 0:
                if bt.F_sh_stundenwerte is not None and stunde_jahr < len(bt.F_sh_stundenwerte):
                    # Fallback: Vorberechnete stündliche Werte
                    F_sh = bt.F_sh_stundenwerte[stunde_jahr]
                else:
                    # Fallback: Konstanter Wert (NICHT normkonform!)
                    F_sh = bt.F_sh_obst
            
            # 4. Horizontverschattung: wirkt IMMER zusätzlich
            # multiplikativ auf den Direktanteil (Konvention: wer eigene
            # F_sh_stundenwerte inkl. Horizont liefert, lässt
            # horizont_winkel_deg auf 0, sonst Doppelzählung).
            if bt.horizont_winkel_deg > 0:
                F_sh *= berechne_F_sh_horizont_stuendlich(
                    std, tag, optionen.standort, bt.horizont_winkel_deg)
            
            # Direkt/Diffus getrennt behandeln
            if I_sol_dir_dict and I_sol_dif_dict:
                # Direkt/Diffus-Trennung verfügbar
                I_dir = I_sol_dir_dict.get(key, 0.0)
                I_dif = I_sol_dif_dict.get(key, 0.0)
                
                # ============================================================
                # Diffusverschattung nach ISO 52016-1
                # ============================================================
                # Anhang F Verfahren 1: Verschattung nur auf Direktanteil,
                # F_sh,dif = 1.0 fest. Begründung: Vom Gelände reflektierte
                # Strahlung kompensiert die blockierte diffuse Himmels-
                # strahlung (ISO 52016-1, 6.5.13). Kein Eingabeparameter —
                # F_sh_obst_dif wurde als wirkungsloser Parameter entfernt
                # (Doppelstruktur bewusst entfernt).
                # ============================================================
                F_sh_dif = 1.0
                
                I_sol_eff = I_dir * F_sh + I_dif * F_sh_dif
            else:
                # Fallback: Alte Methode (Verschattung auf Gesamtstrahlung)
                I_sol = I_sol_dict.get(key, 0.0)
                I_sol_eff = I_sol * F_sh
            
            A_sol = bt.flaeche_m2 * (1 - bt.rahmenanteil)
            
            # ================================================================
            # SONNENSCHUTZ (DIN 4108-2)
            # ================================================================
            # Steuerung: "statisch", "manuell", "automatik"
            # Grenzwerte: "norm" (WG/NWG abhängig), "eigene"
            # Manuell + NWG + Wochenende → Fc=1.0 (niemand da)
            # Automatik → immer aktiv wenn I > Schwelle
            # ================================================================
            
            # Rückwärtskompatibilität: alte Modi auf neue Parameter mappen
            steuerung = bt.sonnenschutz_steuerung
            if bt.sonnenschutz_modus != "statisch" and steuerung == "statisch":
                # Alte Modi konvertieren
                if bt.sonnenschutz_modus == "automatik_wg":
                    steuerung = "automatik"
                    bt.ist_nwg = False
                elif bt.sonnenschutz_modus == "automatik_nwg":
                    steuerung = "automatik"
                    bt.ist_nwg = True
            
            if steuerung == "statisch":
                # Statischer Modus: g_wert bereits mit Fc multipliziert
                g_eff = bt.g_wert
            else:
                # Manuell oder Automatik: Fc abhängig von Einstrahlung
                
                # Wochentag bestimmen (Simulation startet 1.1. = Montag)
                tag_im_jahr = stunde_jahr // 24
                wochentag = tag_im_jahr % 7  # 0=Mo, 1=Di, ..., 5=Sa, 6=So
                ist_wochenende = wochentag >= 5
                
                # Schwellenwert bestimmen
                if bt.sonnenschutz_grenzwerte == "eigene":
                    # Eigene Schwelle für alle Richtungen gleich
                    schwelle = bt.sonnenschutz_schwelle_eigene
                else:
                    # Norm-Grenzwerte nach DIN 4108-2
                    # Nord-Bereich: 315°-45° (±45° um Nord=0°)
                    ist_nord = bt.azimut_deg <= 45 or bt.azimut_deg >= 315
                    
                    if bt.ist_nwg:
                        # NWG: 200 W/m² (O,S,W), 150 W/m² (Nord)
                        schwelle = 150.0 if ist_nord else 200.0
                    else:
                        # WG: 300 W/m² (O,S,W), 200 W/m² (Nord)
                        schwelle = 200.0 if ist_nord else 300.0
                
                # Wochenende-Logik nur bei Manuell + NWG
                wochenende_inaktiv = (steuerung == "manuell" and bt.ist_nwg)
                
                # Einstrahlung prüfen (I_dir + I_dif senkrecht zum Fenster)
                I_total = I_sol_eff  # Bereits F_sh berücksichtigt
                
                if ist_wochenende and wochenende_inaktiv:
                    # NWG Wochenende bei manueller Steuerung: niemand da → Fc=1.0
                    Fc = bt.Fc_offen
                elif I_total > schwelle:
                    # Schwelle überschritten → Sonnenschutz aktiv
                    Fc = bt.Fc_aktiviert
                else:
                    # Schwelle nicht überschritten → Sonnenschutz offen
                    Fc = bt.Fc_offen
                
                g_eff = bt.g_wert_basis * Fc
            
            Phi_sol += I_sol_eff * A_sol * g_eff * bt.F_w
    
    idx = 0
    knoten_indices = []
    
    # ========================================================================
    # BAUTEIL-GLEICHUNGEN (39-42)
    # ========================================================================
    
    for bt in zone.bauteile:
        knoten_indices.append(idx)
        A_el = bt.flaeche_m2
        
        rb = randbedingungen.get(bt.zone_aussen)
        ist_adiabat = (rb is not None and rb.typ == 'adiabatisch')
        ist_nachbar = (rb is not None and rb.typ == 'nachbarzone')
        ist_erdreich = (rb is not None and rb.typ == 'erdreich')
        
        # Außentemperatur für dieses Bauteil
        if ist_adiabat or ist_nachbar:
            # Gl. (42) / 6.5.6.3.7 Standardweg:
            # interne Trennwand mit adiabater Mittelebene — KEINE
            # Außenkopplung; theta_aussen ist in diesem Zweig ungenutzt.
            # Die frühere sequenzielle Nachbartemperatur-Kopplung
            # (normfremd) entfällt im Standardweg; die
            # Anhang-D.2-Kopplung ist dokumentierte Ausbaustufe
            # (nachbar_temps bleibt dafür in der Signatur).
            theta_aussen = 0.0
        elif ist_erdreich:
            if bt.theta_gr_vi_monat is not None:
                # Gl.-48-Knotenmodell: monatliche virtuelle
                # Erdreichtemperatur θ_gr;vi;m (Gl. 49/F.2)
                theta_aussen = bt.theta_gr_vi_monat[
                    _MONAT_JE_STUNDE[stunde_jahr]]
            else:
                # Altmodell (sinus_direkt): Sinustemperatur über
                # normale h_ce/h_re-Kopplung
                theta_aussen = berechne_erdreich_temperatur(rb, stunde_jahr)
        else:
            theta_aussen = theta_e
        
        key = _bt_orientierungs_key(bt, I_sol_dict)  # exakt o. Raster
        I_sol_bt = I_sol_dict.get(key, 0.0)
        
        if bt.typ == 'opak':
            for i in range(bt.n_knoten):
                row = idx + i
                kappa_i = bt.kappa_pl[i] * A_el
                
                if i == 0:
                    # Gleichung 41: Äußerer Knoten
                    if ist_adiabat or ist_nachbar:
                        # Gl. (42): h_ce = h_re = 0, a_sol = 0,
                        # Φ_sky = 0 (interne Trennwand, adiabate
                        # Mittelebene; für nachbarzone der
                        # 6.5.6.3.7-Standardweg). EINGABE-
                        # KONVENTION: R_c und κ_m dieser Elemente
                        # gelten BIS ZUR MITTELEBENE (halbe
                        # Konstruktion), vgl. 6.5.6.3.6.
                        h_innen = bt.h_pl[0] * A_el
                        A[row, row] = kappa_i / (DELTA_T/3600) + h_innen
                        A[row, row+1] = -h_innen
                        B[row] = kappa_i / (DELTA_T/3600) * bt.theta_pl[i]
                    else:
                        h_ce = bt.h_ce * A_el
                        h_re = bt.h_re * A_el
                        h_innen = bt.h_pl[0] * A_el
                        
                        A[row, row] = kappa_i / (DELTA_T/3600) + h_ce + h_re + h_innen
                        A[row, row+1] = -h_innen
                        
                        # ====================================================
                        # Solare Absorption nach Gl. (41), 6.5.6.3.5:
                        # a_sol * (I_dif + I_dir * F_sh,obst) — Verschattung
                        # nur auf den Direktanteil, Diffusanteil (inkl. Boden-
                        # reflexion) unverschattet. Am Seitenbild verifiziert
                        # 22.07.2026; deckungsgleich mit Anhang F.1 a)/b)
                        # (Verfahren 1); gilt auch für opake Flächen.
                        # Fallback ohne Kanaltrennung: alte Näherung
                        # Gesamtstrahlung * F_sh (nur wenn dir/dif-Dicts
                        # fehlen; analog Fensterpfad).
                        # ====================================================
                        # Horizont blockiert auch hier nur den
                        # Direktanteil (Gl. (41) i. V. m. Anhang F).
                        F_hor_bt = (berechne_F_sh_horizont_stuendlich(
                                        std, tag, optionen.standort,
                                        bt.horizont_winkel_deg)
                                    if bt.horizont_winkel_deg > 0 else 1.0)
                        if I_sol_dir_dict and I_sol_dif_dict:
                            I_sol_eff_bt = (I_sol_dir_dict.get(key, 0.0)
                                            * bt.F_sh_obst_dir * F_hor_bt
                                            + I_sol_dif_dict.get(key, 0.0))
                        else:
                            I_sol_eff_bt = I_sol_bt * bt.F_sh_obst_dir * F_hor_bt
                        Phi_sol_abs = bt.alpha_sol * I_sol_eff_bt * A_el
                        
                        # Himmelsstrahlung nach ISO 52016-1 Gl. (70): Phi_sky = F_sky * h_re * delta_theta_sky
                        # (h_re enthaelt epsilon bereits gemaess 6.5.8 - kein separater epsilon-Faktor!)
                        Phi_sky = bt.h_re * A_el * bt.F_sky * delta_theta_sky
                        
                        # Für Erdreich: keine Himmelsstrahlung
                        if ist_erdreich:
                            Phi_sky = 0.0
                            Phi_sol_abs = 0.0
                        
                        B[row] = (kappa_i / (DELTA_T/3600) * bt.theta_pl[i]
                                 + (h_ce + h_re) * theta_aussen
                                 + Phi_sol_abs
                                 - Phi_sky)
                
                elif i == bt.n_knoten - 1:
                    # Gleichung 39: Innerer Knoten
                    h_aussen = bt.h_pl[i-1] * A_el
                    h_ci = bt.h_ci * A_el
                    h_ri = bt.h_ri * A_el
                    
                    A_self_ratio = A_el / zone.A_tot
                    h_ri_eff = h_ri * (1 - A_self_ratio)
                    
                    A[row, row] = kappa_i / (DELTA_T/3600) + h_aussen + h_ci + h_ri_eff
                    A[row, row-1] = -h_aussen
                    A[row, n_gesamt-1] = -h_ci
                    
                    idx_temp = 0
                    for bt2 in zone.bauteile:
                        if bt2.id != bt.id:
                            inner_idx = idx_temp + bt2.n_knoten - 1
                            A_ratio = bt2.flaeche_m2 / zone.A_tot
                            A[row, inner_idx] = -h_ri * A_ratio
                        idx_temp += bt2.n_knoten
                    
                    Phi_rad_anteil = ((1 - f_int_c) * Phi_int 
                                     + (1 - f_int2_c) * Phi_int2
                                     + (1 - f_sol_c) * Phi_sol
                                     + (1 - f_HC_c) * Phi_HC) * A_el / zone.A_tot
                    
                    B[row] = (kappa_i / (DELTA_T/3600) * bt.theta_pl[i]
                             + Phi_rad_anteil)
                
                else:
                    # Gleichung 40: Innere Knoten
                    h_aussen = bt.h_pl[i-1] * A_el
                    h_innen = bt.h_pl[i] * A_el
                    
                    A[row, row] = kappa_i / (DELTA_T/3600) + h_aussen + h_innen
                    A[row, row-1] = -h_aussen
                    A[row, row+1] = -h_innen
                    
                    B[row] = kappa_i / (DELTA_T/3600) * bt.theta_pl[i]
        
        else:
            # Transparentes Bauteil: 2 Knoten
            # Knotenleitwert nach ISO 52016-1 Gl. (51)+(53) aus _berechne_leitwerte_transparent
            h_U = bt.h_pl[0] * A_el
            
            row = idx
            if ist_adiabat or ist_nachbar:
                # Gl. (42) analog für transparente Trennwand-Elemente
                # (Gl. 42); Eingabekonvention Mittelebene s. o.
                A[row, row] = h_U
                A[row, row+1] = -h_U
                B[row] = 0
            else:
                h_ce = bt.h_ce * A_el
                h_re = bt.h_re * A_el
                
                # Himmelsstrahlung nach ISO 52016-1 Gl. (70) - gilt auch fuer verglaste
                # Elemente (Aussenknoten-Gleichung, 6.5.6.3.3); Phi_sky = 0 nur fuer Erdreich (6.5.8)
                Phi_sky = bt.h_re * A_el * bt.F_sky * delta_theta_sky
                if ist_erdreich:
                    Phi_sky = 0.0
                
                A[row, row] = h_ce + h_re + h_U
                A[row, row+1] = -h_U
                B[row] = (h_ce + h_re) * theta_aussen - Phi_sky
            
            row = idx + 1
            h_ci = bt.h_ci * A_el
            h_ri = bt.h_ri * A_el
            
            A_self_ratio = A_el / zone.A_tot
            h_ri_eff = h_ri * (1 - A_self_ratio)
            
            A[row, row] = h_U + h_ci + h_ri_eff
            A[row, row-1] = -h_U
            A[row, n_gesamt-1] = -h_ci
            
            idx_temp = 0
            for bt2 in zone.bauteile:
                if bt2.id != bt.id:
                    inner_idx = idx_temp + bt2.n_knoten - 1
                    A_ratio = bt2.flaeche_m2 / zone.A_tot
                    A[row, inner_idx] = -h_ri * A_ratio
                idx_temp += bt2.n_knoten
            
            Phi_rad_anteil = ((1 - f_int_c) * Phi_int 
                             + (1 - f_int2_c) * Phi_int2
                             + (1 - f_sol_c) * Phi_sol
                             + (1 - f_HC_c) * Phi_HC) * A_el / zone.A_tot
            
            B[row] = Phi_rad_anteil
        
        idx += bt.n_knoten
    
    # ========================================================================
    # GLEICHUNG 38: Luftknoten (letzte Zeile) - NEU mit Wärmebrücken
    # ========================================================================
    
    row = n_gesamt - 1
    
    sum_h_ci_A = sum(bt.h_ci * bt.flaeche_m2 for bt in zone.bauteile)
    
    # Wärmebrücken-Koeffizient H_tb hinzufügen
    H_tb = zone.H_tb
    
    # Diagonaleintrag mit Wärmebrücken
    A[row, row] = zone.C_int / (DELTA_T/3600) + sum_h_ci_A + H_ve + H_tb
    
    # Kopplung zu Oberflächenknoten
    idx = 0
    for bt in zone.bauteile:
        inner_idx = idx + bt.n_knoten - 1
        A[row, inner_idx] = -bt.h_ci * bt.flaeche_m2
        idx += bt.n_knoten
    
    # Rechte Seite mit Wärmebrücken
    Phi_konv = (f_int_c * Phi_int 
               + f_int2_c * Phi_int2
               + f_sol_c * Phi_sol
               + f_HC_c * Phi_HC)
    
    B[row] = (zone.C_int / (DELTA_T/3600) * zone.theta_air
             + H_ve * theta_e
             + H_tb * theta_e  # Wärmebrücken mit Außentemperatur
             + Phi_konv)
    
    return A, B, knoten_indices


# ============================================================================
# KERNBERECHNUNG - 5-STUFEN-VERFAHREN
# ============================================================================

def _solve_zonenmatrix(A, B, zone_id: str, stunde_jahr: int):
    """np.linalg.solve mit lauter Fehlerbehandlung.

    Ein singuläres A ist IMMER ein Modellfehler; der frühere stille
    Fallback (alle Knoten 20 °C) korrumpierte Ergebnisse unbemerkt.
    """
    try:
        return np.linalg.solve(A, B)
    except np.linalg.LinAlgError as exc:
        raise RuntimeError(
            f"Zonenmatrix der Zone '{zone_id}' ist singulär "
            f"(Stunde {stunde_jahr}): {exc}. Modell prüfen — "
            f"kein stiller 20-°C-Fallback.") from exc


def fuenf_stufen_verfahren(zone: Zone, theta_e: float, I_sol_dict: Dict[str, float],
                           randbedingungen: Dict[str, Randbedingung],
                           nachbar_temps: Dict[str, float],
                           optionen: SimulationsOptionen,
                           nutzung: Nutzungsprofil, stunde_tag: int,
                           stunde_jahr: int,
                           Phi_H_max: float = 1e6,
                           Phi_C_max: float = -1e6,
                           I_sol_dir_dict: Dict[str, float] = None,
                           I_sol_dif_dict: Dict[str, float] = None,
                           theta_i_vorher: float = 20.0) -> Tuple[float, float, float, float]:
    """
    5-Stufen-Verfahren zur Bestimmung der Heiz-/Kühllasten.
    
    Ermittelt ob Heizen/Kühlen nötig ist und berechnet die erforderliche
    Leistung um die Solltemperatur zu halten.
    
    Args:
        zone: Thermische Zone
        theta_e: Außenlufttemperatur [°C]
        I_sol_dict: Solare Einstrahlung pro Orientierung [W/m²]
        randbedingungen: Randbedingungen (Erdreich, Nachbarzonen)
        nachbar_temps: Temperaturen benachbarter Zonen [°C]
        optionen: Simulationsoptionen
        nutzung: Nutzungsprofil mit Solltemperaturen
        stunde_tag: Stunde im Tag (0-23)
        stunde_jahr: Stunde im Jahr (0-8759)
        Phi_H_max: Maximale Heizleistung [W]
        Phi_C_max: Maximale Kühlleistung [W], negativ
        I_sol_dir_dict: Direktstrahlung [W/m²]
        I_sol_dif_dict: Diffusstrahlung [W/m²]
    
    Returns:
        Tuple (theta_op, theta_air, Phi_H, Phi_C):
        - theta_op: Operative Temperatur [°C]
        - theta_air: Raumlufttemperatur [°C]
        - Phi_H: Heizleistung [W], ≥0
        - Phi_C: Kühlleistung [W], ≤0
        (Aufrufer verwenden diese Reihenfolge.)
    
    Reference:
        DIN EN ISO 52016-1:2018-04, Abschnitt 6.5.5.2
    """
    h = stunde_tag % 24
    theta_set_H = nutzung.heizen_C[h]
    theta_set_C = nutzung.kuehlen_C[h]
    
    # SCHRITT 1: Freischwingtemperatur
    A, B, knoten_idx = baue_zonenmatrix(
        zone, theta_e, I_sol_dict, randbedingungen, nachbar_temps,
        optionen, nutzung, stunde_tag, stunde_jahr, Phi_HC=0.0,
        I_sol_dir_dict=I_sol_dir_dict, I_sol_dif_dict=I_sol_dif_dict,
        theta_i_vorher=theta_i_vorher
    )
    
    X = _solve_zonenmatrix(A, B, zone.id, stunde_jahr)
    
    theta_air_0 = X[-1]
    
    A_gewichtet = 0.0
    theta_rad_sum = 0.0
    idx = 0
    for bt in zone.bauteile:
        theta_surface = X[idx + bt.n_knoten - 1]
        theta_rad_sum += theta_surface * bt.flaeche_m2
        A_gewichtet += bt.flaeche_m2
        idx += bt.n_knoten
    
    theta_rad_0 = theta_rad_sum / max(A_gewichtet, 1.0)
    theta_op_0 = 0.5 * (theta_air_0 + theta_rad_0)
    
    # Regelgröße: θ_air (VDI 6020) oder θ_op (ISO 52016)
    theta_ctrl_0 = theta_air_0 if nutzung.regelung_nach_luft else theta_op_0
    
    if theta_set_H <= theta_ctrl_0 <= theta_set_C:
        _update_zone_temps(zone, X, knoten_idx)
        return theta_op_0, theta_air_0, 0.0, 0.0
    
    # SCHRITT 2: Unbeschränkte Last
    Phi_test = 10000.0
    
    if theta_ctrl_0 < theta_set_H:
        theta_set = theta_set_H
        
        A_test, B_test, _ = baue_zonenmatrix(
            zone, theta_e, I_sol_dict, randbedingungen, nachbar_temps,
            optionen, nutzung, stunde_tag, stunde_jahr, Phi_HC=Phi_test,
            I_sol_dir_dict=I_sol_dir_dict, I_sol_dif_dict=I_sol_dif_dict,
            theta_i_vorher=theta_i_vorher
        )
        
        X_test = _solve_zonenmatrix(A_test, B_test, zone.id, stunde_jahr)
        
        theta_air_test = X_test[-1]
        idx = 0
        theta_rad_sum = 0.0
        for bt in zone.bauteile:
            theta_rad_sum += X_test[idx + bt.n_knoten - 1] * bt.flaeche_m2
            idx += bt.n_knoten
        theta_rad_test = theta_rad_sum / max(A_gewichtet, 1.0)
        theta_op_test = 0.5 * (theta_air_test + theta_rad_test)
        theta_ctrl_test = theta_air_test if nutzung.regelung_nach_luft else theta_op_test
        
        if abs(theta_ctrl_test - theta_ctrl_0) > 0.001:
            Phi_un = Phi_test * (theta_set - theta_ctrl_0) / (theta_ctrl_test - theta_ctrl_0)
        else:
            Phi_un = 0.0
        
        Phi_H = min(Phi_un, Phi_H_max)
        Phi_C = 0.0
        
    else:
        theta_set = theta_set_C
        
        A_test, B_test, _ = baue_zonenmatrix(
            zone, theta_e, I_sol_dict, randbedingungen, nachbar_temps,
            optionen, nutzung, stunde_tag, stunde_jahr, Phi_HC=-Phi_test,
            I_sol_dir_dict=I_sol_dir_dict, I_sol_dif_dict=I_sol_dif_dict,
            theta_i_vorher=theta_i_vorher
        )
        
        X_test = _solve_zonenmatrix(A_test, B_test, zone.id, stunde_jahr)
        
        theta_air_test = X_test[-1]
        idx = 0
        theta_rad_sum = 0.0
        for bt in zone.bauteile:
            theta_rad_sum += X_test[idx + bt.n_knoten - 1] * bt.flaeche_m2
            idx += bt.n_knoten
        theta_rad_test = theta_rad_sum / max(A_gewichtet, 1.0)
        theta_op_test = 0.5 * (theta_air_test + theta_rad_test)
        theta_ctrl_test = theta_air_test if nutzung.regelung_nach_luft else theta_op_test
        
        if abs(theta_ctrl_test - theta_ctrl_0) > 0.001:
            Phi_un = -Phi_test * (theta_ctrl_0 - theta_set) / (theta_ctrl_0 - theta_ctrl_test)
        else:
            Phi_un = 0.0
        
        Phi_C = max(Phi_un, Phi_C_max)
        Phi_H = 0.0
    
    # SCHRITT 4 & 5: Endgültige Temperaturen
    Phi_HC = Phi_H + Phi_C
    
    A_final, B_final, knoten_idx = baue_zonenmatrix(
        zone, theta_e, I_sol_dict, randbedingungen, nachbar_temps,
        optionen, nutzung, stunde_tag, stunde_jahr, Phi_HC=Phi_HC,
        I_sol_dir_dict=I_sol_dir_dict, I_sol_dif_dict=I_sol_dif_dict,
        theta_i_vorher=theta_i_vorher
    )
    
    X_final = _solve_zonenmatrix(A_final, B_final, zone.id, stunde_jahr)
    
    theta_air = X_final[-1]
    
    idx = 0
    theta_rad_sum = 0.0
    for bt in zone.bauteile:
        theta_rad_sum += X_final[idx + bt.n_knoten - 1] * bt.flaeche_m2
        idx += bt.n_knoten
    theta_rad = theta_rad_sum / max(A_gewichtet, 1.0)
    theta_op = 0.5 * (theta_air + theta_rad)
    
    _update_zone_temps(zone, X_final, knoten_idx)
    
    return theta_op, theta_air, max(0, Phi_H), min(0, Phi_C)


def _update_zone_temps(zone: Zone, X: np.ndarray, knoten_idx: List[int]):
    """
    Aktualisiert Temperaturen in Zone und Bauteilen nach Matrixlösung.
    
    Args:
        zone: Zone deren Temperaturen aktualisiert werden
        X: Lösungsvektor aus np.linalg.solve
        knoten_idx: Zuordnung Knotenindex zu Bauteilen
    """
    zone.theta_air = X[-1]
    
    for i, bt in enumerate(zone.bauteile):
        start = knoten_idx[i] if i < len(knoten_idx) else 0
        for j in range(bt.n_knoten):
            if start + j < len(X) - 1:
                bt.theta_pl[j] = X[start + j]
    
    A_tot = sum(bt.flaeche_m2 for bt in zone.bauteile)
    theta_rad = sum(bt.theta_pl[-1] * bt.flaeche_m2 for bt in zone.bauteile) / max(A_tot, 1)
    zone.theta_rad_mean = theta_rad
    zone.theta_op = 0.5 * (zone.theta_air + theta_rad)


# ============================================================================
# HAUPTSIMULATION
# ============================================================================

def bereite_erdreich_vor(gebaeude: "Gebaeude", klima: Klimadaten,
                         optionen: SimulationsOptionen) -> None:
    """Bereitet alle ERD-Bauteile auf das
    normeigene Knotenmodell vor (Gl. 48–50 der ISO 52016-1 mit
    Parametern nach ISO 13370, Lesart A / M4).

    θ̄int-Bestimmung: Default ist das 24-h-Mittel des
    Heiz-Sollwertprofils der Zone (monatlich konstant ⇒ der
    H_pi-Term der Gl. (C.4) entfällt, wie C.3 Anm. 3 es für
    konstante Innentemperatur vorsieht). Die Gleichsetzung
    Soll ≈ Ist ist eine SETZUNG, die für geregelte Zonen trägt;
    für frei schwingende Zonen ist sie ungeeignet (Fangfall unten).

    Freilauf-Fangfall (dokumentierte Schutzregel): enthält das
    Heiz-Sollprofil Platzhalter (< −50 °C, z. B. −999/Anlage aus),
    ist dessen Mittel unbrauchbar — dann ist theta_int_mittel_C
    faktisch Pflicht; ohne Angabe greift der dokumentierte Fallback
    20 °C MIT Log-Hinweis.

    Ψ_wf-Default 0: gemäß Anmerkung zu Gl. (F.2) wird die
    Wand/Boden-Randwärmebrücke im dynamischen Modell als normale
    lineare Wärmebrücke geführt (waermebruecken-Eingabe), nicht im
    Erdelement.
    """
    if optionen.erdreich_modell == "sinus_direkt":
        hat_erd = any(bt.zone_aussen == 'ERD'
                      for z in gebaeude.zonen.values()
                      for bt in z.bauteile)
        if hat_erd:
            print("  Erdreich: Altmodell 'sinus_direkt' aktiv "
                  "(dokumentierter Schalter; Normmodell = "
                  "'knotenmodell').")
        return
    if optionen.erdreich_modell != "knotenmodell":
        raise ValueError(
            f"Unbekanntes erdreich_modell "
            f"'{optionen.erdreich_modell}' (knotenmodell|sinus_direkt).")

    # Monatsmittel der Außentemperatur aus den Klimadaten
    n = min(klima.n_stunden, 8760)
    theta_e_monat = []
    start = 0
    for tage in _MONATSTAGE:
        ende = min(start + tage * 24, n)
        if ende > start:
            theta_e_monat.append(
                float(sum(klima.theta_e[start:ende]) / (ende - start)))
        else:
            theta_e_monat.append(float(klima.theta_e[n - 1]))
        start = ende

    for zone in gebaeude.zonen.values():
        profil = gebaeude.nutzungsprofile.get(zone.nutzungsprofil)
        for bt in zone.bauteile:
            if bt.zone_aussen != 'ERD':
                continue
            ed = bt.erdreich_daten or {}

            # --- θ_int,m bestimmen -------------------------------
            if ed.get('theta_int_monat') is not None:
                ti_monat = [float(v) for v in ed['theta_int_monat']]
                if len(ti_monat) != 12:
                    raise ValueError(
                        f"Bauteil '{bt.id}': theta_int_monat braucht "
                        f"12 Werte.")
            elif ed.get('theta_int_mittel_C') is not None:
                ti_monat = [float(ed['theta_int_mittel_C'])] * 12
            else:
                heiz = profil.heizen_C if profil else None
                if heiz and all(v > -50.0 for v in heiz):
                    # geregelte Zone: 24-h-Mittel, log-frei
                    ti_monat = [sum(heiz) / len(heiz)] * 12
                else:
                    ti_monat = [20.0] * 12
                    warnings.warn(
                        f"Erdreich-Bauteil '{bt.id}': Heiz-Sollprofil "
                        f"enthält Platzhalter/fehlt (Freilauf?) — "
                        f"θ̄int-Fallback 20 °C aktiv. Für belastbare "
                        f"θ_gr;vi;m 'theta_int_mittel_C' im "
                        f"erdreich-Block setzen.")

            # --- Bodenkennwerte: volle 13370-Kette oder Fallback --
            if ed.get('perimeter_m') is not None:
                if ed.get('wanddicke_m') is None:
                    raise ValueError(
                        f"Bauteil '{bt.id}': erdreich.perimeter_m "
                        f"gesetzt, aber wanddicke_m fehlt — beide "
                        f"Geometriegrößen gehören zusammen (Gl. 3).")
                # Übergangswiderstände aus den (Tab.-25-)Koeffizienten
                # des Elements VOR der Umverdrahtung
                R_si = 1.0 / (bt.h_ci + bt.h_ri)
                R_se = 1.0 / (bt.h_ce + bt.h_re)
                params = berechne_erdreich_parameter(
                    flaeche_m2=bt.flaeche_m2,
                    perimeter_m=float(ed['perimeter_m']),
                    R_f_m2K_W=bt.R_c_m2K_W,
                    wanddicke_m=float(ed['wanddicke_m']),
                    R_si_m2K_W=R_si, R_se_m2K_W=R_se,
                    boden_kategorie=int(ed.get('boden_kategorie',
                                               BODEN_KATEGORIE_DEFAULT)),
                    lambda_g=ed.get('lambda_gr_W_mK'),
                    rho_c_g=ed.get('rho_c_gr_J_m3K'))
                if ed.get('theta_gr_vi_monat') is not None:
                    theta_vi = [float(v) for v in ed['theta_gr_vi_monat']]
                    if len(theta_vi) != 12:
                        raise ValueError(
                            f"Bauteil '{bt.id}': theta_gr_vi_monat "
                            f"braucht 12 Werte.")
                else:
                    theta_vi = berechne_theta_vi_monate(
                        params, bt.flaeche_m2, float(ed['perimeter_m']),
                        theta_e_monat, ti_monat,
                        psi_wf_W_mK=float(ed.get('psi_wf_W_mK', 0.0)))
                R_gr = params.R_g_m2K_W
                kappa_gr = params.kappa_gr_J_m2K
                R_vi = params.R_vi_m2K_W
            else:
                # Dokumentierter FALLBACK (Näherung, mit Log-Hinweis):
                # Kat.-2-Standardboden, R_gr;vi := R_gr, θ_gr;vi;m aus
                # dem Bestands-Sinus der ERD-Randbedingung.
                R_gr = 0.25          # 0,5 m / λ = 2,0 (Tab. 7 Kat. 2)
                kappa_gr = 1.0e6     # 0,5 m · 2,0e6 (Tab. 7 Kat. 2)
                R_vi = R_gr
                warnings.warn(
                    f"Erdreich-Bauteil '{bt.id}': keine Bodenkennwerte "
                    f"(erdreich.perimeter_m/wanddicke_m) — "
                    f"dokumentierter NÄHERUNGS-Fallback aktiv: "
                    f"Kat.-2-Boden, R_gr;vi := R_gr = 0,25 m²K/W "
                    f"(keine 13370-Ableitung möglich).")
                if ed.get('theta_gr_vi_monat') is not None:
                    theta_vi = [float(v) for v in ed['theta_gr_vi_monat']]
                    if len(theta_vi) != 12:
                        raise ValueError(
                            f"Bauteil '{bt.id}': theta_gr_vi_monat "
                            f"braucht 12 Werte.")
                else:
                    rb = gebaeude.randbedingungen.get('ERD')
                    tm = rb.temperatur_C if rb else THETA_GR_MEAN_DEFAULT
                    amp = rb.amplitude_K if rb else 3.0
                    ph = rb.phasenverschiebung_monate if rb else 1.0
                    theta_vi = theta_vi_fallback_sinus(tm, amp, ph)
                    warnings.warn(
                        f"Erdreich-Bauteil '{bt.id}': θ_gr;vi;m als "
                        f"NÄHERUNG aus dem Bestands-Sinus "
                        f"(Mittel {tm} °C, Amplitude {amp} K) — kein "
                        f"13370-Bezug).")

            bt.konfiguriere_erdreich_knotenmodell(R_gr, kappa_gr, R_vi)
            bt.theta_gr_vi_monat = theta_vi


def simuliere(gebaeude: Gebaeude, klima: Klimadaten, 
              optionen: SimulationsOptionen) -> Dict[str, Any]:
    """
    Führt die stündliche Jahressimulation durch.
    
    Berechnet für jede Stunde des Jahres die Heiz-/Kühllast aller Zonen
    mittels des 5-Stufen-Verfahrens nach ISO 52016-1.
    
    Args:
        gebaeude: Gebäude mit Zonen, Bauteilen und Randbedingungen
        klima: Klimadaten mit 8760 Stundenwerten
        optionen: Simulationsoptionen (Zeitraum, Ausgabe, etc.)
    
    Returns:
        Dictionary mit Ergebnissen:
        - 'projekt': Projektname
        - 'zonen': Dict mit Zonenergebnissen (Q_H, Q_C, Stundenwerte)
        - 'gesamt': Summen über alle Zonen [kWh/a]
    """
    print(f"Starte Simulation: {gebaeude.name}")
    print(f"  Zonen: {len(gebaeude.zonen)}")
    print(f"  Bauteile: {len(gebaeude.bauteile)}")
    print(f"  Wärmebrücken: {len(gebaeude.waermebruecken)}")
    print(f"  Klimadaten: {klima.n_stunden} Stunden")
    print()

    # Erdreich-Knotenmodell vorbereiten (Default; Altmodell
    # über optionen.erdreich_modell = "sinus_direkt")
    bereite_erdreich_vor(gebaeude, klima, optionen)
    
    ergebnisse = {
        'projekt': gebaeude.name,
        'timestamp': datetime.now().isoformat(),
        
        'zonen': {},
        'gesamt': {
            'Q_H_kWh': 0.0,
            'Q_C_kWh': 0.0,
            'Q_tb_kWh': 0.0  # Wärmebrückenverluste
        }
    }
    
    for z_id, zone in gebaeude.zonen.items():
        ergebnisse['zonen'][z_id] = {
            'name': zone.name,
            'H_tb_W_K': zone.H_tb,  # NEU
            'stunden': [],
            'monate': [{'Q_H_kWh': 0.0, 'Q_C_kWh': 0.0} for _ in range(12)],
            'Q_H_kWh': 0.0,
            'Q_C_kWh': 0.0,
            'theta_op_max': -100.0,
            'theta_op_min': 100.0
        }
    
    tage_monat = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    stunden_monat = [t * 24 for t in tage_monat]
    monat_start = [sum(stunden_monat[:i]) for i in range(12)]
    
    n_stunden = min(klima.n_stunden, 8760)

    # Verschattungs-/Sonnenstands-Standort aus den Klimadaten uebernehmen,
    # wenn der Loader einen liefert (TRY-/TMY3-Header). CSV-Klimadateien ohne
    # Location (z. B. BESTEST-Fassadenwerte) behalten optionen.standort
    # (Default DENVER = korrekt fuer die Verifizierungsfaelle).
    # Behebt den Audit-Pruefpunkt "GUI verschattet mit Denver-Sonne".
    if getattr(klima, 'location', None) is not None:
        loc = klima.location
        optionen.standort = Standort(
            name=getattr(loc, 'name', 'Klimadatei'),
            breitengrad=loc.latitude,
            laengengrad=loc.longitude,
            zeitzone=loc.timezone,
            hoehe_m=getattr(loc, 'elevation', 0.0))

    # ------------------------------------------------------------------
    # Echte Element-Orientierung statt 5-Richtungs-Raster.
    # Für jedes Bauteil abseits des Rasters wird die Bestrahlung mit den
    # tatsächlichen Winkeln (β/γ, Gl. 41/69 → EPB-Modul M1-13) über die
    # 52010-1-Kette vorberechnet. Rasterelemente und sämtliche
    # Direktspalten-CSV-Läufe (ohne DNI/DHI) nutzen unverändert die
    # bisherigen Rasterspalten (Spezialfall, bitidentisch).
    # ------------------------------------------------------------------
    kann_exakt = (getattr(klima, 'DNI', None) is not None
                  and getattr(klima, 'DHI', None) is not None)
    raster_hinweis = False
    for zone in gebaeude.zonen.values():
        for bt in zone.bauteile:
            exakt = orientierung_key_exakt(bt.azimut_deg, bt.neigung_deg)
            if exakt is None:
                bt.orientierung_key = None
            elif kann_exakt:
                # BESTEST-Azimut (N=0, O=90) -> ISO (S=0, O=+90, W=-90)
                azimut_iso = 180.0 - bt.azimut_deg
                azimut_iso = ((azimut_iso + 180.0) % 360.0) - 180.0
                if azimut_iso == -180.0:
                    azimut_iso = 180.0
                ergaenze_orientierung(
                    klima, exakt, azimut_iso, bt.neigung_deg,
                    location=getattr(klima, 'location', None))
                bt.orientierung_key = exakt
            else:
                bt.orientierung_key = None
                # Hinweis nur, wenn die Rundung wirken KANN: bei opaken
                # Flächen mit alpha_sol = 0 ist Phi_sol_abs unabhängig von
                # der Spaltenwahl exakt 0 (z. B. BESTEST-Boden, Neigung
                # 180°) — dort wäre der Hinweis ein Falsch-Positiv.
                strahlungswirksam = (bt.typ == 'transparent'
                                     or getattr(bt, 'alpha_sol', 0.0) > 0.0)
                if strahlungswirksam and not raster_hinweis:
                    print("  HINWEIS: Klimadatei ohne DNI/DHI - Orientierungen"
                          " abseits des Rasters werden auf N/E/S/W/H gerundet"
                          " (dokumentierte Einschränkung von Klimadateien ohne DNI/DHI).")
                    raster_hinweis = True
    
    # Arrays für Übertemperatur-Analyse
    theta_op_arrays = {z_id: np.zeros(n_stunden) for z_id in gebaeude.zonen}
    
    # Initialisierungsperiode nach ISO 52016-1, 6.5.5.2: der eigentlichen
    # Berechnung muss ein Vorlauf von mindestens zwei Wochen vorausgehen
    # (Jahresrechnung ab 1.1.: mindestens 18.-31. Dezember). Umsetzung: die
    # letzten init_tage Tage des Klimajahres werden vorab durchgerechnet und
    # ihre Ergebnisse verworfen (Norm: Bericht nur fuer die Berechnungszeit-
    # spanne). Der Vorlauf greift nur bei vollen Jahreslaeufen (8760 h) -
    # Kurzlaeufe (z. B. VDI-6020-Faelle) starten definitionsgemaess ab
    # Anfangszustand.
    init_tage = max(0, int(getattr(optionen, 'init_tage', 14)))
    init_stunden = init_tage * 24 if n_stunden == 8760 else 0
    vorlauf = range(n_stunden - init_stunden, n_stunden)
    stunden_plan = [(h, False) for h in vorlauf] + [(h, True) for h in range(n_stunden)]

    for lauf_idx, (stunde, aufzeichnen) in enumerate(stunden_plan):
        monat = 0
        for m in range(12):
            if stunde < monat_start[m] + stunden_monat[m]:
                monat = m
                break
        
        theta_e = klima.theta_e[stunde]
        # Über alle vorhandenen Orientierungs-Keys iterieren
        # (Raster N/E/S/W/H + ggf. exakte Zusatzorientierungen)
        I_sol_dict = {k: arr[stunde] for k, arr in klima.I_sol.items()}

        # Direkt/Diffus-Dicts erstellen (falls verfügbar)
        I_sol_dir_dict = None
        I_sol_dif_dict = None
        if klima.I_sol_dir and klima.I_sol_dif:
            I_sol_dir_dict = {k: arr[stunde]
                              for k, arr in klima.I_sol_dir.items()}
            I_sol_dif_dict = {k: arr[stunde]
                              for k, arr in klima.I_sol_dif.items()}
        
        nachbar_temps = {z_id: z.theta_air for z_id, z in gebaeude.zonen.items()}
        
        for z_id, zone in gebaeude.zonen.items():
            np_id = zone.nutzungsprofil
            if np_id in gebaeude.nutzungsprofile:
                nutzung = gebaeude.nutzungsprofile[np_id]
            else:
                nutzung = Nutzungsprofil(id='default', beschreibung='Default')
            
            # θ_i aus vorheriger Stunde (für temperaturgesteuerte Lüftung)
            theta_i_vorher = zone.theta_op if lauf_idx > 0 else 20.0
            
            theta_op, theta_air, Phi_H, Phi_C = fuenf_stufen_verfahren(
                zone, theta_e, I_sol_dict,
                gebaeude.randbedingungen, nachbar_temps,
                optionen, nutzung, stunde, stunde,  # stunde_jahr = stunde
                Phi_H_max=nutzung.max_heizleistung_W,
                Phi_C_max=-nutzung.max_kuehlleistung_W,  # Negativ für Kühlung!
                I_sol_dir_dict=I_sol_dir_dict, I_sol_dif_dict=I_sol_dif_dict,
                theta_i_vorher=theta_i_vorher
            )
            
            if not aufzeichnen:
                continue  # Vorlauf: Zustand fortschreiben, Ergebnisse verwerfen

            # Für Übertemperatur-Analyse speichern
            theta_op_arrays[z_id][stunde] = theta_op
            
            Q_H = Phi_H / 1000.0
            Q_C = abs(Phi_C) / 1000.0
            
            erg_zone = ergebnisse['zonen'][z_id]
            
            if optionen.ausgabe_stunden:
                erg_zone['stunden'].append({
                    'stunde': stunde + 1,
                    'theta_e': round(theta_e, 2),
                    'theta_op': round(theta_op, 2),
                    'theta_air': round(theta_air, 2),
                    'Phi_H_W': round(Phi_H, 1),
                    'Phi_C_W': round(Phi_C, 1)
                })
            
            erg_zone['monate'][monat]['Q_H_kWh'] += Q_H
            erg_zone['monate'][monat]['Q_C_kWh'] += Q_C
            erg_zone['Q_H_kWh'] += Q_H
            erg_zone['Q_C_kWh'] += Q_C
            erg_zone['theta_op_max'] = max(erg_zone['theta_op_max'], theta_op)
            erg_zone['theta_op_min'] = min(erg_zone['theta_op_min'], theta_op)
        
        if aufzeichnen and (stunde + 1) % 1000 == 0:
            print(f"  Stunde {stunde + 1}/{n_stunden}")
    
    for z_id, erg_zone in ergebnisse['zonen'].items():
        ergebnisse['gesamt']['Q_H_kWh'] += erg_zone['Q_H_kWh']
        ergebnisse['gesamt']['Q_C_kWh'] += erg_zone['Q_C_kWh']
        
        erg_zone['Q_H_kWh'] = round(erg_zone['Q_H_kWh'], 1)
        erg_zone['Q_C_kWh'] = round(erg_zone['Q_C_kWh'], 1)
        for m in erg_zone['monate']:
            m['Q_H_kWh'] = round(m['Q_H_kWh'], 1)
            m['Q_C_kWh'] = round(m['Q_C_kWh'], 1)
    
    ergebnisse['gesamt']['Q_H_kWh'] = round(ergebnisse['gesamt']['Q_H_kWh'], 1)
    ergebnisse['gesamt']['Q_C_kWh'] = round(ergebnisse['gesamt']['Q_C_kWh'], 1)
    
    # =========================================================================
    # ÜBERTEMPERATUR-ANALYSE (DIN EN 16798-1)
    # =========================================================================
    if n_stunden == 8760:
        # Gleitendes Mittel der Außentemperatur berechnen
        theta_rm = berechne_theta_rm_stuendlich(klima.theta_e[:8760])
        
        for z_id, theta_op_arr in theta_op_arrays.items():
            erg_zone = ergebnisse['zonen'][z_id]
            
            # theta_op Zeitreihe speichern (für Plots und DIN 4108-2)
            erg_zone['theta_op'] = theta_op_arr.tolist()
            
            # Übertemperatur-Auswertung
            uet = berechne_uebertemperatur(theta_op_arr, theta_rm)
            
            # In Ergebnisse schreiben
            erg_zone['uebertemperatur'] = {
                'gradstunden_fest': {str(k): round(v, 1) for k, v in uet.gradstunden_fest.items()},
                'stunden_fest': {str(k): round(v, 1) for k, v in uet.stunden_fest.items()},
                'gradstunden_16798': {k: round(v, 1) for k, v in uet.gradstunden_adaptiv.items()},
                'stunden_16798': {k: round(v, 1) for k, v in uet.stunden_adaptiv.items()},
                'theta_op_max': round(uet.theta_op_max, 1),
                'theta_op_max_stunde': uet.theta_op_max_stunde
            }
    
    print()
    print("Simulation abgeschlossen.")
    
    return ergebnisse


# ============================================================================
# AUSGABE-FUNKTIONEN
# ============================================================================

def schreibe_ergebnisse_csv(ergebnisse: Dict, pfad: str):
    """
    Schreibt Jahres- und Monatsergebnisse als CSV-Datei.
    
    Args:
        ergebnisse: Ergebnis-Dictionary aus simuliere()
        pfad: Ausgabepfad für CSV-Datei
    """
    Path(pfad).parent.mkdir(parents=True, exist_ok=True)
    
    with open(pfad, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f, delimiter=';')
        
        writer.writerow(['ISO 52016-1 Simulationsergebnisse'])
        writer.writerow(['Projekt:', ergebnisse['projekt']])
        writer.writerow(['Zeitstempel:', ergebnisse['timestamp']])
        writer.writerow([])
        
        writer.writerow(['JAHRESERGEBNISSE'])
        writer.writerow(['Zone', 'Q_H [kWh/a]', 'Q_C [kWh/a]', 'H_tb [W/K]', 'theta_op_max [°C]', 'theta_op_min [°C]'])
        
        for z_id, z_erg in ergebnisse['zonen'].items():
            writer.writerow([
                z_erg['name'],
                z_erg['Q_H_kWh'],
                z_erg['Q_C_kWh'],
                z_erg.get('H_tb_W_K', 0),
                round(z_erg['theta_op_max'], 1),
                round(z_erg['theta_op_min'], 1)
            ])
        
        writer.writerow(['GESAMT', ergebnisse['gesamt']['Q_H_kWh'], ergebnisse['gesamt']['Q_C_kWh'], '', '', ''])
        writer.writerow([])
        
        writer.writerow(['MONATSERGEBNISSE'])
        monate = ['Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez']
        
        for z_id, z_erg in ergebnisse['zonen'].items():
            writer.writerow([f"Zone: {z_erg['name']}"])
            writer.writerow(['Monat', 'Q_H [kWh]', 'Q_C [kWh]'])
            for i, m in enumerate(z_erg['monate']):
                writer.writerow([monate[i], m['Q_H_kWh'], m['Q_C_kWh']])
            writer.writerow([])
    
    print(f"CSV-Ergebnisse geschrieben: {pfad}")


def schreibe_ergebnisse_json(ergebnisse: Dict, pfad: str):
    """
    Schreibt Ergebnisse als JSON-Datei (ohne Stundenwerte).
    
    Args:
        ergebnisse: Ergebnis-Dictionary aus simuliere()
        pfad: Ausgabepfad für JSON-Datei
    """
    Path(pfad).parent.mkdir(parents=True, exist_ok=True)
    
    erg_kompakt = {
        'projekt': ergebnisse['projekt'],
        'timestamp': ergebnisse['timestamp'],
        
        'gesamt': ergebnisse['gesamt'],
        'zonen': {}
    }
    
    for z_id, z_erg in ergebnisse['zonen'].items():
        erg_kompakt['zonen'][z_id] = {
            'name': z_erg['name'],
            'Q_H_kWh': z_erg['Q_H_kWh'],
            'Q_C_kWh': z_erg['Q_C_kWh'],
            'H_tb_W_K': z_erg.get('H_tb_W_K', 0),
            'theta_op_max': round(z_erg['theta_op_max'], 1),
            'theta_op_min': round(z_erg['theta_op_min'], 1),
            'monate': z_erg['monate']
        }
    
    with open(pfad, 'w', encoding='utf-8') as f:
        json.dump(erg_kompakt, f, indent=2, ensure_ascii=False)
    
    print(f"JSON-Ergebnisse geschrieben: {pfad}")


def schreibe_stundenwerte_csv(ergebnisse: Dict, pfad: str):
    """
    Schreibt detaillierte Stundenwerte als CSV-Datei.
    
    Args:
        ergebnisse: Ergebnis-Dictionary aus simuliere()
        pfad: Ausgabepfad für CSV-Datei
    """
    Path(pfad).parent.mkdir(parents=True, exist_ok=True)
    
    with open(pfad, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f, delimiter=';')
        
        header = ['Stunde', 'theta_e']
        for z_id, z_erg in ergebnisse['zonen'].items():
            name = z_erg['name']
            header.extend([f'{name}_theta_op', f'{name}_theta_air', 
                          f'{name}_Phi_H', f'{name}_Phi_C'])
        writer.writerow(header)
        
        if ergebnisse['zonen']:
            erste_zone = list(ergebnisse['zonen'].values())[0]
            n_stunden = len(erste_zone.get('stunden', []))
            
            for i in range(n_stunden):
                row = []
                for z_id, z_erg in ergebnisse['zonen'].items():
                    if i < len(z_erg.get('stunden', [])):
                        s = z_erg['stunden'][i]
                        if not row:
                            row = [s['stunde'], s['theta_e']]
                        row.extend([s['theta_op'], s['theta_air'], 
                                   s['Phi_H_W'], s['Phi_C_W']])
                if row:
                    writer.writerow(row)
    
    print(f"Stundenwerte geschrieben: {pfad}")


# ============================================================================
# HAUPTPROGRAMM
# ============================================================================

def main(pfad_gebaeude: str = 'gebaeude.json',
         pfad_nutzung: str = 'nutzung.json',
         pfad_steuerung: str = 'steuerung.json'):
    """
    Hauptfunktion - führt komplette Simulation durch.
    
    Lädt alle Eingabedaten, führt die Jahressimulation aus und
    schreibt die Ergebnisse in CSV- und JSON-Dateien.
    
    Args:
        pfad_gebaeude: Pfad zur Gebäude-JSON
        pfad_nutzung: Pfad zur Nutzungsprofil-JSON
        pfad_steuerung: Pfad zur Steuerungs-JSON (Optionen, Klimadatei)
    """
    print("=" * 60)
    print("ISO 52016-1 Thermische Gebäudesimulation (Normkonform)")
    print("=" * 60)
    print()
    
    print("Lade Eingabedaten...")
    optionen = lade_optionen(pfad_steuerung)
    gebaeude = lade_gebaeude(pfad_gebaeude, pfad_nutzung)
    klima = lade_klimadaten(optionen.klimadatei, optionen.klimaformat)
    print()
    
    ergebnisse = simuliere(gebaeude, klima, optionen)
    
    print()
    print("=" * 60)
    print("ERGEBNISSE")
    print("=" * 60)
    print()
    print(f"Heizwärmebedarf:  {ergebnisse['gesamt']['Q_H_kWh']:,.0f} kWh/a")
    print(f"Kühlbedarf:       {ergebnisse['gesamt']['Q_C_kWh']:,.0f} kWh/a")
    print()
    
    for z_id, z_erg in ergebnisse['zonen'].items():
        print(f"Zone '{z_erg['name']}':")
        print(f"  Heizen:  {z_erg['Q_H_kWh']:,.0f} kWh/a")
        print(f"  Kühlen:  {z_erg['Q_C_kWh']:,.0f} kWh/a")
        print(f"  H_tb:    {z_erg.get('H_tb_W_K', 0):.2f} W/K")
        print(f"  θ_op:    {z_erg['theta_op_min']:.1f} ... {z_erg['theta_op_max']:.1f} °C")
    
    print()
    schreibe_ergebnisse_csv(ergebnisse, optionen.ausgabe_datei_csv)
    schreibe_ergebnisse_json(ergebnisse, optionen.ausgabe_datei_json)
    
    if optionen.ausgabe_stunden:
        pfad_stunden = optionen.ausgabe_datei_csv.replace('.csv', '_stunden.csv')
        schreibe_stundenwerte_csv(ergebnisse, pfad_stunden)
    
    print()
    print("Fertig!")
    
    return ergebnisse


if __name__ == '__main__':
    import sys
    
    if len(sys.argv) >= 4:
        main(sys.argv[1], sys.argv[2], sys.argv[3])
    else:
        main()

# Copyright (c) 2026 Mario Vukadinovic
# SPDX-License-Identifier: AGPL-3.0-only
# Part of the ISO 52016-1 Room Simulator. See LICENSE.
# Commercial licensing available on request.

"""
Climate Data Module
===================

Climate data classes and weather file loaders for building energy simulation.

Contents:
    - ClimateData: Central climate data class
    - Location: Site definition  
    - load_climate(): Unified loader with auto-detection
    - load_tmy3(), load_try(): Format-specific loaders
    - Solar position and surface radiation (ISO 52010-1)

Supported weather formats:
    - TMY3: NREL Typical Meteorological Year 3
    - TRY: DWD Test Reference Year (2010, 2035, 2045)
    - CSV: Simple CSV with pre-computed values

References:
    - DIN EN ISO 52010-1:2017 (Solar radiation)
    - TMY3: NREL Technical Report NREL/TP-581-43156
    - TRY: DWD Test Reference Years for Germany
"""

import math
import re
import numpy as np
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple
from enum import Enum, auto

from .solar import (
    Standort as _SolarStandort,
    berechne_sonnenstand,
    berechne_strahlung_geneigte_flaeche,
    RHO_GROUND_DEFAULT,
    I_SC,
)


# =============================================================================
# CONSTANTS
# =============================================================================

# I_SC (1370, Tabelle 9) und RHO_GROUND_DEFAULT (0,2, Tabelle B.5) kommen
# aus solar.py (Import oben) — die früheren lokalen Doubletten (I_SC = 1367!)
# überschrieben den Import und sind entfernt.


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class Location:
    """
    Geographic location for solar calculations.
    
    Attributes:
        name: Location identifier
        latitude: Geographic latitude [°], positive = North
        longitude: Geographic longitude [°], positive = East
        timezone: Hours from UTC (e.g., -7 for Denver, +1 for CET)
        elevation: Height above sea level [m]
    """
    name: str
    latitude: float
    longitude: float
    timezone: float
    elevation: float = 0.0


# Common locations
DENVER = Location("Denver, CO", 39.76, -104.86, -7.0, 1609.0)
POTSDAM = Location("Potsdam, Germany", 52.38, 13.06, 1.0, 81.0)


@dataclass
class ClimateData:
    """
    Hourly climate data for building energy simulation.
    
    Attributes:
        n_hours: Number of data points (typically 8760)
        theta_e: Outdoor air temperature [°C]
        I_sol: Total solar irradiance per orientation [W/m²]
        I_sol_dir: Direct component per orientation [W/m²]
        I_sol_dif: Diffuse component per orientation [W/m²]
        location: Site location (optional)
        GHI: Global Horizontal Irradiance [W/m²] (optional)
        DNI: Direct Normal Irradiance [W/m²] (optional)
        DHI: Diffuse Horizontal Irradiance [W/m²] (optional)
        v_wind: Wind speed [m/s] (optional)
    """
    n_hours: int
    theta_e: np.ndarray
    
    # Solar radiation on surfaces (keyed by 'N', 'E', 'S', 'W', 'H')
    I_sol: Dict[str, np.ndarray] = field(default_factory=dict)
    I_sol_dir: Dict[str, np.ndarray] = field(default_factory=dict)
    I_sol_dif: Dict[str, np.ndarray] = field(default_factory=dict)
    
    # Optional
    location: Optional[Location] = None
    GHI: Optional[np.ndarray] = None
    DNI: Optional[np.ndarray] = None
    DHI: Optional[np.ndarray] = None
    v_wind: Optional[np.ndarray] = None
    
    @property
    def n_stunden(self) -> int:
        """Alias for n_hours (backwards compatibility)."""
        return self.n_hours
    
    def get_irradiance(self, orientation: str) -> np.ndarray:
        """Get total irradiance for an orientation."""
        return self.I_sol.get(orientation, np.zeros(self.n_hours))


# =============================================================================
# SOLAR POSITION (ISO 52010-1)
# =============================================================================

def compute_solar_position(hour: int, day: int, location: Location) -> Tuple[float, float]:
    """
    Compute solar altitude and azimuth.
    
    Dünner Wrapper über die geprüfte 52010-1-Kette in solar.py
    (Gl. 1-16 der ISO 52010-1; Fixes 15-21). Die frühere Eigenkopie der
    Sonnenstandsformeln hier war eine Doppelstruktur und ist entfernt.
    Nachts gilt Gl. (11): alpha = 0 (kein Sonderwert-Tupel mehr); der
    Azimut wird auch bei alpha = 0 normkonform berechnet.
    
    Args:
        hour: Hour of day (0-23)
        day: Day of year (1-365)
        location: Site location
        
    Returns:
        (altitude, azimuth) in degrees
        - altitude: Solar elevation [°], 0 = horizon (auch nachts, Gl. 11)
        - azimuth: Solar azimuth [°], South = 0, East = +90, West = -90
    """
    standort = _SolarStandort(
        name=location.name or "climate",
        breitengrad=location.latitude,
        laengengrad=location.longitude,
        zeitzone=location.timezone,
        hoehe_m=location.elevation,
    )
    erg = berechne_sonnenstand(hour, day, standort)
    return erg.alpha_sol, erg.phi_sol


def compute_surface_irradiance(
    DNI: np.ndarray,
    DHI: np.ndarray,
    alpha_sol: np.ndarray,
    phi_sol: np.ndarray,
    surface_azimuth: float,
    surface_tilt: float = 90.0,
    rho_ground: float = RHO_GROUND_DEFAULT,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Compute irradiance on a tilted surface — Perez-Modell nach ISO 52010-1.
    
    Ersetzt das frühere isotrope Modell durch die
    geprüfte Kette in solar.py (Gl. 26-39, Fixes 15-21), inklusive
    Bodenreflexion (Gl. 35, rho = 0,2 nach Tabelle B.5).
    
    Kanalzuordnung nach Norm:
        I_dir = I_dir;tot nach Gl. (37)  — Direkt + Zirkumsolar
        I_dif = I_dif;tot nach Gl. (38)  — Diffus - Zirkumsolar + Boden
    Damit trifft die Verschattung (F_sh nur auf Direktanteil, Anhang F
    Verfahren 1) normkonform auch den zirkumsolaren Anteil.
    
    Args:
        DNI: Direct Normal Irradiance [W/m²]
        DHI: Diffuse Horizontal Irradiance [W/m²]
        alpha_sol: Solar altitude [°] (Gl. 11: nachts 0)
        phi_sol: Solar azimuth [°]
        surface_azimuth: Surface azimuth [°] (South = 0, East = +90)
        surface_tilt: Surface tilt [°] (90 = vertical, 0 = horizontal)
        rho_ground: Bodenalbedo [-] (Default 0,2, Tabelle B.5)
    
    Returns:
        (I_dir_tot, I_dif_tot) arrays [W/m²] nach Gl. (37)/(38)
    """
    n = len(DNI)
    I_dir = np.zeros(n)
    I_dif = np.zeros(n)
    
    for h in range(n):
        if DNI[h] <= 0.0 and DHI[h] <= 0.0:
            continue  # keine Strahlung -> Kette liefert exakt 0 (reine Laufzeitersparnis)
        r = berechne_strahlung_geneigte_flaeche(
            G_sol_b=float(DNI[h]),
            G_sol_d=float(DHI[h]),
            alpha_sol_deg=float(alpha_sol[h]),
            gamma_sol_deg=float(phi_sol[h]),
            beta_deg=surface_tilt,
            gamma_surf_deg=surface_azimuth,
            n_day=(h // 24) + 1,
            rho_ground=rho_ground,
        )
        I_dir[h] = r.I_dir_tot
        I_dif[h] = r.I_dif_tot
    
    return I_dir, I_dif


def compute_all_orientations(climate: ClimateData, location: Optional[Location] = None) -> None:
    """
    Compute radiation on all standard orientations (N, E, S, W, H).
    
    Modifies climate.I_sol, I_sol_dir, I_sol_dif in place.
    """
    if climate.DNI is None or climate.DHI is None:
        raise ValueError("ClimateData must have DNI and DHI")
    
    loc = location or climate.location
    if loc is None:
        raise ValueError("Location required")
    
    print("Computing radiation on surfaces (Perez, ISO 52010-1)...")
    
    # Solar position arrays
    alpha_sol = np.zeros(climate.n_hours)
    phi_sol = np.zeros(climate.n_hours)
    for h in range(climate.n_hours):
        day = (h // 24) + 1
        hour = h % 24
        alpha_sol[h], phi_sol[h] = compute_solar_position(hour, day, loc)
    
    # Azimuth convention: South=0, East=+90, West=-90, North=±180
    orientations = {'N': (180, 90), 'E': (90, 90), 'S': (0, 90), 'W': (-90, 90), 'H': (0, 0)}
    
    for key, (azimuth, tilt) in orientations.items():
        I_dir, I_dif = compute_surface_irradiance(
            climate.DNI, climate.DHI, alpha_sol, phi_sol, azimuth, tilt)
        climate.I_sol_dir[key] = I_dir
        climate.I_sol_dif[key] = I_dif
        climate.I_sol[key] = I_dir + I_dif
        print(f"  {key}: I_dir_max={np.max(I_dir):.0f}, I_dif_max={np.max(I_dif):.0f} W/m²")


def ergaenze_orientierung(climate: ClimateData, key: str, azimut_iso_deg: float,
                          neigung_deg: float,
                          location: Optional[Location] = None) -> None:
    """
    Bestrahlung fuer eine zusaetzliche (Nicht-Raster-)
    Orientierung ueber die 52010-1-Kette berechnen und unter `key` in
    climate.I_sol / I_sol_dir / I_sol_dif ablegen.

    Normbasis: Gl. (41)/(69) der 52016-1 verlangen die Bestrahlungsstaerke
    mit den TATSAECHLICHEN Winkeln beta/gamma des Elements aus dem
    EPB-Modul M1-13 (= ISO 52010-1); die 45-Grad-Rundungsempfehlung
    (Anm. 3 zu Gl. 123) gilt nur den Horizontsegmenten des
    monatsbezogenen Anhang-F-Verfahrens, nicht dem Stundenverfahren
    (Seitenbild geprueft 22.07.2026, S. 96/110/135).

    Rasterorientierungen (N/E/S/W/H) werden hier nie angefasst
    (Spezialfall, bleibt bitidentisch). Braucht DNI/DHI, also die
    Konvertierungspfade (TMY3/TRY bzw. CSVs mit Rohdaten);
    Direktspalten-CSVs koennen keine Zusatzorientierungen liefern.

    Args:
        climate: Klimaobjekt mit DNI/DHI und Location
        key: Ziel-Key (Konvention der Simulation: "A{azimut}_T{neigung}")
        azimut_iso_deg: Flaechenazimut ISO-Konvention (S=0, O=+90, W=-90)
        neigung_deg: Flaechenneigung (0=horizontal, 90=vertikal)
        location: optional; sonst climate.location
    """
    if key in climate.I_sol:
        return  # bereits berechnet (mehrere Bauteile gleicher Orientierung)
    if climate.DNI is None or climate.DHI is None:
        raise ValueError("Zusatzorientierungen brauchen DNI/DHI im Klimaobjekt")
    loc = location or climate.location
    if loc is None:
        raise ValueError("Location required")

    # Sonnenstandsarrays einmalig berechnen und am Objekt cachen
    cache = getattr(climate, '_sonnenstand_cache', None)
    if cache is None:
        alpha_sol = np.zeros(climate.n_hours)
        phi_sol = np.zeros(climate.n_hours)
        for h in range(climate.n_hours):
            alpha_sol[h], phi_sol[h] = compute_solar_position(
                h % 24, (h // 24) + 1, loc)
        cache = (alpha_sol, phi_sol)
        climate._sonnenstand_cache = cache
    alpha_sol, phi_sol = cache

    I_dir, I_dif = compute_surface_irradiance(
        climate.DNI, climate.DHI, alpha_sol, phi_sol,
        azimut_iso_deg, neigung_deg)
    climate.I_sol_dir[key] = I_dir
    climate.I_sol_dif[key] = I_dif
    climate.I_sol[key] = I_dir + I_dif


def create_constant_climate(n_hours: int = 8760, theta_e: float = 20.0, I_sol: float = 0.0) -> ClimateData:
    """Create climate with constant values (for testing)."""
    I_sol_dict = {k: np.full(n_hours, I_sol) for k in ['N', 'E', 'S', 'W', 'H']}
    I_sol_dir_dict = {k: np.full(n_hours, I_sol) for k in ['N', 'E', 'S', 'W', 'H']}
    I_sol_dif_dict = {k: np.zeros(n_hours) for k in ['N', 'E', 'S', 'W', 'H']}
    return ClimateData(n_hours=n_hours, theta_e=np.full(n_hours, theta_e),
                       I_sol=I_sol_dict, I_sol_dir=I_sol_dir_dict, I_sol_dif=I_sol_dif_dict)


# =============================================================================
# TRY FORMAT DETECTION
# =============================================================================

class TRYFormat(Enum):
    """TRY file format types."""
    TRY_2010 = auto()  # TRY 2010, 2035
    TRY_2045 = auto()  # TRY 2045 (new format)


def _detect_try_format(filepath: str) -> TRYFormat:
    """Detect TRY format from first line."""
    with open(filepath, 'r', encoding='latin-1', errors='replace') as f:
        first_line = f.readline().strip()
    if first_line.startswith('TRY'):
        return TRYFormat.TRY_2010
    elif first_line.startswith('Koordinatensystem'):
        return TRYFormat.TRY_2045
    raise ValueError(f"Unknown TRY format: {first_line[:50]}...")


# =============================================================================
# LOADERS
# =============================================================================

def load_tmy3(path: str, compute_surfaces: bool = True) -> ClimateData:
    """Load TMY3 weather file (NREL format)."""
    with open(path, 'r') as f:
        lines = f.readlines()
    
    header = lines[0].strip().split(',')
    location = Location(
        name=f"{header[1].strip('\"')}, {header[2].strip('\"')}",
        latitude=float(header[4]),
        longitude=float(header[5]),
        timezone=float(header[3]),
        elevation=float(header[6])
    )
    
    print(f"Loading TMY3: {location.name}")
    
    n = min(len(lines) - 2, 8760)
    theta_e = np.zeros(n)
    GHI, DNI, DHI = np.zeros(n), np.zeros(n), np.zeros(n)
    v_wind = np.zeros(n)
    
    for i, line in enumerate(lines[2:2+n]):
        parts = line.strip().split(',')
        try:
            GHI[i] = float(parts[4])
            DNI[i] = float(parts[7])
            DHI[i] = float(parts[10])
            theta_e[i] = float(parts[31])
            v_wind[i] = float(parts[46])
        except (ValueError, IndexError):
            pass
    
    print(f"  Loaded: {n} hours")
    print(f"  Temperature range: {np.min(theta_e):.1f}°C to {np.max(theta_e):.1f}°C")
    
    climate = ClimateData(n_hours=n, theta_e=theta_e, location=location,
                          GHI=GHI, DNI=DNI, DHI=DHI, v_wind=v_wind)
    
    if compute_surfaces:
        compute_all_orientations(climate)
    
    return climate


def load_try(path: str, compute_surfaces: bool = True) -> ClimateData:
    """Load TRY (DWD Test Reference Year) with auto-detection."""
    fmt = _detect_try_format(path)
    
    with open(path, 'r', encoding='latin-1', errors='replace') as f:
        lines = f.readlines()
    
    print(f"Loading TRY: {path}")
    print(f"  Format: {fmt.name}")
    
    # Find data start
    data_start = 0
    station = "TRY"
    elevation = 0.0
    ref_period = ""
    lat_hdr, lon_hdr = None, None
    
    for i, line in enumerate(lines):
        line_s = line.strip()
        if 'Station:' in line_s:
            station = line_s.split(':')[1].split('WMO')[0].strip()
        # Standort aus dem TRY-Header (z. B. "GEOGR. BREITE:  54.18 GRAD   GEOGR. LAENGE:   12.08 GRAD")
        m = re.search(r'BREITE\s*:\s*([0-9.,]+)', line_s, re.IGNORECASE)
        if m:
            lat_hdr = float(m.group(1).replace(',', '.'))
        m = re.search(r'LAENGE\s*:\s*([0-9.,]+)', line_s, re.IGNORECASE)
        if m:
            lon_hdr = float(m.group(1).replace(',', '.'))
        m = re.search(r'STATIONSHOEHE\s+([0-9.,]+)', line_s, re.IGNORECASE)
        if m:
            elevation = float(m.group(1).replace(',', '.'))
        if 'Hoehenlage' in line_s or 'Höhenlage' in line_s:
            try:
                elevation = float(line_s.split(':')[-1].strip().split()[0])
            except:
                pass
        if 'Bezugszeitraum' in line_s:
            ref_period = line_s.split(':')[-1].strip()
        if line_s.startswith('***'):
            data_start = i + 1
            break
    
    print(f"  Station: {station}")
    print(f"  Reference: {ref_period}")
    
    # Parse data
    data_lines = lines[data_start:]
    n = min(len(data_lines), 8760)
    
    # Column indices differ by format
    if fmt == TRYFormat.TRY_2010:
        IDX_T, IDX_WG, IDX_B, IDX_D = 8, 7, 13, 14
    else:
        IDX_T, IDX_WG, IDX_B, IDX_D = 5, 8, 12, 13
    
    theta_e = np.zeros(n)
    I_dir, I_dif = np.zeros(n), np.zeros(n)
    v_wind = np.zeros(n)
    
    for i, line in enumerate(data_lines[:n]):
        parts = line.split()
        if len(parts) < 14:
            continue
        try:
            theta_e[i] = float(parts[IDX_T].replace(',', '.'))
            v_wind[i] = float(parts[IDX_WG].replace(',', '.'))
            I_dir[i] = max(0, float(parts[IDX_B].replace(',', '.')))
            I_dif[i] = max(0, float(parts[IDX_D].replace(',', '.')))
        except (ValueError, IndexError):
            pass
    
    # Standort aus dem TRY-Header; nur wenn dort nichts steht, Fallback mit WARNUNG
    if lat_hdr is not None and lon_hdr is not None:
        location = Location(name=station, latitude=lat_hdr, longitude=lon_hdr,
                            timezone=1.0, elevation=elevation)
    else:
        print("  WARNUNG: TRY-Header ohne Koordinaten - Fallback Potsdam (52.38/13.07). "
              "Sonnenstand/Fassadenstrahlung nur fuer diesen Standort korrekt!")
        location = Location(name=station, latitude=52.38, longitude=13.07,
                            timezone=1.0, elevation=elevation)
    
    # ISO 52010-1, 6.4.2: Spalte B der TRY-Dateien ist die DIREKTSTRAHLUNG AUF
    # DER HORIZONTALEN ("horiz. Ebene", s. Dateikopf). Fuer die Fassadenrechnung
    # wird die Normalstrahlung benoetigt: I_b = B / sin(alpha_sol).
    # Anmerkung 1 der Norm: bei tiefer Sonne hochempfindlich -> Schutzgrenze
    # alpha > 1 Grad, Kappung auf die Solarkonstante.
    DNI = np.zeros(n)
    for i in range(n):
        if I_dir[i] <= 0:
            continue
        alpha_i, _ = compute_solar_position(i % 24, i // 24 + 1, location)
        sin_a = math.sin(math.radians(alpha_i))
        if sin_a > 0.0175:  # alpha > ~1 Grad
            DNI[i] = min(I_dir[i] / sin_a, I_SC)  # Kappung auf Solarkonstante (Schutz, s.o.)
        # sonst: Direktanteil bei tiefstehender Sonne verworfen (numerisch instabil)
    climate = ClimateData(n_hours=n, theta_e=theta_e, location=location,
                          GHI=I_dir + I_dif, DNI=DNI, DHI=I_dif, v_wind=v_wind)
    
    print(f"  Loaded: {n} hours")
    print(f"  Temperature range: {np.min(theta_e):.1f}°C to {np.max(theta_e):.1f}°C")
    
    if compute_surfaces:
        compute_all_orientations(climate)
    
    return climate


def load_csv(path: str) -> ClimateData:
    """Load simple CSV with pre-computed surface radiation."""
    import csv
    
    with open(path, 'r') as f:
        reader = csv.DictReader(f, delimiter=';')
        rows = list(reader)
    
    n = len(rows)
    print(f"Loading CSV: {path}, {n} rows")
    
    theta_e = np.zeros(n)
    I_sol = {k: np.zeros(n) for k in ['N', 'E', 'S', 'W', 'H']}
    
    cols = rows[0].keys()
    temp_col = next((c for c in ['theta_e', 'T_e', 'temp'] if c in cols), None)
    dir_map = {'N': 'I_N', 'E': 'I_E', 'S': 'I_S', 'W': 'I_W', 'H': 'I_H'}
    
    # Optional: getrennte Direkt-/Diffusstrahlung (Spalten I_X_dir / I_X_dif).
    # Wenn vorhanden, wird die dir/dif-Trennung befuellt und die Simulation
    # verschattet nur den Direktanteil (ISO 52016-1, 6.5.13: F_sh,dif = 1,0).
    hat_dirdif = all(f'{c}_dir' in cols and f'{c}_dif' in cols for c in dir_map.values())
    I_sol_dir = {k: np.zeros(n) for k in ['N', 'E', 'S', 'W', 'H']} if hat_dirdif else {}
    I_sol_dif = {k: np.zeros(n) for k in ['N', 'E', 'S', 'W', 'H']} if hat_dirdif else {}
    
    for i, row in enumerate(rows):
        if temp_col:
            try:
                theta_e[i] = float(row[temp_col].replace(',', '.'))
            except:
                pass
        for d, col in dir_map.items():
            if col in cols:
                try:
                    I_sol[d][i] = float(row[col].replace(',', '.'))
                except:
                    pass
            if hat_dirdif:
                try:
                    I_sol_dir[d][i] = float(row[f'{col}_dir'].replace(',', '.'))
                    I_sol_dif[d][i] = float(row[f'{col}_dif'].replace(',', '.'))
                except:
                    pass
    
    if hat_dirdif:
        print("  Direkt-/Diffusstrahlung getrennt geladen")
    return ClimateData(n_hours=n, theta_e=theta_e, I_sol=I_sol,
                       I_sol_dir=I_sol_dir, I_sol_dif=I_sol_dif)


def load_climate(path: str, format: str = 'auto') -> ClimateData:
    """
    Load climate data with automatic format detection.
    
    Args:
        path: Path to weather file
        format: 'tmy3', 'try', 'csv', or 'auto' (case-insensitive)
    
    Returns:
        ClimateData object
    """
    # Normalize format to lowercase
    format = format.lower()
    
    if format == 'auto':
        with open(path, 'r', errors='replace') as f:
            first_line = f.readline().strip()
        
        if first_line.startswith('TRY') or first_line.startswith('Koordinatensystem'):
            format = 'try'
        elif first_line.count(',') >= 6:
            try:
                parts = first_line.split(',')
                float(parts[3])
                format = 'tmy3'
            except:
                format = 'csv'
        else:
            format = 'csv'
    
    print(f"Detected format: {format}")
    
    if format == 'tmy3':
        return load_tmy3(path)
    elif format == 'try':
        return load_try(path)
    elif format == 'csv':
        return load_csv(path)
    else:
        raise ValueError(f"Unknown format: {format}")


# =============================================================================
# BACKWARDS COMPATIBILITY (German aliases)
# =============================================================================

Klimadaten = ClimateData
Standort = Location
lade_klimadaten = load_climate

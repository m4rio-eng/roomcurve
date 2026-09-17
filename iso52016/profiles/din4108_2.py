# Copyright (c) 2026 Mario Vukadinovic
# SPDX-License-Identifier: AGPL-3.0-only
# Part of the ISO 52016-1 Room Simulator. See LICENSE.
# Commercial licensing available on request.
"""
DIN 4108-2 Summer Thermal Protection Profiles
==============================================

Usage profiles and boundary conditions for verification per DIN 4108-2.

Contents:
    - UsageType: Residential (WG) / Non-residential (NWG)
    - ClimateRegion: A (Rostock) / B (Potsdam) / C (Mannheim)
    - Hourly profiles for ventilation, loads, shading
    - Overheating evaluation

References:
    - DIN 4108-2:2026-05 (ersetzt DIN 4108-2:2013-02)
    - DIN EN ISO 52016-1 (stündliches Berechnungsverfahren)
    - TRY-Klimadaten: Gegenwart nach 8.5.2 c); Zukunfts-TRY nach Anhang B (informativ)
"""

import numpy as np
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple
from enum import Enum


# =============================================================================
# ENUMS
# =============================================================================

class UsageType(Enum):
    """Building usage type per DIN 4108-2."""
    WG = "residential"          # Wohngebäude
    NWG = "non_residential"     # Nichtwohngebäude


class ClimateRegion(Enum):
    """Climate region per DIN 4108-2."""
    A = "A"  # Rostock, cool
    B = "B"  # Potsdam, moderate
    C = "C"  # Mannheim, warm


class ShadingControl(Enum):
    """Shading control type."""
    AUTOMATIC = "automatic"
    MANUAL = "manual"


class NightVentilation(Enum):
    """Night ventilation option."""
    OFF = "off"           # Base air change only
    INCREASED = "increased"  # 2.0 ACH (window ventilation)
    HIGH = "high"         # 5.0 ACH (cross-floor)


# =============================================================================
# CONSTANTS
# =============================================================================

# Reference temperatures per climate region [°C]
REFERENCE_TEMPERATURES = {
    ClimateRegion.A: 25.0,
    ClimateRegion.B: 26.0,
    ClimateRegion.C: 27.0,
}

# Limit values for overheating degree hours [Kh/a]
LIMIT_VALUES = {
    UsageType.WG: 1200.0,
    UsageType.NWG: 500.0,
}

# Internal loads [W/m²]
# DIN 4108-2:2026-05, 8.5.2 e): Tageswert als konstante Last WÄHREND der
# Nutzungszeit ansetzen. WG-Nutzungszeit = 24 h, NWG-Nutzungszeit = 11 h
# (Mo–Fr 07–18 Uhr). Daher Tageswert durch die jeweilige Nutzungsstundenzahl.
INTERNAL_LOADS = {
    UsageType.WG: 100.0 / 24.0,    # 100 Wh/(m²·d) über 24 h ≈ 4.17 W/m²
    UsageType.NWG: 144.0 / 11.0,   # 144 Wh/(m²·d) über 11 h ≈ 13.09 W/m²
}

# Heating setpoint temperatures [°C]
HEATING_SETPOINTS = {
    UsageType.WG: 20.0,
    UsageType.NWG: 21.0,
}

# Air change rates [1/h]
AIR_CHANGE_RATES = {
    'base_wg': 0.5,
    'base_nwg_unoccupied': 0.24,
    'increased_day': 3.0,
    'night_increased': 2.0,
    'night_high': 5.0,
}

# Shading activation thresholds [W/m²]
SHADING_THRESHOLDS = {
    UsageType.WG: {'standard': 300.0, 'north': 200.0},
    UsageType.NWG: {'standard': 200.0, 'north': 150.0},
}

# Threshold for increased ventilation [°C]
VENTILATION_THRESHOLD = 23.0


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class DIN4108Profile:
    """
    Hourly profiles for DIN 4108-2 simulation.
    
    All arrays have 8760 elements (1 year, hourly).
    """
    usage_type: UsageType
    climate_region: ClimateRegion
    shading_control: ShadingControl
    night_ventilation: NightVentilation
    
    # Hourly profiles (8760 values)
    is_occupied: np.ndarray = field(default=None)         # Boolean
    is_workday: np.ndarray = field(default=None)          # Boolean (Mon-Fri)
    heating_setpoint: np.ndarray = field(default=None)    # [°C]
    internal_loads: np.ndarray = field(default=None)      # [W/m²]
    air_change_base: np.ndarray = field(default=None)     # [1/h] without increase
    air_change_increased: np.ndarray = field(default=None)# [1/h] with increase
    shading_threshold: np.ndarray = field(default=None)   # [W/m²]
    shading_available: np.ndarray = field(default=None)   # Boolean
    
    # Derived values
    reference_temperature: float = field(default=26.0)
    limit_value: float = field(default=1200.0)
    
    def __post_init__(self):
        """Initialize derived values."""
        self.reference_temperature = REFERENCE_TEMPERATURES[self.climate_region]
        self.limit_value = LIMIT_VALUES[self.usage_type]


@dataclass
class DIN4108Result:
    """Result of DIN 4108-2 evaluation."""
    # Inputs
    usage_type: UsageType
    climate_region: ClimateRegion
    reference_temperature: float
    limit_value: float
    
    # Results
    overheating_degree_hours: float   # [Kh/a]
    exceedance_hours: float           # [h/a]
    max_operative_temperature: float  # [°C]
    max_temperature_hour: int         # Hour of maximum
    
    # Evaluation
    requirement_met: bool
    reserve_kh: float                 # Limit - actual [Kh/a]
    reserve_percent: float            # Reserve in %
    
    def __repr__(self):
        status = "✅ PASSED" if self.requirement_met else "❌ FAILED"
        return (f"DIN 4108-2 Verification: {status}\n"
                f"  Overheating degree hours: {self.overheating_degree_hours:.0f} Kh/a "
                f"(Limit: {self.limit_value:.0f} Kh/a)\n"
                f"  Reserve: {self.reserve_kh:.0f} Kh/a ({self.reserve_percent:.1f}%)")


# =============================================================================
# PROFILE GENERATION
# =============================================================================

def _is_workday(day_of_year: int) -> bool:
    """
    Check if a day is a workday (Mon-Fri).
    
    DIN 4108-2: Year starts on a Monday, January 1st.
    Day 0 = Monday, Day 5 = Saturday, Day 6 = Sunday
    """
    weekday = day_of_year % 7
    return weekday < 5


def _generate_time_masks(usage_type: UsageType) -> Tuple[np.ndarray, np.ndarray]:
    """
    Generate occupancy and workday masks.
    
    Returns:
        (is_occupied, is_workday) - Boolean arrays (8760,)
    """
    is_occupied = np.zeros(8760, dtype=bool)
    is_workday = np.zeros(8760, dtype=bool)
    
    for day in range(365):
        workday = _is_workday(day)
        is_workday[day*24:(day+1)*24] = workday
        
        for hour in range(24):
            h = day * 24 + hour
            
            if usage_type == UsageType.WG:
                # WG: 0-24h, 7 days
                is_occupied[h] = True
            else:
                # NWG: Mon-Fri 7-18h
                if workday and 7 <= hour < 18:
                    is_occupied[h] = True
    
    return is_occupied, is_workday


def _generate_air_change_profiles(
    usage_type: UsageType,
    night_ventilation: NightVentilation,
    is_workday: np.ndarray,
    floor_area: float = 100.0,
    volume: float = 250.0
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Generate air change rate profiles (base and increased).
    
    Args:
        usage_type: WG or NWG
        night_ventilation: Night ventilation option
        is_workday: Workday mask
        floor_area: Net floor area [m²] (NWG only)
        volume: Room volume [m³] (NWG only)
    
    Returns:
        (air_change_base, air_change_increased) - Arrays (8760,) [1/h]
    """
    n_base = np.zeros(8760)
    n_increased = np.zeros(8760)
    
    # Night ventilation rate
    if night_ventilation == NightVentilation.OFF:
        n_night = 0.0
    elif night_ventilation == NightVentilation.INCREASED:
        n_night = AIR_CHANGE_RATES['night_increased']
    else:  # HIGH
        n_night = AIR_CHANGE_RATES['night_high']
    
    for day in range(365):
        workday = is_workday[day * 24]
        
        for hour in range(24):
            h = day * 24 + hour
            
            if usage_type == UsageType.WG:
                # WG: Base always 0.5 ACH
                n_base_hour = AIR_CHANGE_RATES['base_wg']
                
                # Occupancy hours: 6-23h → increased ventilation possible
                if 6 <= hour < 23:
                    n_base[h] = n_base_hour
                    n_increased[h] = AIR_CHANGE_RATES['increased_day']
                else:
                    # Night: 23-6h → night ventilation
                    n_base[h] = max(n_base_hour, n_night)
                    n_increased[h] = n_base[h]
            
            else:  # NWG
                if workday and 7 <= hour < 18:
                    # Occupancy: 4 × A_G / V
                    n_base_hour = 4.0 * floor_area / volume
                    n_base[h] = n_base_hour
                    n_increased[h] = max(n_base_hour, AIR_CHANGE_RATES['increased_day'])
                else:
                    # Outside occupancy: 0.24 ACH or night ventilation
                    n_base_hour = AIR_CHANGE_RATES['base_nwg_unoccupied']
                    n_base[h] = max(n_base_hour, n_night)
                    n_increased[h] = n_base[h]
    
    return n_base, n_increased


def _generate_internal_loads(
    usage_type: UsageType,
    is_occupied: np.ndarray
) -> np.ndarray:
    """
    Generate internal heat loads profile.
    
    WG: 4.17 W/m² constant (24h)
    NWG: 6.0 W/m² during occupancy only
    """
    loads = np.zeros(8760)
    
    if usage_type == UsageType.WG:
        loads[:] = INTERNAL_LOADS[UsageType.WG]
    else:
        loads[is_occupied] = INTERNAL_LOADS[UsageType.NWG]
    
    return loads


def _generate_shading_profiles(
    usage_type: UsageType,
    shading_control: ShadingControl,
    is_workday: np.ndarray,
    is_north: bool = False
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Generate shading activation threshold and availability.
    
    Args:
        usage_type: WG or NWG
        shading_control: Automatic or manual
        is_workday: Workday mask
        is_north: True for north orientation (lower threshold)
    
    Returns:
        (threshold, available) - Arrays (8760,)
    """
    thresholds = SHADING_THRESHOLDS[usage_type]
    threshold_value = thresholds['north'] if is_north else thresholds['standard']
    
    threshold = np.full(8760, threshold_value)
    available = np.ones(8760, dtype=bool)
    
    # Manual control NWG: inactive on weekends
    if shading_control == ShadingControl.MANUAL and usage_type == UsageType.NWG:
        available[~is_workday] = False
    
    return threshold, available


def create_profile(
    usage_type: UsageType,
    climate_region: ClimateRegion,
    shading_control: ShadingControl = ShadingControl.AUTOMATIC,
    night_ventilation: NightVentilation = NightVentilation.INCREASED,
    floor_area: float = 100.0,
    volume: float = 250.0
) -> DIN4108Profile:
    """
    Create complete DIN 4108-2 profile for simulation.
    
    Args:
        usage_type: WG or NWG
        climate_region: A, B, or C
        shading_control: Automatic or manual
        night_ventilation: Off, increased (2 ACH), or high (5 ACH)
        floor_area: Net floor area [m²]
        volume: Room volume [m³]
    
    Returns:
        DIN4108Profile with all hourly profiles
    """
    # Time masks
    is_occupied, is_workday = _generate_time_masks(usage_type)
    
    # Air change
    n_base, n_increased = _generate_air_change_profiles(
        usage_type, night_ventilation, is_workday, floor_area, volume
    )
    
    # Internal loads
    loads = _generate_internal_loads(usage_type, is_occupied)
    
    # Heating setpoint
    heating_setpoint = np.full(8760, HEATING_SETPOINTS[usage_type])
    
    # Shading (standard orientation)
    shading_threshold, shading_available = _generate_shading_profiles(
        usage_type, shading_control, is_workday
    )
    
    return DIN4108Profile(
        usage_type=usage_type,
        climate_region=climate_region,
        shading_control=shading_control,
        night_ventilation=night_ventilation,
        is_occupied=is_occupied,
        is_workday=is_workday,
        heating_setpoint=heating_setpoint,
        internal_loads=loads,
        air_change_base=n_base,
        air_change_increased=n_increased,
        shading_threshold=shading_threshold,
        shading_available=shading_available,
    )


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_reference_temperature(climate_region: ClimateRegion) -> float:
    """Get reference temperature for a climate region."""
    return REFERENCE_TEMPERATURES[climate_region]


def get_limit_value(usage_type: UsageType) -> float:
    """Get limit value for overheating degree hours."""
    return LIMIT_VALUES[usage_type]


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # Enums
    'UsageType',
    'ClimateRegion',
    'ShadingControl',
    'NightVentilation',
    
    # Data classes
    'DIN4108Profile',
    'DIN4108Result',
    
    # Functions
    'create_profile',
    'get_reference_temperature',
    'get_limit_value',
    
    # Constants
    'REFERENCE_TEMPERATURES',
    'LIMIT_VALUES',
    'INTERNAL_LOADS',
    'HEATING_SETPOINTS',
    'AIR_CHANGE_RATES',
    'SHADING_THRESHOLDS',
    'VENTILATION_THRESHOLD',
]

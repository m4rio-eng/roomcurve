# Copyright (c) 2026 Mario Vukadinovic
# SPDX-License-Identifier: AGPL-3.0-only
# Part of the ISO 52016-1 Room Simulator. See LICENSE.
# Commercial licensing available on request.

"""
ISO 52016-1 Building Energy Simulation
======================================

Hourly building energy simulation per DIN EN ISO 52016-1:2018-04.

Quick Start:
    from iso52016 import load_climate, load_building, simulate
    
    climate = load_climate('weather.csv')
    building = load_building('building.json', 'usage.json')
    results = simulate(building, climate)

Module Structure:
    - climate: Climate data classes and loaders
    - simulation: Thermal simulation engine  
    - solar: Solar position calculations
    - thermal_mass: Thermal capacity (ISO 13786)
    - analysis: Result evaluation
    - profiles/: Usage profiles (din4108_2, custom)

Example with DIN 4108-2:
    from iso52016 import load_climate, simulate
    from iso52016.profiles import create_profile, UsageType, ClimateRegion
    from iso52016.analysis import evaluate_din4108_2
    
    climate = load_climate('TRY2045-04.txt')
    profile = create_profile(UsageType.WG, ClimateRegion.B)
"""



# =============================================================================
# CLIMATE
# =============================================================================

from .climate import (
    ClimateData,
    Location,
    load_climate,
    load_tmy3,
    load_try,
    load_csv,
    TRYFormat,
    compute_solar_position,
    compute_surface_irradiance,
    compute_all_orientations,
    create_constant_climate,
    DENVER,
    POTSDAM,
    I_SC,
    RHO_GROUND_DEFAULT,
    # German aliases
    Klimadaten,
    Standort,
    lade_klimadaten,
)


# =============================================================================
# SIMULATION (from existing German module)
# =============================================================================

from .simulation import (
    Gebaeude as Building,
    Zone,
    Bauteil as Component,
    Waermebruecke as ThermalBridge,
    Nutzungsprofil as UsageProfile,
    Randbedingung as BoundaryCondition,
    SimulationsOptionen as SimulationOptions,
    lade_gebaeude as load_building,
    simuliere as simulate,
    lade_optionen as load_options,
    # German names for backwards compatibility
    Gebaeude,
    Bauteil,
    Waermebruecke,
    Nutzungsprofil,
    Randbedingung,
    SimulationsOptionen,
    lade_gebaeude,
    simuliere,
    lade_optionen,
)


# =============================================================================
# SOLAR (from existing German module)
# =============================================================================

from .solar import (
    Standort as Site,
    berechne_sonnenstand,
    DENVER as DENVER_BESTEST,
)


# =============================================================================
# THERMAL MASS (from existing German module)
# =============================================================================

from .thermal_mass import (
    Schicht as Layer,
    Massenklasse as MassClass,
    berechne_kappa_m as calculate_kappa,
    verteile_kapazitaet_auf_knoten as distribute_kappa_to_nodes,
    # German names
    Schicht,
    Massenklasse,
    berechne_kappa_m,
)


# =============================================================================
# ANALYSIS
# =============================================================================

from .analysis import (
    # German (original)
    UebertemperaturErgebnis,
    berechne_theta_rm_stuendlich,
    berechne_uebertemperatur,
    berechne_komfort_grenzwert,
    berechne_alle_grenzwerte,
    erstelle_nutzungszeit_maske,
    
    # English aliases
    OverheatingResult,
    calculate_running_mean_temperature,
    calculate_overheating,
    calculate_comfort_limit,
    calculate_all_limits,
    create_occupancy_mask,
    
    # DIN 4108-2
    DIN4108Result,
    evaluate_din4108_2,
)


# =============================================================================
# PROFILES (via submodule)
# =============================================================================

from . import profiles


# =============================================================================
# PUBLIC API
# =============================================================================

__all__ = [
    
    # Climate
    'ClimateData',
    'Location',
    'load_climate',
    'load_tmy3',
    'load_try',
    'load_csv',
    'TRYFormat',
    'compute_solar_position',
    'compute_all_orientations',
    'create_constant_climate',
    'DENVER',
    'POTSDAM',
    
    # Simulation (English)
    'Building',
    'Zone',
    'Component',
    'ThermalBridge',
    'UsageProfile',
    'BoundaryCondition',
    'SimulationOptions',
    'load_building',
    'simulate',
    'load_options',
    
    # Solar & Thermal (English)
    'Site',
    'Layer',
    'MassClass',
    'calculate_kappa',
    
    # Analysis (English)
    'OverheatingResult',
    'calculate_running_mean_temperature',
    'calculate_overheating',
    'calculate_comfort_limit',
    'create_occupancy_mask',
    'DIN4108Result',
    'evaluate_din4108_2',
    
    # Submodules
    'profiles',
    
    # German API (backwards compatibility)
    'Gebaeude',
    'Bauteil',
    'Waermebruecke',
    'Nutzungsprofil',
    'Klimadaten',
    'Standort',
    'Schicht',
    'Massenklasse',
    'lade_gebaeude',
    'simuliere',
    'berechne_sonnenstand',
    'berechne_kappa_m',
    'lade_klimadaten',
    'UebertemperaturErgebnis',
    'berechne_theta_rm_stuendlich',
    'berechne_uebertemperatur',
]

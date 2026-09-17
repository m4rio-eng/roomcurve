# Copyright (c) 2026 Mario Vukadinovic
# SPDX-License-Identifier: AGPL-3.0-only
# Part of the ISO 52016-1 Room Simulator. See LICENSE.
# Commercial licensing available on request.
"""
Usage Profiles Module
=====================

Pre-defined usage profiles for building energy simulation.

Available profiles:
    - din4108_2: DIN 4108-2 summer thermal protection (WG, NWG)
    - custom: User-defined profiles

Future:
    - din18599: DIN V 18599 energy certification profiles
"""

from .din4108_2 import (
    # Enums
    UsageType,
    ClimateRegion,
    ShadingControl,
    NightVentilation,
    
    # Data classes
    DIN4108Profile,
    DIN4108Result,
    
    # Functions
    create_profile,
    get_reference_temperature,
    get_limit_value,
    
    # Constants
    REFERENCE_TEMPERATURES,
    LIMIT_VALUES,
    INTERNAL_LOADS,
    HEATING_SETPOINTS,
)

from .custom import (
    CustomProfile,
    create_custom_profile,
    create_office_profile,
    create_residential_profile,
)

__all__ = [
    # DIN 4108-2
    'UsageType',
    'ClimateRegion',
    'ShadingControl',
    'NightVentilation',
    'DIN4108Profile',
    'DIN4108Result',
    'create_profile',
    'get_reference_temperature',
    'get_limit_value',
    'REFERENCE_TEMPERATURES',
    'LIMIT_VALUES',
    'INTERNAL_LOADS',
    'HEATING_SETPOINTS',
    
    # Custom
    'CustomProfile',
    'create_custom_profile',
    'create_office_profile',
    'create_residential_profile',
]

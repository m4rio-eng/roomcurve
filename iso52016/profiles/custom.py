# Copyright (c) 2026 Mario Vukadinovic
# SPDX-License-Identifier: AGPL-3.0-only
# Part of the ISO 52016-1 Room Simulator. See LICENSE.
# Commercial licensing available on request.
"""
Custom Usage Profiles
=====================

User-defined usage profiles for building energy simulation.

Allows full customization of:
    - Occupancy schedules
    - Internal loads
    - Ventilation rates
    - Heating/cooling setpoints
    - Shading control
"""

import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class CustomProfile:
    """
    User-defined usage profile.
    
    All hourly arrays should have 8760 elements (or will be broadcast).
    
    Attributes:
        name: Profile identifier
        description: Profile description
        
        is_occupied: Occupancy mask (Boolean)
        heating_setpoint: Heating setpoint [°C]
        cooling_setpoint: Cooling setpoint [°C]
        internal_loads: Internal heat gains [W/m²]
        air_change_rate: Ventilation rate [1/h]
        
        reference_temperature: For overheating evaluation [°C]
        limit_value: Maximum overheating degree hours [Kh/a]
    """
    name: str
    description: str = ""
    
    # Hourly profiles
    is_occupied: np.ndarray = field(default_factory=lambda: np.ones(8760, dtype=bool))
    heating_setpoint: np.ndarray = field(default_factory=lambda: np.full(8760, 20.0))
    cooling_setpoint: np.ndarray = field(default_factory=lambda: np.full(8760, 26.0))
    internal_loads: np.ndarray = field(default_factory=lambda: np.full(8760, 5.0))
    air_change_rate: np.ndarray = field(default_factory=lambda: np.full(8760, 0.5))
    
    # Evaluation parameters
    reference_temperature: float = 26.0
    limit_value: float = 1200.0
    
    def validate(self) -> List[str]:
        """
        Validate profile data.
        
        Returns:
            List of validation errors (empty if valid)
        """
        errors = []
        
        # Check array lengths
        for attr in ['is_occupied', 'heating_setpoint', 'cooling_setpoint', 
                     'internal_loads', 'air_change_rate']:
            arr = getattr(self, attr)
            if len(arr) != 8760:
                errors.append(f"{attr}: expected 8760 elements, got {len(arr)}")
        
        # Check value ranges
        if np.any(self.heating_setpoint < 0) or np.any(self.heating_setpoint > 50):
            errors.append("heating_setpoint: values should be 0-50°C")
        
        if np.any(self.cooling_setpoint < 0) or np.any(self.cooling_setpoint > 50):
            errors.append("cooling_setpoint: values should be 0-50°C")
        
        if np.any(self.internal_loads < 0):
            errors.append("internal_loads: negative values not allowed")
        
        if np.any(self.air_change_rate < 0):
            errors.append("air_change_rate: negative values not allowed")
        
        return errors


def create_custom_profile(
    name: str,
    occupancy_hours: Tuple[int, int] = (7, 18),
    occupancy_days: Tuple[int, ...] = (0, 1, 2, 3, 4),  # Mon-Fri
    heating_setpoint: float = 20.0,
    cooling_setpoint: float = 26.0,
    internal_loads: float = 5.0,
    air_change_rate: float = 0.5,
    reference_temperature: float = 26.0,
    limit_value: float = 1200.0,
    description: str = ""
) -> CustomProfile:
    """
    Create a custom profile with simple parameters.
    
    Args:
        name: Profile identifier
        occupancy_hours: (start_hour, end_hour), e.g. (7, 18)
        occupancy_days: Tuple of weekdays (0=Mon, 6=Sun)
        heating_setpoint: Constant heating setpoint [°C]
        cooling_setpoint: Constant cooling setpoint [°C]
        internal_loads: Constant internal loads [W/m²]
        air_change_rate: Constant air change rate [1/h]
        reference_temperature: For overheating evaluation [°C]
        limit_value: Maximum overheating degree hours [Kh/a]
        description: Profile description
    
    Returns:
        CustomProfile object
    """
    # Generate occupancy mask
    is_occupied = np.zeros(8760, dtype=bool)
    
    for day in range(365):
        weekday = day % 7
        if weekday in occupancy_days:
            start_h = day * 24 + occupancy_hours[0]
            end_h = day * 24 + occupancy_hours[1]
            is_occupied[start_h:end_h] = True
    
    return CustomProfile(
        name=name,
        description=description,
        is_occupied=is_occupied,
        heating_setpoint=np.full(8760, heating_setpoint),
        cooling_setpoint=np.full(8760, cooling_setpoint),
        internal_loads=np.full(8760, internal_loads),
        air_change_rate=np.full(8760, air_change_rate),
        reference_temperature=reference_temperature,
        limit_value=limit_value,
    )


# =============================================================================
# PRESET TEMPLATES
# =============================================================================

def create_office_profile() -> CustomProfile:
    """Create standard office profile."""
    return create_custom_profile(
        name="Office",
        occupancy_hours=(8, 18),
        occupancy_days=(0, 1, 2, 3, 4),
        heating_setpoint=21.0,
        cooling_setpoint=26.0,
        internal_loads=8.0,
        air_change_rate=1.5,
        description="Standard office (Mon-Fri 8-18h)"
    )


def create_residential_profile() -> CustomProfile:
    """Create standard residential profile."""
    return create_custom_profile(
        name="Residential",
        occupancy_hours=(0, 24),
        occupancy_days=(0, 1, 2, 3, 4, 5, 6),
        heating_setpoint=20.0,
        cooling_setpoint=26.0,
        internal_loads=4.0,
        air_change_rate=0.5,
        description="Residential (24/7)"
    )


def create_school_profile() -> CustomProfile:
    """Create school profile."""
    return create_custom_profile(
        name="School",
        occupancy_hours=(8, 16),
        occupancy_days=(0, 1, 2, 3, 4),
        heating_setpoint=20.0,
        cooling_setpoint=26.0,
        internal_loads=12.0,
        air_change_rate=2.5,
        description="School (Mon-Fri 8-16h)"
    )


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    'CustomProfile',
    'create_custom_profile',
    'create_office_profile',
    'create_residential_profile',
    'create_school_profile',
]

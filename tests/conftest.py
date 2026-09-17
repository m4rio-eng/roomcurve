"""
Pytest Fixtures für ISO 52016-1 Testsuite
"""

import pytest
import sys
from pathlib import Path

# Projektpfad hinzufügen
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from iso52016 import (
    load_climate, create_constant_climate,
    Gebaeude, Zone, Bauteil, Nutzungsprofil,
    SimulationsOptionen
)


# =============================================================================
# PFADE
# =============================================================================

@pytest.fixture
def project_root():
    """Projektverzeichnis"""
    return PROJECT_ROOT


@pytest.fixture
def klimadaten_dir(project_root):
    """Klimadaten-Verzeichnis"""
    return project_root / "klimadaten"


@pytest.fixture
def bestest_dir(project_root):
    """BESTEST-Validierungsverzeichnis"""
    return project_root / "verifizierungen" / "bestest"


# =============================================================================
# KLIMADATEN
# =============================================================================

@pytest.fixture
def klima_konstant():
    """Konstantes Klima für schnelle Tests"""
    return create_constant_climate(8760, theta_e=10.0, I_sol=200.0)


@pytest.fixture
def klima_try(klimadaten_dir):
    """TRY-Klimadaten Potsdam 2015"""
    try_file = klimadaten_dir / "TRY2015-04-Jahr.txt"
    if try_file.exists():
        return load_climate(str(try_file), format='try')
    pytest.skip("TRY-Datei nicht gefunden")


@pytest.fixture
def klima_bestest(bestest_dir):
    """BESTEST-Klimadaten (DRYCOLD, EPB-Center-Begleitdatei)"""
    klima_file = bestest_dir / "klimadaten" / "DRYCOLD_52016_verifizierung.csv"
    if klima_file.exists():
        return load_climate(str(klima_file), format='csv')
    pytest.skip("BESTEST-Klimadatei nicht gefunden")


# =============================================================================
# GEBÄUDE
# =============================================================================

@pytest.fixture
def profil_minimal():
    """Minimales Nutzungsprofil"""
    return Nutzungsprofil(
        id="test",
        beschreibung="Test-Profil",
        heizen_C=[20.0] * 24,
        kuehlen_C=[26.0] * 24,
        interne_gewinne_W=[0.0] * 24,
        luftwechsel_1_h=[0.5] * 24,
    )


@pytest.fixture
def gebaeude_minimal(profil_minimal):
    """Minimales Testgebäude (1 Zone, 6 Bauteile)"""
    
    bauteile = [
        # Südfassade mit Fenster (opak + transparent)
        Bauteil(
            id="sued_wand", name="Süd Wand", typ="opak",
            flaeche_m2=7.0, azimut_deg=180, neigung_deg=90,
            zone_innen="Z1", zone_aussen="AUL",
            R_c_m2K_W=3.5, kappa_m_kJ_m2K=50.0
        ),
        Bauteil(
            id="sued_fenster", name="Süd Fenster", typ="transparent",
            flaeche_m2=3.0, azimut_deg=180, neigung_deg=90,
            zone_innen="Z1", zone_aussen="AUL",
            U_W_m2K=1.3, g_wert=0.6
        ),
        # Restliche Wände
        Bauteil(
            id="nord", name="Nord", typ="opak",
            flaeche_m2=10.0, azimut_deg=0, neigung_deg=90,
            zone_innen="Z1", zone_aussen="AUL",
            R_c_m2K_W=3.5, kappa_m_kJ_m2K=50.0
        ),
        Bauteil(
            id="ost", name="Ost", typ="opak",
            flaeche_m2=10.0, azimut_deg=90, neigung_deg=90,
            zone_innen="Z1", zone_aussen="AUL",
            R_c_m2K_W=3.5, kappa_m_kJ_m2K=50.0
        ),
        Bauteil(
            id="west", name="West", typ="opak",
            flaeche_m2=10.0, azimut_deg=270, neigung_deg=90,
            zone_innen="Z1", zone_aussen="AUL",
            R_c_m2K_W=3.5, kappa_m_kJ_m2K=50.0
        ),
        # Dach und Boden
        Bauteil(
            id="dach", name="Dach", typ="opak",
            flaeche_m2=40.0, azimut_deg=0, neigung_deg=0,
            zone_innen="Z1", zone_aussen="AUL",
            R_c_m2K_W=5.0, kappa_m_kJ_m2K=50.0
        ),
        Bauteil(
            id="boden", name="Boden", typ="opak",
            flaeche_m2=40.0, azimut_deg=0, neigung_deg=0,
            zone_innen="Z1", zone_aussen="ERD",
            R_c_m2K_W=2.5, kappa_m_kJ_m2K=50.0
        ),
    ]
    
    zone = Zone(
        id="Z1",
        name="Testzone",
        volumen_m3=100.0,
        nutzflaeche_m2=40.0,
        nutzungsprofil="test",
        bauteile=bauteile,
    )
    
    return Gebaeude(
        name="Testgebäude",
        beschreibung="Minimales Testgebäude",
        zonen={"Z1": zone},
        nutzungsprofile={"test": profil_minimal}
    )


@pytest.fixture
def optionen_schnell():
    """Simulationsoptionen für schnelle Tests (1 Monat)"""
    return SimulationsOptionen(
        klimadatei="test",
    )


@pytest.fixture
def optionen_jahr():
    """Simulationsoptionen für Jahressimulation"""
    return SimulationsOptionen(
        klimadatei="test",
    )

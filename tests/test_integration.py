"""
Integration Tests für RoomCurve (ISO 52016-1)
============================================

Testet das Zusammenspiel der Module.
"""

import pytest
import numpy as np
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from iso52016 import (
    load_climate, create_constant_climate,
    lade_gebaeude, simuliere, SimulationsOptionen,
)


# =============================================================================
# KLIMADATEN LADEN
# =============================================================================

class TestKlimadatenLaden:
    """Tests für Klimadaten-Import"""
    
    def test_try_laden(self, klima_try):
        """TRY-Datei vollständig laden"""
        assert len(klima_try.theta_e) == 8760
    
    def test_try_temperatur_plausibel(self, klima_try):
        """TRY-Temperaturen im realistischen Bereich"""
        assert np.min(klima_try.theta_e) > -30
        assert np.max(klima_try.theta_e) < 45
    
    def test_try_strahlung_hat_orientierungen(self, klima_try):
        """TRY hat Strahlung für alle Orientierungen"""
        assert 'N' in klima_try.I_sol
        assert 'S' in klima_try.I_sol
        assert 'E' in klima_try.I_sol
        assert 'W' in klima_try.I_sol
    
    def test_bestest_klima_laden(self, klima_bestest):
        """BESTEST-Klimadatei (DRYCOLD) laden"""
        assert len(klima_bestest.theta_e) == 8760
    
    def test_konstantes_klima(self, klima_konstant):
        """Konstantes Klima für Tests"""
        assert len(klima_konstant.theta_e) == 8760
        assert np.all(klima_konstant.theta_e == 10.0)


# =============================================================================
# SIMULATION MIT BESTEST-KONFIGURATION
# =============================================================================

class TestSimulationMitBestest:
    """Tests für Simulation mit BESTEST-Konfigurationen"""
    
    @pytest.mark.slow
    def test_case_600_durchlaeuft(self, bestest_dir):
        """BESTEST Case 600 Simulation läuft ohne Fehler"""
        configs_dir = bestest_dir / "configs"
        
        gebaeude = lade_gebaeude(
            str(configs_dir / "gebaeude_600.json"),
            str(configs_dir / "nutzung_600.json")
        )
        
        klima_file = bestest_dir / "klimadaten" / "DRYCOLD_52016_verifizierung.csv"
        klima = load_climate(str(klima_file), format='csv')
        
        optionen = SimulationsOptionen(klimadatei="test")
        ergebnisse = simuliere(gebaeude, klima, optionen)
        
        assert ergebnisse is not None
        assert 'gesamt' in ergebnisse
        assert 'Q_H_kWh' in ergebnisse['gesamt']
        assert 'Q_C_kWh' in ergebnisse['gesamt']
    
    @pytest.mark.slow
    def test_ergebnisse_plausibel(self, bestest_dir):
        """Simulationsergebnisse sind physikalisch plausibel"""
        configs_dir = bestest_dir / "configs"
        
        gebaeude = lade_gebaeude(
            str(configs_dir / "gebaeude_600.json"),
            str(configs_dir / "nutzung_600.json")
        )
        
        klima_file = bestest_dir / "klimadaten" / "DRYCOLD_52016_verifizierung.csv"
        klima = load_climate(str(klima_file), format='csv')
        
        optionen = SimulationsOptionen(klimadatei="test")
        ergebnisse = simuliere(gebaeude, klima, optionen)
        
        Q_H = ergebnisse['gesamt']['Q_H_kWh']
        Q_C = ergebnisse['gesamt']['Q_C_kWh']
        
        # Case 600 sollte Heiz- und Kühlbedarf haben
        assert Q_H > 1000  # Mindestens 1000 kWh Heizen
        assert Q_C > 1000  # Mindestens 1000 kWh Kühlen
        assert Q_H < 10000  # Nicht übermäßig viel
        assert Q_C < 10000

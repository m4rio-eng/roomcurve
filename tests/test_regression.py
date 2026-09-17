"""
Regression Tests für RoomCurve (ISO 52016-1)
===========================================

Fixierte Referenzwerte aus der validierten Version.
Erkennt unbeabsichtigte Änderungen am Berechnungsverhalten.
"""

import pytest
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from iso52016 import simuliere, lade_gebaeude, lade_optionen, lade_klimadaten


# =============================================================================
# BESTEST REFERENZWERTE
# =============================================================================

# Toleranz für Regression: ±50 kWh (ca. 1%)
TOLERANZ_KWH = 50

# Referenzwerte = Byte-Baseline dieses Stands (2026-07-28;
# DRYCOLD-Klima, f_HC = 1,0 nach Kap. 7.2.2.9). Scharfe Prüfung ist
# der cmp gegen ergebnisse_alle.json; dieser Test ist das grobe Netz.
# Testpfad identisch zum Harness:
# steuerung_<case>.json wird geladen (lade_optionen), nicht nachgebaut.
BESTEST_REFERENZ = {
    "600": {"Q_H": 5486, "Q_C": 7982},
    "610": {"Q_H": 5540, "Q_C": 5316},
    "620": {"Q_H": 5710, "Q_C": 4874},
    "630": {"Q_H": 6079, "Q_C": 3417},
    "640": {"Q_H": 3523, "Q_C": 7662},
    "650": {"Q_H": 0, "Q_C": 6276},
    "900": {"Q_H": 1906, "Q_C": 3556},
    "910": {"Q_H": 2241, "Q_C": 1590},
    "920": {"Q_H": 4114, "Q_C": 3084},
    "930": {"Q_H": 4926, "Q_C": 2118},
    "940": {"Q_H": 1319, "Q_C": 3433},
    "950": {"Q_H": 0, "Q_C": 1090},
}


# =============================================================================
# HILFSFUNKTIONEN
# =============================================================================

def run_bestest_case(case_id: str, bestest_dir: Path) -> dict:
    """Führt einen BESTEST-Case aus und gibt Ergebnisse zurück."""
    
    # Konfigurationen laden
    configs_dir = bestest_dir / "configs"
    
    gebaeude_json = configs_dir / f"gebaeude_{case_id}.json"
    nutzung_json = configs_dir / f"nutzung_{case_id}.json"
    
    if not gebaeude_json.exists():
        pytest.skip(f"Config für Case {case_id} nicht gefunden")
    
    steuerung_json = configs_dir / f"steuerung_{case_id}.json"
    if not steuerung_json.exists():
        pytest.skip(f"Steuerung für Case {case_id} nicht gefunden")
    
    gebaeude = lade_gebaeude(str(gebaeude_json), str(nutzung_json))
    
    # Optionen und Klima EXAKT wie der Harness (DRYCOLD, f_HC = 1,0, ...)
    optionen = lade_optionen(str(steuerung_json))
    klima = lade_klimadaten(optionen.klimadatei, optionen.klimaformat)
    
    ergebnisse = simuliere(gebaeude, klima, optionen)
    
    return {
        "Q_H": round(ergebnisse['gesamt']['Q_H_kWh']),
        "Q_C": round(ergebnisse['gesamt']['Q_C_kWh']),
    }


# =============================================================================
# REGRESSION TESTS - LEICHTBAU (600er)
# =============================================================================

class TestBestestLeichtbauRegression:
    """Regression Tests für BESTEST Leichtbau-Cases"""
    
    @pytest.mark.slow
    def test_case_600(self, bestest_dir):
        """Case 600: Basis Leichtbau"""
        erg = run_bestest_case("600", bestest_dir)
        ref = BESTEST_REFERENZ["600"]
        
        assert abs(erg["Q_H"] - ref["Q_H"]) < TOLERANZ_KWH, \
            f"Q_H: {erg['Q_H']} vs Ref {ref['Q_H']}"
        assert abs(erg["Q_C"] - ref["Q_C"]) < TOLERANZ_KWH, \
            f"Q_C: {erg['Q_C']} vs Ref {ref['Q_C']}"
    
    @pytest.mark.slow
    def test_case_610(self, bestest_dir):
        """Case 610: Süd-Verschattung"""
        erg = run_bestest_case("610", bestest_dir)
        ref = BESTEST_REFERENZ["610"]
        
        assert abs(erg["Q_H"] - ref["Q_H"]) < TOLERANZ_KWH
        assert abs(erg["Q_C"] - ref["Q_C"]) < TOLERANZ_KWH
    
    @pytest.mark.slow
    def test_case_620(self, bestest_dir):
        """Case 620: Ost/West-Fenster"""
        erg = run_bestest_case("620", bestest_dir)
        ref = BESTEST_REFERENZ["620"]
        
        assert abs(erg["Q_H"] - ref["Q_H"]) < TOLERANZ_KWH
        assert abs(erg["Q_C"] - ref["Q_C"]) < TOLERANZ_KWH
    
    @pytest.mark.slow
    def test_case_630(self, bestest_dir):
        """Case 630: Ost/West + Verschattung"""
        erg = run_bestest_case("630", bestest_dir)
        ref = BESTEST_REFERENZ["630"]
        
        assert abs(erg["Q_H"] - ref["Q_H"]) < TOLERANZ_KWH
        assert abs(erg["Q_C"] - ref["Q_C"]) < TOLERANZ_KWH
    
    @pytest.mark.slow
    def test_case_640(self, bestest_dir):
        """Case 640: Thermostat-Setback"""
        erg = run_bestest_case("640", bestest_dir)
        ref = BESTEST_REFERENZ["640"]
        
        assert abs(erg["Q_H"] - ref["Q_H"]) < TOLERANZ_KWH
        assert abs(erg["Q_C"] - ref["Q_C"]) < TOLERANZ_KWH
    
    @pytest.mark.slow
    def test_case_650(self, bestest_dir):
        """Case 650: Nachtlüftung"""
        erg = run_bestest_case("650", bestest_dir)
        ref = BESTEST_REFERENZ["650"]
        
        assert abs(erg["Q_H"] - ref["Q_H"]) < TOLERANZ_KWH
        assert abs(erg["Q_C"] - ref["Q_C"]) < TOLERANZ_KWH


# =============================================================================
# REGRESSION TESTS - MASSIVBAU (900er)
# =============================================================================

class TestBestestMassivbauRegression:
    """Regression Tests für BESTEST Massivbau-Cases"""
    
    @pytest.mark.slow
    def test_case_900(self, bestest_dir):
        """Case 900: Basis Massivbau"""
        erg = run_bestest_case("900", bestest_dir)
        ref = BESTEST_REFERENZ["900"]
        
        assert abs(erg["Q_H"] - ref["Q_H"]) < TOLERANZ_KWH
        assert abs(erg["Q_C"] - ref["Q_C"]) < TOLERANZ_KWH
    
    @pytest.mark.slow
    def test_case_910(self, bestest_dir):
        """Case 910: Süd-Verschattung Massiv"""
        erg = run_bestest_case("910", bestest_dir)
        ref = BESTEST_REFERENZ["910"]
        
        assert abs(erg["Q_H"] - ref["Q_H"]) < TOLERANZ_KWH
        assert abs(erg["Q_C"] - ref["Q_C"]) < TOLERANZ_KWH
    
    @pytest.mark.slow
    def test_case_920(self, bestest_dir):
        """Case 920: Ost/West-Fenster Massiv"""
        erg = run_bestest_case("920", bestest_dir)
        ref = BESTEST_REFERENZ["920"]
        
        assert abs(erg["Q_H"] - ref["Q_H"]) < TOLERANZ_KWH
        assert abs(erg["Q_C"] - ref["Q_C"]) < TOLERANZ_KWH
    
    @pytest.mark.slow
    def test_case_930(self, bestest_dir):
        """Case 930: Ost/West + Verschattung Massiv"""
        erg = run_bestest_case("930", bestest_dir)
        ref = BESTEST_REFERENZ["930"]
        
        assert abs(erg["Q_H"] - ref["Q_H"]) < TOLERANZ_KWH
        assert abs(erg["Q_C"] - ref["Q_C"]) < TOLERANZ_KWH
    
    @pytest.mark.slow
    def test_case_940(self, bestest_dir):
        """Case 940: Thermostat-Setback Massiv"""
        erg = run_bestest_case("940", bestest_dir)
        ref = BESTEST_REFERENZ["940"]
        
        assert abs(erg["Q_H"] - ref["Q_H"]) < TOLERANZ_KWH
        assert abs(erg["Q_C"] - ref["Q_C"]) < TOLERANZ_KWH
    
    @pytest.mark.slow
    def test_case_950(self, bestest_dir):
        """Case 950: Nachtlüftung Massiv"""
        erg = run_bestest_case("950", bestest_dir)
        ref = BESTEST_REFERENZ["950"]
        
        assert abs(erg["Q_H"] - ref["Q_H"]) < TOLERANZ_KWH
        assert abs(erg["Q_C"] - ref["Q_C"]) < TOLERANZ_KWH


# =============================================================================
# DELTA-TESTS (Unterschiede zwischen Cases)
# =============================================================================

class TestBestestDeltas:
    """Tests für Differenzen zwischen BESTEST-Cases"""
    
    @pytest.mark.slow
    def test_massiv_weniger_heizen(self, bestest_dir):
        """Massivbau (900) braucht weniger Heizenergie als Leichtbau (600)"""
        erg_600 = run_bestest_case("600", bestest_dir)
        erg_900 = run_bestest_case("900", bestest_dir)
        
        assert erg_900["Q_H"] < erg_600["Q_H"]
    
    @pytest.mark.slow
    def test_verschattung_reduziert_kuehlen(self, bestest_dir):
        """Verschattung (610) reduziert Kühlbedarf gegenüber Basis (600)"""
        erg_600 = run_bestest_case("600", bestest_dir)
        erg_610 = run_bestest_case("610", bestest_dir)
        
        assert erg_610["Q_C"] < erg_600["Q_C"]
    
    @pytest.mark.slow
    def test_nachtlueftung_reduziert_kuehlen(self, bestest_dir):
        """Nachtlüftung (650) reduziert Kühlbedarf gegenüber Basis (600)"""
        erg_600 = run_bestest_case("600", bestest_dir)
        erg_650 = run_bestest_case("650", bestest_dir)
        
        assert erg_650["Q_C"] < erg_600["Q_C"]

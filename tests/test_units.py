"""
Unit Tests für RoomCurve (ISO 52016-1)
=====================================

Testet einzelne Berechnungsfunktionen isoliert.
"""

import pytest
import numpy as np
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from iso52016.solar import I_SC, RHO_GROUND_DEFAULT, berechne_sonnenstand, Standort, DENVER
from iso52016.thermal_mass import Schicht, Massenklasse, berechne_kappa_m, bestimme_massenklasse


# =============================================================================
# KONSTANTEN
# =============================================================================

class TestKonstanten:
    """Tests für physikalische Konstanten"""
    
    def test_solarkonstante(self):
        """Solarkonstante nach ISO 52010-1, Tabelle 9"""
        assert I_SC == 1370.0
    
    def test_bodenalbedo_default(self):
        """Standard-Bodenalbedo"""
        assert RHO_GROUND_DEFAULT == 0.2
    
    def test_denver_koordinaten(self):
        """BESTEST-Standort Denver"""
        assert DENVER.breitengrad == pytest.approx(39.76, abs=0.1)
        assert DENVER.laengengrad == pytest.approx(-104.86, abs=0.1)
        assert DENVER.zeitzone == -7


# =============================================================================
# SONNENSTAND
# =============================================================================

class TestSonnenstand:
    """Tests für Sonnenstandsberechnung"""
    
    def test_sommersonnenwende_mittag(self):
        """21. Juni, Stundenabschnitt 13 (12-13 Uhr) - Sonne hoch, knapp westlich"""
        # Tag 172 = 21. Juni. stunde=12 (0-basiert) ist der Abschnitt 12-13 Uhr;
        # ausgewertet wird normkonform die Stundenmitte 12:30 (Gl. 9/10,
        # Gl. 9/10) - dort steht die Sonne bereits westlich von Sued.
        # Die fruehere Erwartung |phi| < 15 passte zur alten (falschen)
        # Stundenanfangs-Auswertung und war danach unzutreffend.
        ergebnis = berechne_sonnenstand(stunde=12, tag=172, standort=DENVER)
        
        # Sonnenhöhe sollte hoch sein (>70°)
        assert ergebnis.alpha_sol > 70
        # Azimut westlich von Süd (Nachmittag, ISO: West negativ)
        assert -35 < ergebnis.phi_sol < -10
    
    def test_wintersonnenwende_mittag(self):
        """21. Dezember 12:00 - Sonne tief"""
        # Tag 355 = 21. Dezember
        ergebnis = berechne_sonnenstand(stunde=12, tag=355, standort=DENVER)
        
        # Sonnenhöhe sollte niedrig sein (<35°)
        assert ergebnis.alpha_sol < 35
        assert ergebnis.alpha_sol > 0
    
    def test_nacht_keine_sonne(self):
        """Nachts keine Sonne über Horizont"""
        ergebnis = berechne_sonnenstand(stunde=2, tag=172, standort=DENVER)
        
        # Sonnenhöhe negativ oder null
        assert ergebnis.alpha_sol <= 0
    
    def test_sonnenaufgang_osten(self):
        """Morgens kommt Sonne aus Osten"""
        # 6:00 Uhr im Sommer
        ergebnis = berechne_sonnenstand(stunde=6, tag=172, standort=DENVER)
        
        # Azimut sollte im Osten sein (positiv, ca. 60-90°)
        if ergebnis.alpha_sol > 0:  # Falls schon aufgegangen
            assert ergebnis.phi_sol > 0


# =============================================================================
# THERMISCHE MASSE
# =============================================================================

class TestThermischeMasse:
    """Tests für Wärmekapazitätsberechnung nach ISO 13786"""
    
    def test_aussendaemmung_erkennung(self):
        """Außendämmung: Masse innen, Dämmung außen → Klasse I"""
        schichten = [
            Schicht(name="Beton", dicke_m=0.15, lambda_W_mK=2.0, rho_kg_m3=2400, c_J_kgK=1000),
            Schicht(name="Dämmung", dicke_m=0.10, lambda_W_mK=0.04, rho_kg_m3=30, c_J_kgK=1000),
        ]
        
        klasse = bestimme_massenklasse(schichten)
        assert klasse == Massenklasse.I
    
    def test_innendaemmung_erkennung(self):
        """Innendämmung: Dämmung innen, Masse außen → Klasse E"""
        schichten = [
            Schicht(name="Dämmung", dicke_m=0.05, lambda_W_mK=0.04, rho_kg_m3=30, c_J_kgK=1000),
            Schicht(name="Beton", dicke_m=0.20, lambda_W_mK=2.0, rho_kg_m3=2400, c_J_kgK=1000),
        ]
        
        klasse = bestimme_massenklasse(schichten)
        assert klasse == Massenklasse.E
    
    def test_kappa_berechnung(self):
        """Kappa-Berechnung für schwere Wand"""
        schichten = [
            Schicht(name="Beton", dicke_m=0.20, lambda_W_mK=2.0, rho_kg_m3=2400, c_J_kgK=1000),
        ]
        
        kappa = berechne_kappa_m(schichten)
        
        # Schwerer Beton → hohe Speichermasse
        assert kappa > 50_000  # J/(m²K)


# =============================================================================
# U-WERT / R-WERT
# =============================================================================

class TestUWert:
    """Tests für U-Wert Berechnungen"""
    
    def test_r_aus_schichten(self):
        """R = Σ(d/λ) für Schichten"""
        schichten = [
            Schicht(name="Dämmung", dicke_m=0.20, lambda_W_mK=0.04, rho_kg_m3=30, c_J_kgK=1000),
        ]
        
        R_summe = sum(s.dicke_m / s.lambda_W_mK for s in schichten)
        assert R_summe == pytest.approx(5.0, abs=0.01)
    
    def test_u_aus_r(self):
        """U = 1 / (Rsi + R + Rse)"""
        R_si = 0.13  # Innen
        R_se = 0.04  # Außen
        R_konstruktion = 5.0  # Dämmung
        
        U = 1.0 / (R_si + R_konstruktion + R_se)
        
        assert U == pytest.approx(0.193, abs=0.01)


# =============================================================================
# G-WERT / SONNENSCHUTZ
# =============================================================================

class TestGWert:
    """Tests für g-Wert und Sonnenschutz"""
    
    def test_g_eff_berechnung(self):
        """g_eff = g × Fc"""
        g_wert = 0.60
        Fc = 0.25  # Außenjalousie
        
        g_eff = g_wert * Fc
        
        assert g_eff == pytest.approx(0.15, abs=0.01)
    
    def test_fc_ohne_sonnenschutz(self):
        """Ohne Sonnenschutz: Fc = 1.0"""
        Fc = 1.0
        assert Fc == 1.0
    
    def test_fc_aussenjalousie(self):
        """Außenjalousie: Fc ≈ 0.25"""
        # Typischer Wert nach DIN 4108-2
        Fc_aussen = 0.25
        assert Fc_aussen < 0.5


# =============================================================================
# NUMERISCHE STABILITÄT
# =============================================================================

class TestNumerik:
    """Tests für numerische Stabilität"""
    
    def test_keine_division_durch_null(self):
        """Keine Division durch Null bei U=0"""
        # R = 1/U sollte abgefangen werden
        U = 0.0
        if U > 0:
            R = 1.0 / U
        else:
            R = float('inf')
        
        assert R == float('inf') or R > 1000
    
    def test_temperatur_plausibel(self):
        """Temperaturen in realistischem Bereich"""
        theta_min = -40  # °C
        theta_max = 50   # °C
        
        # Beispieltemperaturen
        temps = np.array([15.0, 20.0, 25.0, 30.0])
        
        assert np.all(temps > theta_min)
        assert np.all(temps < theta_max)


def test_k313_rahmenanteil_default_b21():
    """Der Eingabedefault des
    Rahmenanteils entspricht dem F_fr-Standardwert 0,25 aus
    Tabelle B.21 (informativ)."""
    from iso52016.simulation import Bauteil
    bt = Bauteil(id="f", name="f", typ="transparent", flaeche_m2=1.0,
                 azimut_deg=180, neigung_deg=90,
                 zone_innen="Z1", zone_aussen="AUL",
                 U_W_m2K=1.3, g_wert=0.6)
    assert bt.rahmenanteil == 0.25


def test_k44_a_tot_null_wird_laut():
    """Zone ohne Hüllflächen
    (A_tot = 0) wirft ValueError statt stiller Klemme auf 1 m²."""
    from iso52016.simulation import Zone
    zone = Zone(id="leer", name="leer", volumen_m3=10.0,
                nutzflaeche_m2=4.0, nutzungsprofil="test", bauteile=[])
    with pytest.raises(ValueError, match="A_tot"):
        zone.berechne_A_tot()


def test_k44_singulaere_matrix_wird_laut():
    """Singuläre Zonenmatrix
    wirft RuntimeError statt stillem 20-°C-Fallback."""
    import numpy as np
    from iso52016.simulation import _solve_zonenmatrix
    A = np.zeros((3, 3))
    B = np.ones(3)
    with pytest.raises(RuntimeError, match="singulär"):
        _solve_zonenmatrix(A, B, "Z_test", 42)


def test_k42_epsilon_entfernt_und_warnt(tmp_path):
    """Das tote Eingabefeld
    epsilon ist entfernt; ein JSON, das es setzt, löst eine Warnung
    mit Verweis auf h_re aus statt still ignoriert zu werden."""
    import json
    import warnings as w
    from iso52016 import lade_gebaeude
    from iso52016.simulation import Bauteil
    assert not hasattr(Bauteil(
        id="x", name="x", typ="opak", flaeche_m2=1.0, azimut_deg=0,
        neigung_deg=90, zone_innen="Z1", zone_aussen="AUL",
        R_c_m2K_W=1.0, kappa_m_kJ_m2K=10.0), "epsilon")
    geb = {
        "name": "t", "zonen": [{"id": "Z1", "name": "Z", "volumen_m3": 50.0,
                                 "nutzflaeche_m2": 20.0,
                                 "nutzungsprofil": "p"}],
        "bauteile": [{"id": "w", "typ": "opak", "flaeche_m2": 10.0,
                      "zone_innen": "Z1", "zone_aussen": "AUL",
                      "R_c_m2K_W": 2.0, "kappa_m_kJ_m2K": 50.0,
                      "epsilon": 0.85}]}
    nutz = {"profile": {"p": {"beschreibung": "t",
                              "interne_gewinne_W": [0.0] * 24,
                              "luftwechsel_1_h": 0.5}}}
    gp = tmp_path / "geb.json"
    np_ = tmp_path / "nutz.json"
    gp.write_text(json.dumps(geb))
    np_.write_text(json.dumps(nutz))
    with w.catch_warnings(record=True) as rec:
        w.simplefilter("always")
        lade_gebaeude(str(gp), str(np_))
    assert any("epsilon" in str(r.message) and "h_re" in str(r.message)
               for r in rec)


def test_k13_h_ri_h_re_defaults_tab25():
    """Die Defaults der
    Strahlungsübergänge entsprechen Tabelle 25 (h_lr;i = 5,13,
    h_lr;e = 4,14; Zwei-Quellen-verifiziert 27.07.). Die alten Werte
    5,5/4,0 hatten keine Normgrundlage."""
    from iso52016.simulation import (H_RI_DEFAULT, H_RE_DEFAULT,
                                     H_CE_DEFAULT, Bauteil)
    assert H_RI_DEFAULT == 5.13
    assert H_RE_DEFAULT == 4.14
    assert H_CE_DEFAULT == 20.0
    bt = Bauteil(id="w", name="w", typ="opak", flaeche_m2=1.0,
                 azimut_deg=0, neigung_deg=90,
                 zone_innen="Z1", zone_aussen="AUL",
                 R_c_m2K_W=1.0, kappa_m_kJ_m2K=10.0)
    assert bt.h_ri == 5.13 and bt.h_re == 4.14


@pytest.mark.parametrize("neigung,erwartet", [
    (0.0, 5.0),     # Dach: Wärmestrom aufwärts
    (45.0, 5.0),    # Grenze einschließlich
    (90.0, 2.5),    # Wand: horizontal
    (134.9, 2.5),
    (135.0, 0.7),   # abwärts weisend
    (180.0, 0.7),   # Boden: Wärmestrom abwärts
])
def test_k27_h_ci_automatik_nach_richtung(neigung, erwartet):
    """Die h_ci-Automatik folgt der
    Richtungslogik der Tabelle 25 (5,0/2,5/0,7), unabhängig von der
    Randbedingung — auch für ADIABAT/Nachbarzone."""
    from iso52016.simulation import Bauteil
    for za in ("AUL", "ADIABAT"):
        bt = Bauteil(id="x", name="x", typ="opak", flaeche_m2=1.0,
                     azimut_deg=0, neigung_deg=neigung,
                     zone_innen="Z1", zone_aussen=za,
                     R_c_m2K_W=1.0, kappa_m_kJ_m2K=10.0)
        assert bt.h_ci == pytest.approx(erwartet), za


def test_k27_explizites_h_ci_bleibt():
    """Sentinel-Schutz: ein EXPLIZIT gesetztes h_ci = 2,5 wird auf
    einem Dach nicht mehr von der Automatik überschrieben."""
    from iso52016.simulation import Bauteil
    bt = Bauteil(id="d", name="d", typ="opak", flaeche_m2=1.0,
                 azimut_deg=0, neigung_deg=0.0,
                 zone_innen="Z1", zone_aussen="AUL",
                 R_c_m2K_W=1.0, kappa_m_kJ_m2K=10.0, h_ci=2.5)
    assert bt.h_ci == 2.5


def test_k27_erd_vorrang():
    """ERD hat Vorrang vor der Neigung — Bestandsmodelle (GUI,
    Fixtures) tragen Erdböden mit Neigung 0 ein; Wärmestrom ist dort
    per Definition abwärts (0,7). Altverhalten bleibt erhalten."""
    from iso52016.simulation import Bauteil
    for neigung in (0.0, 90.0, 180.0):
        bt = Bauteil(id="b", name="b", typ="opak", flaeche_m2=1.0,
                     azimut_deg=0, neigung_deg=neigung,
                     zone_innen="Z1", zone_aussen="ERD",
                     R_c_m2K_W=2.5, kappa_m_kJ_m2K=50.0)
        assert bt.h_ci == pytest.approx(0.7), neigung


def test_k21_rho_c_luft_tab20():
    """ρ_a·c_a entspricht
    Tabelle 20 (1,204 · 1006; Zwei-Quellen-verifiziert 27.07.).
    Vorher normfremd 1,2 · 1000."""
    from iso52016.simulation import RHO_LUFT, C_LUFT
    assert RHO_LUFT == 1.204
    assert C_LUFT == 1006.0


def test_k21_hoehenfaktor_tab20_fn_b():
    """Höhenkorrektur Tab. 20 Fn. b: (1 − 0,00651·h/288)^4,255.
    Prüfpunkte: h = 0 → 1; h = 1609 m → ≈ 0,854 (Normtext 7.2.2.14
    nennt 'ungefähr 80 %' als Grobangabe; der 0,822-ACH-Faktor der
    Prüffälle ist die dort festgelegte externe Pauschale)."""
    from iso52016.simulation import hoehenfaktor_luftdichte
    assert hoehenfaktor_luftdichte(0.0) == pytest.approx(1.0)
    f1609 = hoehenfaktor_luftdichte(1609.0)
    assert 0.80 < f1609 < 0.90
    # Monotonie
    assert hoehenfaktor_luftdichte(500.0) > f1609


def test_k21_hoehenkorrektur_opt_in():
    """Die Höhenkorrektur ist OPT-IN (standort_hoehe_m, Default None)
    und darf NICHT automatisch aus dem Klimaheader kommen (externe
    0,822-ACH-Korrektur der Prüffälle → Doppelkorrektur)."""
    from iso52016.simulation import SimulationsOptionen
    opt = SimulationsOptionen(klimadatei="x")
    assert opt.standort_hoehe_m is None

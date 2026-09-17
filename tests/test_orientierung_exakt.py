"""
Echte Element-Orientierung statt 5-Richtungs-Raster.

Normbasis: Gl. (41)/(69) der 52016-1 verlangen die Bestrahlungsstärke mit
den tatsächlichen Winkeln β/γ des Elements aus dem EPB-Modul M1-13
(= ISO 52010-1). Die 45°-Rundungsempfehlung (Anm. 3 zu Gl. 123) betrifft
nur die Horizontsegmente des monatsbezogenen Anhang-F-Verfahrens.
Seitenbild geprüft 22.07.2026 (S. 96/110/135).

Verifiziert hier:
  1. Raster-Erkennung (Spezialfall bleibt Raster → bitidentischer CSV-Pfad)
  2. Exakte Kette == Raster-Kette für Rasterorientierungen
  3. Key-Auflösung in baue_zonenmatrix (exakt vor Raster, Fallback sicher)
  4. simuliere() berechnet Zusatzorientierungen vor und nutzt sie
"""

import numpy as np
import pytest

from iso52016.climate import (
    ClimateData, Location, compute_all_orientations, ergaenze_orientierung,
)
from iso52016.simulation import (
    orientierung_key_exakt, orientierung_zu_key, _bt_orientierungs_key,
    baue_zonenmatrix, simuliere,
    Gebaeude, Zone, Bauteil, Nutzungsprofil, SimulationsOptionen,
)


# ---------------------------------------------------------------------------
# 1. Raster-Erkennung
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("azimut,neigung", [
    (0, 90), (90, 90), (180, 90), (270, 90),   # N/E/S/W
    (0, 0), (123, 0),                           # horizontal, Azimut egal
    (360, 90),                                  # 360 ≡ 0
])
def test_raster_bleibt_raster(azimut, neigung):
    assert orientierung_key_exakt(azimut, neigung) is None


@pytest.mark.parametrize("azimut,neigung", [
    (135, 90),    # Südost-Fassade
    (180, 30),    # geneigtes Süddach
    (180, 45),    # 45°-Dach (Raster hätte 'S' geliefert)
    (0, 180),     # abwärts weisend (BESTEST-Boden-Geometrie)
    (200, 90),    # Zwischenazimut
])
def test_exakter_key_fuer_nicht_raster(azimut, neigung):
    key = orientierung_key_exakt(azimut, neigung)
    assert key is not None and key.startswith("A")


# ---------------------------------------------------------------------------
# Synthetisches Klima mit DNI/DHI (Denver, 48 h)
# ---------------------------------------------------------------------------

def _klima_mit_rohdaten(n_stunden=48) -> ClimateData:
    loc = Location(name="Denver", latitude=39.76, longitude=-104.86,
                   timezone=-7.0, elevation=1609.0)
    theta_e = np.full(n_stunden, 10.0)
    DNI = np.zeros(n_stunden)
    DHI = np.zeros(n_stunden)
    for h in range(n_stunden):
        std = h % 24
        if 8 <= std <= 16:
            DNI[h] = 600.0
            DHI[h] = 120.0
    klima = ClimateData(n_hours=n_stunden, theta_e=theta_e,
                        DNI=DNI, DHI=DHI, location=loc)
    compute_all_orientations(klima, loc)
    return klima


# ---------------------------------------------------------------------------
# 2. Exakte Kette == Raster-Kette für Rasterorientierungen
# ---------------------------------------------------------------------------

def test_exakte_kette_identisch_zu_raster_sued():
    """Charakterisiert den Spezialfall: gleiche Kette, gleiche Werte."""
    klima = _klima_mit_rohdaten()
    ergaenze_orientierung(klima, "TESTKEY_S", azimut_iso_deg=0.0,
                          neigung_deg=90.0)
    assert np.array_equal(klima.I_sol_dir["TESTKEY_S"], klima.I_sol_dir["S"])
    assert np.array_equal(klima.I_sol_dif["TESTKEY_S"], klima.I_sol_dif["S"])
    assert np.array_equal(klima.I_sol["TESTKEY_S"], klima.I_sol["S"])


def test_zwischenorientierung_liegt_physikalisch_plausibel():
    """SO-Fassade: Tagessumme zwischen reiner O- und S-Summe nicht nötig,
    aber > 0 und ungleich beiden Rasterwerten (Raster hätte 'S' geliefert)."""
    klima = _klima_mit_rohdaten()
    ergaenze_orientierung(klima, "A135_T90", azimut_iso_deg=45.0,
                          neigung_deg=90.0)
    summe_so = klima.I_sol["A135_T90"].sum()
    assert summe_so > 0.0
    assert summe_so != pytest.approx(klima.I_sol["S"].sum())
    assert summe_so != pytest.approx(klima.I_sol["E"].sum())


# ---------------------------------------------------------------------------
# 3. Key-Auflösung
# ---------------------------------------------------------------------------

def test_key_aufloesung_exakt_vor_raster():
    bt = Bauteil(id="x", name="x", typ="opak", flaeche_m2=1.0,
                 azimut_deg=135, neigung_deg=90,
                 zone_innen="Z1", zone_aussen="AUL",
                 R_c_m2K_W=1.0, kappa_m_kJ_m2K=10.0)
    dicts_mit_exakt = {"S": 100.0, "A135_T90": 250.0}
    dicts_ohne_exakt = {"S": 100.0}

    bt.orientierung_key = "A135_T90"
    assert _bt_orientierungs_key(bt, dicts_mit_exakt) == "A135_T90"
    # Fallback: exakter Key nicht in den Daten (z. B. direkter Aufruf
    # mit Raster-Dicts) -> Raster-Zuordnung, kein KeyError
    assert _bt_orientierungs_key(bt, dicts_ohne_exakt) == "S"

    bt.orientierung_key = None
    assert _bt_orientierungs_key(bt, dicts_mit_exakt) == "S"
    assert (_bt_orientierungs_key(bt, dicts_mit_exakt)
            == orientierung_zu_key(135, 90))


# ---------------------------------------------------------------------------
# 4. Ende-zu-Ende: simuliere() nutzt die exakte Orientierung
# ---------------------------------------------------------------------------

def _gebaeude_mit_so_wand() -> Gebaeude:
    bauteile = [
        Bauteil(id="so_wand", name="SO Wand", typ="opak",
                flaeche_m2=10.0, azimut_deg=135, neigung_deg=90,
                zone_innen="Z1", zone_aussen="AUL",
                R_c_m2K_W=3.5, kappa_m_kJ_m2K=50.0),
        Bauteil(id="dach", name="Dach", typ="opak",
                flaeche_m2=20.0, azimut_deg=0, neigung_deg=0,
                zone_innen="Z1", zone_aussen="AUL",
                R_c_m2K_W=5.0, kappa_m_kJ_m2K=50.0),
    ]
    zone = Zone(id="Z1", name="Z", volumen_m3=50.0, nutzflaeche_m2=20.0,
                nutzungsprofil="test", bauteile=bauteile)
    zone.berechne_A_tot()
    profil = Nutzungsprofil(
        id="test", beschreibung="Test",
        heizen_C=[20.0] * 24, kuehlen_C=[26.0] * 24,
        interne_gewinne_W=[0.0] * 24, luftwechsel_1_h=[0.5] * 24)
    return Gebaeude(name="T", beschreibung="T",
                    zonen={"Z1": zone}, nutzungsprofile={"test": profil})


def test_simuliere_berechnet_zusatzorientierung_vor():
    klima = _klima_mit_rohdaten(48)
    gebaeude = _gebaeude_mit_so_wand()
    optionen = SimulationsOptionen(klimadatei="test")
    simuliere(gebaeude, klima, optionen)

    bt = gebaeude.zonen["Z1"].bauteile[0]
    assert bt.orientierung_key == "A135_T90"
    assert "A135_T90" in klima.I_sol
    assert "A135_T90" in klima.I_sol_dir and "A135_T90" in klima.I_sol_dif
    # Dach bleibt Raster
    assert gebaeude.zonen["Z1"].bauteile[1].orientierung_key is None


def test_simuliere_ohne_dni_faellt_aufs_raster():
    """Direktspalten-Pfad: keine DNI/DHI -> Raster-Fallback, kein Fehler."""
    n = 48
    raster = {k: np.full(n, 100.0) for k in ['N', 'E', 'S', 'W', 'H']}
    klima = ClimateData(n_hours=n, theta_e=np.full(n, 10.0),
                        I_sol={k: v.copy() for k, v in raster.items()})
    gebaeude = _gebaeude_mit_so_wand()
    optionen = SimulationsOptionen(klimadatei="test")
    simuliere(gebaeude, klima, optionen)
    bt = gebaeude.zonen["Z1"].bauteile[0]
    assert bt.orientierung_key is None
    assert "A135_T90" not in klima.I_sol

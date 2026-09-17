#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests für das zweite interne Quellprofil (interne_gewinne_2_W /
f_int_2_konv), eingeführt für VDI-6020-Testbeispiel 5
(Fenster-Solargewinne "im Raum" mit eigenem Konvektivanteil a_kon = 0,09
neben der Personen-/Maschinenlast mit anderem Split).

Geprüft wird:
  1. Default-Neutralität: Profil None -> identisches Verhalten wie ohne
     das Feature (Grundlage der Bitidentisch-Deklaration).
  2. Äquivalenz: Quelle 2 mit f_int_2_konv == f_int_konv wirkt exakt wie
     dieselbe Leistung auf Quelle 1.
  3. Konvektiv/strahlend-Wirkung: rein konvektive Quelle 2 hebt θ_air
     stärker und schneller als eine rein strahlende gleicher Leistung
     (die zuerst die Flächen lädt).
  4. Loader: lade_gebaeude übernimmt interne_gewinne_2_W und
     f_int_2_konv aus dem Nutzungs-JSON.
"""

import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from iso52016 import (Klimadaten, lade_gebaeude, SimulationsOptionen,
                      simuliere)


STUNDEN = 10 * 24


def _klima():
    leer = {k: np.zeros(STUNDEN) for k in ['N', 'E', 'S', 'W', 'H']}
    return Klimadaten(
        n_hours=STUNDEN, theta_e=np.full(STUNDEN, 10.0),
        I_sol={k: v.copy() for k, v in leer.items()},
        I_sol_dir={k: v.copy() for k, v in leer.items()},
        I_sol_dif={k: v.copy() for k, v in leer.items()})


def _gebaeude(tmp_path, gewinne1, f1, gewinne2, f2):
    geb = {
        "projekt": {"name": "Testbox Quelle 2"},
        "zonen": [{"id": "Z", "name": "Z", "volumen_m3": 50.0,
                   "nutzflaeche_m2": 20.0, "nutzungsprofil": "P",
                   "kapazitaet_Wh_K": 17.0}],
        "bauteile": [
            {"id": "W1", "name": "Wand", "typ": "opak", "flaeche_m2": 40.0,
             "azimut_deg": 180, "neigung_deg": 90, "zone_innen": "Z",
             "zone_aussen": "AUL", "R_c_m2K_W": 2.0,
             "kappa_m_kJ_m2K": 150.0, "massenklasse": "D",
             "alpha_sol": 0.0, "h_re_W_m2K": 0.0},
            {"id": "F1", "name": "Fenster", "typ": "transparent",
             "flaeche_m2": 4.0, "azimut_deg": 180, "neigung_deg": 90,
             "zone_innen": "Z", "zone_aussen": "AUL", "U_W_m2K": 1.3,
             "g_wert": 0.0, "rahmenanteil": 0.0, "h_re_W_m2K": 0.0},
        ],
        "simulation": {"initialisierung_tage": 0},
    }
    nutz = {"profile": {"P": {
        "solltemperaturen": {"heizen_C": [-999.0] * 24,
                             "kuehlen_C": [999.0] * 24},
        "interne_gewinne_W": gewinne1,
        "f_int_konv": f1,
        "luftwechsel_1_h": [0.0] * 24,
        "regelung_nach_luft": True,
    }}}
    if gewinne2 is not None:
        nutz["profile"]["P"]["interne_gewinne_2_W"] = gewinne2
        nutz["profile"]["P"]["f_int_2_konv"] = f2
    gp = tmp_path / "geb.json"
    np_ = tmp_path / "nutz.json"
    gp.write_text(json.dumps(geb))
    np_.write_text(json.dumps(nutz))
    return lade_gebaeude(str(gp), str(np_))


def _lauf(gebaeude):
    opt = SimulationsOptionen(klimadatei="test")
    opt.init_tage = 0
    erg = simuliere(gebaeude, _klima(), opt)
    z = erg['zonen']['Z']['stunden']
    return np.array([h['theta_air'] for h in z])


def test_default_neutral(tmp_path):
    """Ohne Quelle 2 (None) identisch zu 'Feature nicht vorhanden'."""
    g1 = _gebaeude(tmp_path, [300.0] * 24, 0.5, None, None)
    a = _lauf(g1)
    g2 = _gebaeude(tmp_path, [300.0] * 24, 0.5, [0.0] * 24, 1.0)
    b = _lauf(g2)
    assert np.array_equal(a, b)


def test_aequivalenz_zu_quelle_1(tmp_path):
    """Gleicher Split -> Quelle 2 wirkt exakt wie Aufstockung Quelle 1."""
    g1 = _gebaeude(tmp_path, [500.0] * 24, 0.4, None, None)
    a = _lauf(g1)
    g2 = _gebaeude(tmp_path, [200.0] * 24, 0.4, [300.0] * 24, 0.4)
    b = _lauf(g2)
    assert np.allclose(a, b, atol=1e-9)


def test_konvektiv_wirkt_auf_luft(tmp_path):
    """Rein konvektive Quelle 2 hebt θ_air in der ersten Laststunde
    stärker als rein strahlende gleicher Leistung."""
    profil = [0.0] * 24
    for h in range(6, 18):
        profil[h] = 800.0
    g_konv = _gebaeude(tmp_path, [0.0] * 24, 1.0, profil, 1.0)
    g_rad = _gebaeude(tmp_path, [0.0] * 24, 1.0, profil, 0.0)
    a_konv = _lauf(g_konv)
    a_rad = _lauf(g_rad)
    # Erste Laststunde des ersten Tages: konvektiv deutlich vorn
    assert a_konv[6] > a_rad[6] + 1.0
    # Energieerhaltung: In den Nachtstunden (Quelle aus) zählt nur die
    # gespeicherte Energie — dort müssen beide Varianten fast gleich
    # liegen. (Die TAGESmittel der Luft dürfen dagegen differieren:
    # konvektiv liegt die Luft über, strahlend unter den Flächen.)
    nacht = list(range(-24, -18))  # Stunden 0-5 des letzten Tages
    assert np.max(np.abs(a_konv[nacht] - a_rad[nacht])) < 0.3


def test_loader_uebernimmt_felder(tmp_path):
    g = _gebaeude(tmp_path, [0.0] * 24, 1.0, [123.0] * 24, 0.09)
    np_obj = g.nutzungsprofile['P']
    assert np_obj.interne_gewinne_2_W == [123.0] * 24
    assert np_obj.f_int_2_konv == pytest.approx(0.09)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests für die Horizontverschattung des Direktanteils.

Normbezug: Grenzfall "fernes Hindernis" von Gl. (F.10), ISO 52016-1
Anhang F — Sonnenhöhe ≤ Horizontwinkel ⇒ Direktanteil blockiert;
Diffusanteil bleibt (Anhang-F-Verfahren 1). Der Horizontwinkel hat
KEINE langwellige Wirkung: F_sky ist nach Gl. (70)/Tab. B.18 rein
neigungsbestimmt (Gl. 70 / Tab. B.18).
"""

import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from iso52016 import (Klimadaten, lade_gebaeude, SimulationsOptionen,
                      simuliere)
from iso52016.simulation import (berechne_F_sh_horizont_stuendlich,
                                 berechne_sonnenstand)


from iso52016.solar import Standort

STANDORT = Standort(name="Denver-Test", breitengrad=39.76, laengengrad=-104.86, zeitzone=-7.0)


def test_funktion_grenzen():
    """Winkel 0 → immer frei; Winkel 90 → tags immer blockiert."""
    for std in range(24):
        assert berechne_F_sh_horizont_stuendlich(
            std, 172, STANDORT, 0.0) == 1.0
    tags = [std for std in range(24)
            if berechne_sonnenstand(std, 172, STANDORT).alpha_sol > 0]
    assert tags, "Sonnenstand liefert keinen Tag?"
    for std in tags:
        assert berechne_F_sh_horizont_stuendlich(
            std, 172, STANDORT, 90.0) == 0.0


def test_funktion_schwelle():
    """Blockade genau bei Sonnenhöhe ≤ Winkel; darüber frei."""
    # Mittagsstunde im Sommer: hohe Sonne
    erg = berechne_sonnenstand(12, 172, STANDORT)
    assert erg.alpha_sol > 40
    assert berechne_F_sh_horizont_stuendlich(
        12, 172, STANDORT, erg.alpha_sol - 5.0) == 1.0
    assert berechne_F_sh_horizont_stuendlich(
        12, 172, STANDORT, erg.alpha_sol + 5.0) == 0.0


def _gebaeude(tmp_path, horizont_deg):
    geb = {
        "projekt": {"name": "Horizonttest"},
        "zonen": [{"id": "Z", "name": "Z", "volumen_m3": 50.0,
                   "nutzflaeche_m2": 20.0, "nutzungsprofil": "P",
                   "kapazitaet_Wh_K": 17.0}],
        "bauteile": [
            {"id": "AW", "name": "Wand Süd", "typ": "opak",
             "flaeche_m2": 10.0, "azimut_deg": 180, "neigung_deg": 90,
             "zone_innen": "Z", "zone_aussen": "AUL",
             "R_c_m2K_W": 2.0, "kappa_m_kJ_m2K": 100.0,
             "massenklasse": "D", "alpha_sol": 0.6,
             "horizont_winkel_deg": horizont_deg},
            {"id": "F", "name": "Fenster Süd", "typ": "transparent",
             "flaeche_m2": 6.0, "azimut_deg": 180, "neigung_deg": 90,
             "zone_innen": "Z", "zone_aussen": "AUL", "U_W_m2K": 1.3,
             "g_wert": 0.6, "rahmenanteil": 0.0,
             "horizont_winkel_deg": horizont_deg},
        ],
        "simulation": {"initialisierung_tage": 0},
    }
    nutz = {"profile": {"P": {
        "solltemperaturen": {"heizen_C": [-999.0] * 24,
                             "kuehlen_C": [999.0] * 24},
        "interne_gewinne_W": [0.0] * 24,
        "luftwechsel_1_h": [0.0] * 24,
    }}}
    gp = tmp_path / f"geb_{horizont_deg}.json"
    np_ = tmp_path / f"nutz_{horizont_deg}.json"
    gp.write_text(json.dumps(geb))
    np_.write_text(json.dumps(nutz))
    return lade_gebaeude(str(gp), str(np_))


def _klima(stunden=48):
    theta = np.full(stunden, 10.0)
    dir_s = np.zeros(stunden)
    dif_s = np.zeros(stunden)
    for h in range(stunden):
        if 8 <= h % 24 <= 16:
            dir_s[h] = 500.0
            dif_s[h] = 100.0
    leer = lambda: {k: np.zeros(stunden) for k in ['N', 'E', 'S', 'W', 'H']}
    I, Id, Idf = leer(), leer(), leer()
    I['S'] = dir_s + dif_s
    Id['S'] = dir_s
    Idf['S'] = dif_s
    return Klimadaten(n_hours=stunden, theta_e=theta,
                      I_sol=I, I_sol_dir=Id, I_sol_dif=Idf)


def _endtemp(gebaeude):
    opt = SimulationsOptionen(klimadatei="test")
    opt.init_tage = 0
    erg = simuliere(gebaeude, _klima(), opt)
    stunden = erg['zonen']['Z']['stunden']
    return np.array([h['theta_air'] for h in stunden])


def test_integration_horizont_reduziert_solareintrag(tmp_path):
    """Horizont 90°: nur Diffus wirkt; Zone bleibt deutlich kühler als
    ohne Horizont, aber wärmer als ganz ohne Sonne (Diffus bleibt)."""
    a_frei = _endtemp(_gebaeude(tmp_path, 0.0))
    a_block = _endtemp(_gebaeude(tmp_path, 90.0))
    # Mittags des zweiten Tages: freier Horizont deutlich wärmer
    assert a_frei[36] > a_block[36] + 1.0
    # Diffus wirkt weiter: blockierte Variante wärmer als die
    # Außentemperatur (10 °C) es allein erklären würde
    assert a_block[36] > 11.0


def test_integration_niedriger_horizont_kleiner_effekt(tmp_path):
    """Horizont 5°: Die Simulation läuft auf Jahresstunden 0–47
    (Januartage); dort blockiert ein 5°-Horizont korrekt nur die
    Randstunden mit Sonnenhöhe ≤ 5°. Der Effekt muss daher klein und
    monoton sein: nie wärmer als frei, aber deutlich näher an frei
    als die 90°-Vollblockade."""
    a_frei = _endtemp(_gebaeude(tmp_path, 0.0))
    a_niedrig = _endtemp(_gebaeude(tmp_path, 5.0))
    a_block = _endtemp(_gebaeude(tmp_path, 90.0))
    assert a_niedrig[36] <= a_frei[36] + 1e-9
    assert (a_frei[36] - a_niedrig[36]) < 0.3 * (a_frei[36] - a_block[36])


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))

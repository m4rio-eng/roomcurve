#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Loader-Ankunftstests: vormals tote
JSON-Felder erreichen jetzt die Rechenpfade. Je Feld ein Testfall
(Ankunft eines Nicht-Default-Werts auf dem geladenen Objekt).

Die FUNKTIONALE Wirkung der Felder ist andernorts abgedeckt
(F_sh_stundenwerte: test_anhang_f_geometrie-Kaskadentests;
Sonnenschutz/DIN-4108-Logik: Z. 1024–1063/1164–1227, im Default
inaktiv = Standardwerte).
"""

import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from iso52016 import lade_gebaeude


def _lade(tmp_path, bt_extra=None, np_extra=None):
    geb = {
        "name": "t",
        "zonen": [{"id": "Z1", "name": "Z", "volumen_m3": 50.0,
                   "nutzflaeche_m2": 20.0, "nutzungsprofil": "p"}],
        "bauteile": [{"id": "fe", "typ": "transparent", "flaeche_m2": 4.0,
                      "azimut_deg": 180, "neigung_deg": 90,
                      "zone_innen": "Z1", "zone_aussen": "AUL",
                      "U_W_m2K": 1.3, "g_wert": 0.6,
                      **(bt_extra or {})}],
    }
    nutz = {"profile": {"p": {"beschreibung": "t",
                              "interne_gewinne_W": [0.0] * 24,
                              "luftwechsel_1_h": 0.5,
                              **(np_extra or {})}}}
    gp = tmp_path / "geb.json"
    npf = tmp_path / "nutz.json"
    gp.write_text(json.dumps(geb))
    npf.write_text(json.dumps(nutz))
    gebaeude = lade_gebaeude(str(gp), str(npf))
    bt = gebaeude.zonen["Z1"].bauteile[0]
    profil = gebaeude.nutzungsprofile["p"]
    return bt, profil


BAUTEIL_FELDER = [
    ("sonnenschutz_steuerung", "manuell"),
    ("sonnenschutz_grenzwerte", "eigene"),
    ("sonnenschutz_schwelle_eigene", 150.0),
    ("sonnenschutz_modus", "automatik_wg"),
    ("ist_nwg", True),
    ("g_wert_basis", 0.55),
    ("Fc_aktiviert", 0.25),
    ("Fc_offen", 0.9),
]


@pytest.mark.parametrize("feld,wert", BAUTEIL_FELDER)
def test_k41_bauteilfeld_kommt_an(tmp_path, feld, wert):
    bt, _ = _lade(tmp_path, bt_extra={feld: wert})
    assert getattr(bt, feld) == wert


def test_k41_f_sh_stundenwerte_kommen_an(tmp_path):
    """F_sh_stundenwerte (normrelevant, Anhang F Anm. 2): JSON-Liste
    wird als float-Array geladen und stundengenau übernommen."""
    werte = [1.0] * 8760
    werte[100] = 0.4
    bt, _ = _lade(tmp_path, bt_extra={"F_sh_stundenwerte": werte})
    assert isinstance(bt.F_sh_stundenwerte, np.ndarray)
    assert bt.F_sh_stundenwerte.dtype == float
    assert bt.F_sh_stundenwerte[100] == pytest.approx(0.4)
    assert bt.F_sh_stundenwerte[99] == pytest.approx(1.0)
    # Default bleibt None (Neutralpfad)
    bt2, _ = _lade(tmp_path)
    assert bt2.F_sh_stundenwerte is None


NUTZUNG_FELDER = [
    ("lueftung_modus", "din4108"),
    ("aufenthaltszeit_stunden", [8, 9, 10, 11]),
    ("taglueftung_erhoht_ach", 2.5),
]


@pytest.mark.parametrize("feld,wert", NUTZUNG_FELDER)
def test_k41_nutzungsfeld_kommt_an(tmp_path, feld, wert):
    _, profil = _lade(tmp_path, np_extra={feld: wert})
    assert getattr(profil, feld) == wert


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))

"""
Verschattung opaker Flächen nach Gl. (41), 6.5.6.3.5.

F_sh,obst wirkt am äußeren Oberflächenknoten opaker Elemente nur auf den
Direktanteil; der Diffusanteil (inkl. Bodenreflexion) bleibt unverschattet
(Anhang F.1 a)/b), Verfahren 1). Am Seitenbild verifiziert 22.07.2026.

Prüfansatz: baue_zonenmatrix zweimal mit identischen Eingaben, nur
F_sh_obst_dir der Südwand variiert. Die Differenz des B-Vektors am
äußeren Knoten der Südwand muss exakt a_sol · A · ΔF_sh · I_dir sein —
unabhängig von I_dif.
"""

import numpy as np
import pytest

from iso52016.simulation import (
    baue_zonenmatrix, Zone, Bauteil, Nutzungsprofil, SimulationsOptionen,
)


def _mini_zone(f_sh_dir: float) -> Zone:
    """Einzonige Minimalzone: eine opake Südwand + adiabatischer Rest."""
    bauteile = [
        Bauteil(
            id="sued_wand", name="Süd Wand", typ="opak",
            flaeche_m2=10.0, azimut_deg=180, neigung_deg=90,
            zone_innen="Z1", zone_aussen="AUL",
            R_c_m2K_W=3.5, kappa_m_kJ_m2K=50.0,
            F_sh_obst_dir=f_sh_dir,
        ),
        Bauteil(
            id="rest", name="Rest (adiabat)", typ="opak",
            flaeche_m2=30.0, azimut_deg=0, neigung_deg=90,
            zone_innen="Z1", zone_aussen="ADIABAT",
            R_c_m2K_W=3.5, kappa_m_kJ_m2K=50.0,
        ),
    ]
    zone = Zone(
        id="Z1", name="Testzone", volumen_m3=100.0, nutzflaeche_m2=40.0,
        nutzungsprofil="test", bauteile=bauteile,
    )
    zone.berechne_A_tot()
    return zone


def _nutzung() -> Nutzungsprofil:
    return Nutzungsprofil(
        id="test", beschreibung="Test",
        heizen_C=[20.0] * 24, kuehlen_C=[26.0] * 24,
        interne_gewinne_W=[0.0] * 24, luftwechsel_1_h=[0.5] * 24,
    )


def _matrix(f_sh_dir, I_dir, I_dif):
    zone = _mini_zone(f_sh_dir)
    optionen = SimulationsOptionen(klimadatei="test")
    I_dir_dict = {"S": I_dir}
    I_dif_dict = {"S": I_dif}
    I_ges_dict = {"S": I_dir + I_dif}
    A, B, idx = baue_zonenmatrix(
        zone, theta_e=10.0, I_sol_dict=I_ges_dict,
        randbedingungen={}, nachbar_temps={},
        optionen=optionen, nutzung=_nutzung(),
        stunde_tag=12, stunde_jahr=12,
        I_sol_dir_dict=I_dir_dict, I_sol_dif_dict=I_dif_dict,
    )
    zone_alpha = zone.bauteile[0].alpha_sol
    return A, B, zone_alpha


def test_f_sh_wirkt_nur_auf_direktanteil():
    """ΔB am äußeren Knoten = a_sol · A · ΔF_sh · I_dir (Gl. 41)."""
    I_dir, I_dif = 300.0, 100.0
    A1, B1, alpha = _matrix(1.0, I_dir, I_dif)
    A2, B2, _ = _matrix(0.5, I_dir, I_dif)

    # Systemmatrix darf sich nicht ändern (F_sh steht nur in B)
    assert np.array_equal(A1, A2)

    delta = B1[0] - B2[0]  # äußerer Knoten der Südwand = Zeile 0
    erwartet = alpha * 10.0 * (1.0 - 0.5) * I_dir
    assert delta == pytest.approx(erwartet, rel=1e-12)

    # Alle anderen B-Einträge unverändert
    rest1 = np.delete(B1, 0)
    rest2 = np.delete(B2, 0)
    assert np.array_equal(rest1, rest2)


def test_diffusanteil_bleibt_unverschattet():
    """ΔB ist unabhängig von I_dif (F_sh,dif = 1, Anhang F.1 b))."""
    I_dir = 300.0
    _, B_a1, _ = _matrix(1.0, I_dir, 0.0)
    _, B_a2, _ = _matrix(0.5, I_dir, 0.0)
    _, B_b1, _ = _matrix(1.0, I_dir, 250.0)
    _, B_b2, _ = _matrix(0.5, I_dir, 250.0)

    delta_ohne_dif = B_a1[0] - B_a2[0]
    delta_mit_dif = B_b1[0] - B_b2[0]
    assert delta_mit_dif == pytest.approx(delta_ohne_dif, rel=1e-12)


def test_f_sh_eins_entspricht_gesamtstrahlung():
    """F_sh = 1: Split-Formel == alte Gesamtformel (BESTEST-Neutralität)."""
    I_dir, I_dif = 300.0, 100.0
    zone = _mini_zone(1.0)
    optionen = SimulationsOptionen(klimadatei="test")
    I_ges_dict = {"S": I_dir + I_dif}
    # Mit Kanaltrennung
    _, B_split, _ = baue_zonenmatrix(
        zone, theta_e=10.0, I_sol_dict=I_ges_dict,
        randbedingungen={}, nachbar_temps={},
        optionen=optionen, nutzung=_nutzung(),
        stunde_tag=12, stunde_jahr=12,
        I_sol_dir_dict={"S": I_dir}, I_sol_dif_dict={"S": I_dif},
    )
    # Fallback ohne Kanaltrennung
    zone2 = _mini_zone(1.0)
    _, B_fallback, _ = baue_zonenmatrix(
        zone2, theta_e=10.0, I_sol_dict=I_ges_dict,
        randbedingungen={}, nachbar_temps={},
        optionen=optionen, nutzung=_nutzung(),
        stunde_tag=12, stunde_jahr=12,
    )
    assert np.allclose(B_split, B_fallback)

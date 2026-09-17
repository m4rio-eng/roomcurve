#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests der 13370-Ableitung. Alle Soll-Werte sind unabhängige
Handrechnungen der zweifach verifizierten Formeln (B' Gl. 2, d_f
Gl. 3, U Gl. 4/5, R_vi F.1, δ H.1 gegen Tab. H.1, H_pi H.2,
H_pe H.3, θ_vi C.4+F.2).
"""

import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from iso52016.erdreich import (BODEN_KATEGORIEN, ErdreichParameter,
                               berechne_erdreich_parameter,
                               berechne_theta_vi_monate,
                               periodische_eindringtiefe,
                               theta_vi_fallback_sinus)

# Referenzgeometrie: 10 m × 10 m Platte, R_f = 2,0, Wand 0,3 m,
# R_si = 0,17, R_se = 0,04, Kategorie 2 (λ = 2,0, ρc = 2,0e6)
REF = dict(flaeche_m2=100.0, perimeter_m=40.0, R_f_m2K_W=2.0,
           wanddicke_m=0.3, R_si_m2K_W=0.17, R_se_m2K_W=0.04)


def test_charakteristisches_mass_und_wirksame_dicke():
    p = berechne_erdreich_parameter(**REF)
    # B' = 100/(0,5·40) = 5,0 (Gl. 2); Anm.: quadratische Platte →
    # halbe Seitenlänge
    assert p.B_strich_m == pytest.approx(5.0)
    # d_f = 0,3 + 2,0·(0,17+2,0+0,04) = 4,72 (Gl. 3)
    assert p.d_f_m == pytest.approx(4.72)


def test_u_wert_gl4_ungedaemmt_leicht():
    p = berechne_erdreich_parameter(**REF)
    # d_f = 4,72 < B' = 5,0 → Gl. (4):
    # U = 2·2,0/(π·5+4,72)·ln(π·5/4,72+1) = 4/20,42796·ln(4,32800)
    #   = 0,1958107·1,4651437 = 0,2868805
    assert p.U_W_m2K == pytest.approx(0.286880, rel=1e-4)


def test_u_wert_gl5_gut_gedaemmt():
    gut = dict(REF, R_f_m2K_W=5.0)  # d_f = 0,3+2·5,21 = 10,72 ≥ 5,0
    p = berechne_erdreich_parameter(**gut)
    # Gl. (5): U = 2,0/(0,457·5 + 10,72) = 2,0/13,005 = 0,15379
    assert p.U_W_m2K == pytest.approx(0.15379, rel=1e-4)


def test_r_vi_f1_und_kapazitaeten():
    p = berechne_erdreich_parameter(**REF)
    # R_g = 0,5/2,0 = 0,25; κ_gr = 0,5·2,0e6 = 1,0e6
    assert p.R_g_m2K_W == pytest.approx(0.25)
    assert p.kappa_gr_J_m2K == pytest.approx(1.0e6)
    # F.1: R_vi = 1/0,28691 − 0,17 − 2,0 − 0,25 = 3,48541 − 2,42
    assert p.R_vi_m2K_W == pytest.approx(1.0654, rel=1e-3)
    # Lesart A: Kette R_si + R_f + R_g + R_vi = 1/U (jahresmittel-treu)
    summe = REF["R_si_m2K_W"] + REF["R_f_m2K_W"] + p.R_g_m2K_W + p.R_vi_m2K_W
    assert summe == pytest.approx(1.0 / p.U_W_m2K, rel=1e-12)


def test_eindringtiefe_h1_gegen_tabelle_h1():
    # Tab. H.1: Kat. 1 → 2,2 m; Kat. 2 → 3,2 m; Kat. 3 → 4,2 m
    for kat, soll in ((1, 2.2), (2, 3.2), (3, 4.2)):
        lam, rc = BODEN_KATEGORIEN[kat]
        assert periodische_eindringtiefe(lam, rc) == pytest.approx(
            soll, abs=0.06)


def test_h_pi_h2_handrechnung():
    p = berechne_erdreich_parameter(**REF)
    # δ(Kat 2) = √(3,15e7·2/(π·2e6)) = √10,02676 = 3,1665062
    # H_pi = 100·(2/4,72)·√(2/((1+3,1665062/4,72)²+1))
    #      = 42,37288·√(2/(1,6708702²+1)) = 42,37288·√(2/3,7918074)
    #      = 42,37288·0,7262600 = 30,77371
    assert p.delta_m == pytest.approx(3.166506, rel=1e-5)
    assert p.H_pi_W_K == pytest.approx(30.7737, rel=1e-4)


def test_h_pe_h3_handrechnung():
    p = berechne_erdreich_parameter(**REF)
    # H_pe = 0,37·40·2,0·ln(3,1665062/4,72+1) = 29,6·ln(1,6708702)
    #      = 29,6·0,5133448 = 15,19500
    assert p.H_pe_W_K == pytest.approx(15.19499, rel=1e-4)


def test_theta_vi_konstante_temperaturen():
    """Bei θ_int,m = const und θ_e,m = const kollabiert C.4+F.2 auf
    θ_vi = θ_int − (θ_int − θ_e) = θ_e — die virtuelle Temperatur
    entspricht dann exakt der Außentemperatur (stationärer Grenzfall,
    Ψ_wf = 0)."""
    p = berechne_erdreich_parameter(**REF)
    tv = berechne_theta_vi_monate(p, REF["flaeche_m2"],
                                  REF["perimeter_m"],
                                  [8.0] * 12, [20.0] * 12)
    assert all(v == pytest.approx(8.0, abs=1e-9) for v in tv)


def test_theta_vi_daempft_und_verzoegert():
    """Mit Jahresgang der Außentemperatur (Innen konstant) muss die
    virtuelle Temperatur (1) im Jahresmittel dem Außenmittel gleichen
    (F.1-Konstruktion) und (2) eine kleinere Amplitude haben als die
    Außentemperatur (Erdreichträgheit über H_pe < U·A wirkt
    dämpfend)."""
    p = berechne_erdreich_parameter(**REF)
    te = [10.0 - 8.0 * math.cos(2 * math.pi * m / 12) for m in range(12)]
    tv = berechne_theta_vi_monate(p, REF["flaeche_m2"],
                                  REF["perimeter_m"], te, [20.0] * 12)
    assert sum(tv) / 12 == pytest.approx(sum(te) / 12, abs=1e-9)
    amp_te = (max(te) - min(te)) / 2
    amp_tv = (max(tv) - min(tv)) / 2
    assert amp_tv < amp_te
    # Handpin Januar (m=0): Φ_0 = UA·10 + H_pe·(10−2) = 286,91+121,61
    #   (H_pe·(θ̄e−θe,m) mit θe,0 = 2, θ̄e = 10)
    # θ_vi,0 = 20 − 408,52/286,91 = 18,5761... prüfe konsistent:
    UA = p.U_W_m2K * 100.0
    phi0 = UA * 10.0 + p.H_pe_W_K * (10.0 - te[0])
    assert tv[0] == pytest.approx(20.0 - phi0 / UA, rel=1e-12)


def test_eingabefehler_werden_laut():
    with pytest.raises(ValueError, match="Kategorie|kategorie"):
        berechne_erdreich_parameter(**dict(REF, boden_kategorie=7))
    with pytest.raises(ValueError, match="> 0"):
        berechne_erdreich_parameter(**dict(REF, perimeter_m=0.0))


def test_fallback_sinus_monatsmittel():
    """Fallback (nur mit Log-Hinweis nutzbar): Monatsmittel des
    Bestands-Sinus; Jahresmittel = Mitteltemperatur."""
    tv = theta_vi_fallback_sinus(9.0, 3.0, 1.0)
    assert len(tv) == 12
    assert sum(tv) / 12 == pytest.approx(9.0, abs=0.01)
    assert max(tv) <= 12.0 + 1e-9 and min(tv) >= 6.0 - 1e-9


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))


# ---------------------------------------------------------------
# Verdrahtungstests (Gl. 48–50 im Bauteil, Fangfälle, Schalter)
# ---------------------------------------------------------------

def _erd_bauteil(**kw):
    from iso52016.simulation import Bauteil
    basis = dict(id="boden", name="Boden", typ="opak", flaeche_m2=100.0,
                 azimut_deg=0, neigung_deg=0, zone_innen="Z1",
                 zone_aussen="ERD", R_c_m2K_W=2.0, kappa_m_kJ_m2K=100.0,
                 massenklasse="D")
    basis.update(kw)
    return Bauteil(**basis)


def test_k11_gl48_leitwerte_und_gl50_kapazitaeten():
    """Gl. 48 (Lesart A): h_pl = [2/R_gr, 1/(R_c/4+R_gr/2), 2/R_c,
    4/R_c] von außen (pl1) nach innen (pl5); Gl. 50d (Klasse D):
    κ = [0, κ_gr, κ_m/4, κ_m/2, κ_m/4]."""
    bt = _erd_bauteil()
    bt.konfiguriere_erdreich_knotenmodell(
        R_gr_m2K_W=0.25, kappa_gr_J_m2K=1.0e6, R_vi_m2K_W=1.0654)
    assert bt.h_pl[0] == pytest.approx(2.0 / 0.25)          # 8,0
    assert bt.h_pl[1] == pytest.approx(1.0 / (0.5 + 0.125))  # 1,6
    assert bt.h_pl[2] == pytest.approx(1.0)                  # 2/2,0
    assert bt.h_pl[3] == pytest.approx(2.0)                  # 4/2,0
    km_wh = 100.0 * 1000 / 3600
    assert bt.kappa_pl[0] == pytest.approx(0.0)              # virtuell
    assert bt.kappa_pl[1] == pytest.approx(1.0e6 / 3600)     # κ_gr
    assert bt.kappa_pl[2] == pytest.approx(km_wh / 4)
    assert bt.kappa_pl[3] == pytest.approx(km_wh / 2)
    assert bt.kappa_pl[4] == pytest.approx(km_wh / 4)
    # Gl. 49: h_ce = 1/R_vi, h_re = 0 → Φ_sky entfällt automatisch
    assert bt.h_ce == pytest.approx(1.0 / 1.0654)
    assert bt.h_re == 0.0


def test_k11_gl50_klasse_i():
    bt = _erd_bauteil(massenklasse="I")
    bt.konfiguriere_erdreich_knotenmodell(0.25, 1.0e6, 1.0)
    km_wh = 100.0 * 1000 / 3600
    assert bt.kappa_pl == pytest.approx(
        [0.0, 1.0e6 / 3600, 0.0, 0.0, km_wh])


def _gebaeude_mit_erd(tmp_path, erdreich=None, heizen=None, nutz_extra=None):
    import json
    from iso52016 import lade_gebaeude
    bt = {"id": "boden", "typ": "opak", "flaeche_m2": 100.0,
          "azimut_deg": 0, "neigung_deg": 0, "zone_innen": "Z1",
          "zone_aussen": "ERD", "R_c_m2K_W": 2.0,
          "kappa_m_kJ_m2K": 100.0}
    if erdreich is not None:
        bt["erdreich"] = erdreich
    geb = {"name": "t",
           "zonen": [{"id": "Z1", "name": "Z", "volumen_m3": 300.0,
                      "nutzflaeche_m2": 100.0, "nutzungsprofil": "p"}],
           "bauteile": [
               bt,
               {"id": "wand", "typ": "opak", "flaeche_m2": 120.0,
                "azimut_deg": 0, "neigung_deg": 90, "zone_innen": "Z1",
                "zone_aussen": "AUL", "R_c_m2K_W": 3.0,
                "kappa_m_kJ_m2K": 80.0}],
           "randbedingungen": {"ERD": {"typ": "erdreich",
                                       "temperatur_C": 9.0,
                                       "amplitude_K": 3.0}}}
    prof = {"beschreibung": "t", "interne_gewinne_W": [0.0] * 24,
            "luftwechsel_1_h": 0.5}
    if heizen is not None:
        prof["solltemperaturen"] = {"heizen_C": heizen}
    if nutz_extra:
        prof.update(nutz_extra)
    nutz = {"profile": {"p": prof}}
    gp, npf = tmp_path / "g.json", tmp_path / "n.json"
    gp.write_text(json.dumps(geb))
    npf.write_text(json.dumps(nutz))
    return lade_gebaeude(str(gp), str(npf))


class _MiniKlima:
    def __init__(self):
        self.n_stunden = 8760
        self.theta_e = [10.0 - 8.0 * math.cos(2 * math.pi * h / 8760)
                        for h in range(8760)]


def test_k11_vorbereitung_volle_kette(tmp_path):
    """Mit vollem erdreich-Block: 13370-Kette, keine Warnung,
    θ_gr;vi;m gesetzt, Element umverdrahtet."""
    import warnings as w
    from iso52016.simulation import (SimulationsOptionen,
                                     bereite_erdreich_vor)
    geb = _gebaeude_mit_erd(
        tmp_path,
        erdreich={"perimeter_m": 40.0, "wanddicke_m": 0.3},
        heizen=[20.0] * 24)
    opt = SimulationsOptionen(klimadatei="x")
    with w.catch_warnings(record=True) as rec:
        w.simplefilter("always")
        bereite_erdreich_vor(geb, _MiniKlima(), opt)
    assert not [r for r in rec if "Erdreich-Bauteil" in str(r.message)]
    bt = geb.zonen["Z1"].bauteile[0]
    assert bt.theta_gr_vi_monat is not None
    assert len(bt.theta_gr_vi_monat) == 12
    assert bt.h_re == 0.0 and bt.h_ce > 0.0
    # Jahresmittel der virtuellen Temperatur ≈ Außenmittel (F.1-treu)
    assert sum(bt.theta_gr_vi_monat) / 12 == pytest.approx(10.0, abs=0.05)
    # Wand (AUL) bleibt unangetastet
    wand = geb.zonen["Z1"].bauteile[1]
    assert wand.theta_gr_vi_monat is None and wand.h_re > 0.0


def test_k11_freilauf_fangfall(tmp_path):
    """Freilauf-Fangfall: Platzhalter (−999) im Heiz-Sollprofil darf
    nicht als Solltemperatur ins Erdreich-Jahresmittel laufen →
    Fallback 20 °C MIT Log-Hinweis; mit theta_int_mittel_C kein
    Hinweis."""
    import warnings as w
    from iso52016.simulation import (SimulationsOptionen,
                                     bereite_erdreich_vor)
    geb = _gebaeude_mit_erd(
        tmp_path,
        erdreich={"perimeter_m": 40.0, "wanddicke_m": 0.3},
        heizen=[-999.0] * 24)
    with w.catch_warnings(record=True) as rec:
        w.simplefilter("always")
        bereite_erdreich_vor(geb, _MiniKlima(),
                             SimulationsOptionen(klimadatei="x"))
    assert any("Freilauf" in str(r.message) and "20" in str(r.message)
               for r in rec)
    geb2 = _gebaeude_mit_erd(
        tmp_path,
        erdreich={"perimeter_m": 40.0, "wanddicke_m": 0.3,
                  "theta_int_mittel_C": 18.0},
        heizen=[-999.0] * 24)
    with w.catch_warnings(record=True) as rec2:
        w.simplefilter("always")
        bereite_erdreich_vor(geb2, _MiniKlima(),
                             SimulationsOptionen(klimadatei="x"))
    assert not [r for r in rec2 if "Freilauf" in str(r.message)]


def test_k11_fallback_ohne_bodenkennwerte(tmp_path):
    """Ohne erdreich-Block: Näherungs-Fallback (Kat.-2, R_vi=R_gr,
    θ aus Bestands-Sinus) mit BEIDEN Log-Hinweisen."""
    import warnings as w
    from iso52016.simulation import (SimulationsOptionen,
                                     bereite_erdreich_vor)
    geb = _gebaeude_mit_erd(tmp_path, erdreich=None, heizen=[20.0] * 24)
    with w.catch_warnings(record=True) as rec:
        w.simplefilter("always")
        bereite_erdreich_vor(geb, _MiniKlima(),
                             SimulationsOptionen(klimadatei="x"))
    meldungen = [str(r.message) for r in rec]
    assert any("Fallback" in m and "R_gr;vi" in m for m in meldungen)
    assert any("Sinus" in m for m in meldungen)
    bt = geb.zonen["Z1"].bauteile[0]
    assert bt.h_ce == pytest.approx(1.0 / 0.25)
    assert sum(bt.theta_gr_vi_monat) / 12 == pytest.approx(9.0, abs=0.01)


def test_k11_perimeter_ohne_wanddicke_wird_laut(tmp_path):
    from iso52016.simulation import (SimulationsOptionen,
                                     bereite_erdreich_vor)
    geb = _gebaeude_mit_erd(tmp_path, erdreich={"perimeter_m": 40.0},
                            heizen=[20.0] * 24)
    with pytest.raises(ValueError, match="wanddicke_m"):
        bereite_erdreich_vor(geb, _MiniKlima(),
                             SimulationsOptionen(klimadatei="x"))


def test_k11_altmodell_schalter(tmp_path):
    """erdreich_modell='sinus_direkt': keine Umverdrahtung, Altpfad."""
    from iso52016.simulation import (SimulationsOptionen,
                                     bereite_erdreich_vor)
    geb = _gebaeude_mit_erd(tmp_path, erdreich=None, heizen=[20.0] * 24)
    opt = SimulationsOptionen(klimadatei="x", erdreich_modell="sinus_direkt")
    bereite_erdreich_vor(geb, _MiniKlima(), opt)
    bt = geb.zonen["Z1"].bauteile[0]
    assert bt.theta_gr_vi_monat is None
    assert bt.h_re > 0.0


# ---------------------------------------------------------------
# Nachbarzone = interne Trennwand nach Gl. (42)
# ---------------------------------------------------------------

def _zone_mit_trennwand(zone_aussen, rb_typ, tmp_path, unter):
    import json
    from iso52016 import lade_gebaeude
    geb = {"name": "t",
           "zonen": [{"id": "Z1", "name": "Z", "volumen_m3": 150.0,
                      "nutzflaeche_m2": 50.0, "nutzungsprofil": "p"}],
           "bauteile": [
               {"id": "aussen", "typ": "opak", "flaeche_m2": 40.0,
                "azimut_deg": 180, "neigung_deg": 90, "zone_innen": "Z1",
                "zone_aussen": "AUL", "R_c_m2K_W": 2.0,
                "kappa_m_kJ_m2K": 60.0},
               {"id": "trenn", "typ": "opak", "flaeche_m2": 25.0,
                "azimut_deg": 0, "neigung_deg": 90, "zone_innen": "Z1",
                "zone_aussen": zone_aussen, "R_c_m2K_W": 1.5,
                "kappa_m_kJ_m2K": 40.0}],
           "randbedingungen": {zone_aussen: {"typ": rb_typ,
                                             "zone_id": "Z_NACHBAR"}}
           if rb_typ else {}}
    nutz = {"profile": {"p": {"beschreibung": "t",
                              "interne_gewinne_W": [100.0] * 24,
                              "luftwechsel_1_h": 0.5}}}
    gp, npf = tmp_path / f"g_{unter}.json", tmp_path / f"n_{unter}.json"
    gp.write_text(json.dumps(geb))
    npf.write_text(json.dumps(nutz))
    return lade_gebaeude(str(gp), str(npf))


def test_k12_nachbarzone_verhaelt_sich_wie_adiabat(tmp_path):
    """Ohne Anhang-D-Kopplung wird ein
    nachbarzone-Element nach 6.5.6.3.7 als interne Trennwand mit
    Gl. (42) behandelt — identisches Verhalten zu ADIABAT, keine
    fiktiven Solar-/Himmelsterme, keine Kopplung an eine
    Nachbartemperatur."""
    import numpy as np
    from iso52016.simulation import (SimulationsOptionen,
                                     fuenf_stufen_verfahren)
    erg = {}
    for kennung, (za, typ) in {
            "adiabat": ("ADIABAT", "adiabatisch"),
            "nachbar": ("NB", "nachbarzone")}.items():
        geb = _zone_mit_trennwand(za, typ, tmp_path, kennung)
        zone = geb.zonen["Z1"]
        zone.berechne_A_tot()
        profil = geb.nutzungsprofile["p"]
        opt = SimulationsOptionen(klimadatei="x")
        reihe = []
        theta_vorher = 20.0
        for h in range(48):
            res = fuenf_stufen_verfahren(
                zone=zone, theta_e=5.0, I_sol_dict={},
                randbedingungen=geb.randbedingungen,
                nachbar_temps={"Z_NACHBAR": 35.0},
                optionen=opt, nutzung=profil,
                stunde_tag=h % 24, stunde_jahr=h,
                theta_i_vorher=theta_vorher)
            theta_vorher = res[1]
            reihe.append(res[1])  # theta_air
        erg[kennung] = np.array(reihe)
    # Identisch trotz heißer (fiktiver) Nachbartemperatur 35 °C:
    assert np.allclose(erg["adiabat"], erg["nachbar"], atol=1e-12)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))

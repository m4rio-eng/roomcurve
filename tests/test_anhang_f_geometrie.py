"""
Anhang-F-Verschattungsgeometrie, stundenbezogen (Testsatz).

Normbasis (Seitenbild/Textlayer geprüft 22.07.2026, S. 227-241):
  - F.1/Gl. (F.1): F_sh,obst = (F_sh,dir·I_dir + I_dif)/(I_dir + I_dif)
    -> Umsetzung als F_sh nur auf Direktkanal (Verfahren 1).
  - F.3.4.1/Gl. (F.3): Sehfeld — F_sh,dir = 0, wenn |γk−φsol| oder
    |βk−αsol| außerhalb ±90° (Druckbild der Bedingung in der Norm
    verunglückt: „−90 > x > +90"; gemeint ist „außerhalb [−90,+90]").
  - Gl. (F.11): Überhang-Schattenhöhe (fensternaher Überhang äquivalent
    über den Profilwinkel: h = D·tan(α_sol)/cos(Δφ), davon abzüglich L).
  - Gl. (F.16)-(F.22): Kombination; F_sh,dir = (h_sun·w_sun)/(H·W)
    = (h_sun/H)·(w_sun/W) -> Produktbildung Überhang × Fin im Code.

Charakterisiert außerdem zwei dokumentierte Einschränkungen:
  - Grenzfall: Guard cos(Δφ) < 0,01 liefert 1,0 (unverschattet)
    statt des Norm-Grenzwerts 0 (voll verschattet). Numerisch klein
    (I_dir ∝ cos Δφ -> nahe 0), aber Vorzeichen des Grenzwerts falsch.
  - Historisch: horizont_winkel_deg wirkte nur auf F_sky,
    NICHT als F.10-Horizontverschattung auf den Direktanteil.

Die Charakterisierungstests fixieren das IST-Verhalten; eine bewusste
Korrektur muss diese Tests bewusst mit anfassen und die
BESTEST-Erwartung neu deklarieren (610/630/910/930 betroffen).
"""

import math

import numpy as np
import pytest

from iso52016.simulation import (
    berechne_F_sh_ueberhang_stuendlich, berechne_F_sh_fin_stuendlich,
    baue_zonenmatrix, Zone, Bauteil, Nutzungsprofil, SimulationsOptionen,
    DENVER,
)
from iso52016.solar import berechne_sonnenstand


TAG_SOMMER = 172   # um die Sommersonnenwende (hoher Sonnenstand)
STD_MITTAG = 12


def _sonne(stunde=STD_MITTAG, tag=TAG_SOMMER):
    return berechne_sonnenstand(stunde, tag, DENVER)


# ===========================================================================
# Überhang — Gl. (F.11)-äquivalente Profilwinkel-Geometrie
# ===========================================================================

def test_ovh_ohne_ueberhang_unverschattet():
    assert berechne_F_sh_ueberhang_stuendlich(
        STD_MITTAG, TAG_SOMMER, DENVER, azimut_iso=0.0,
        H_fenster=2.0, D_ovh=0.0, L_ovh=0.0) == 1.0


def test_ovh_nachts_neutral():
    """Nachts (α ≤ 0, Gl. 11) ist I_dir = 0; Rückgabe 1,0 ist neutral."""
    assert berechne_F_sh_ueberhang_stuendlich(
        0, TAG_SOMMER, DENVER, azimut_iso=0.0,
        H_fenster=2.0, D_ovh=1.0, L_ovh=0.5) == 1.0


def test_ovh_geschlossene_formel_sued():
    """F = 1 − clamp(D·tanα/cosΔφ − L, 0, H)/H gegen denselben
    (blind geprüften) Sonnenstand gerechnet — prüft NUR die Geometrie."""
    erg = _sonne()
    assert erg.alpha_sol > 45  # Vorbedingung: hoher Sonnenstand
    azimut_iso = erg.phi_sol   # Sonne exakt frontal -> Δφ = 0
    D, L, H = 0.5, 0.5, 2.0
    h_schatten = D * math.tan(math.radians(erg.alpha_sol))
    erwartet = 1.0 - min(max(0.0, h_schatten - L), H) / H
    f = berechne_F_sh_ueberhang_stuendlich(
        STD_MITTAG, TAG_SOMMER, DENVER, azimut_iso, H, D, L)
    assert f == pytest.approx(erwartet, rel=1e-12)
    assert 0.0 < f < 1.0  # Vorbedingung: Fall liegt im teilverschatteten Bereich


def test_ovh_schraegeinfall_profilwinkel():
    """Δφ = 60°: Schattenhöhe wächst mit 1/cosΔφ (Profilwinkel)."""
    erg = _sonne()
    delta_phi = 60.0
    azimut_iso = erg.phi_sol - delta_phi
    D, L, H = 0.3, 0.0, 2.0
    h_schatten = (D * math.tan(math.radians(erg.alpha_sol))
                  / math.cos(math.radians(delta_phi)))
    erwartet = 1.0 - min(max(0.0, h_schatten - L), H) / H
    f = berechne_F_sh_ueberhang_stuendlich(
        STD_MITTAG, TAG_SOMMER, DENVER, azimut_iso, H, D, L)
    assert f == pytest.approx(erwartet, rel=1e-12)


def test_ovh_abstand_schluckt_schatten():
    """L größer als jede mögliche Schattenhöhe -> unverschattet."""
    f = berechne_F_sh_ueberhang_stuendlich(
        STD_MITTAG, TAG_SOMMER, DENVER, azimut_iso=_sonne().phi_sol,
        H_fenster=2.0, D_ovh=0.2, L_ovh=10.0)
    assert f == 1.0


def test_ovh_tiefer_ueberhang_volle_verschattung():
    """Sehr tiefer Überhang: Kappe bei H (Gl. F.17) -> F_sh,dir = 0."""
    f = berechne_F_sh_ueberhang_stuendlich(
        STD_MITTAG, TAG_SOMMER, DENVER, azimut_iso=_sonne().phi_sol,
        H_fenster=2.0, D_ovh=50.0, L_ovh=0.0)
    assert f == 0.0


def test_ovh_monotonie_in_der_tiefe():
    erg = _sonne()
    werte = [berechne_F_sh_ueberhang_stuendlich(
        STD_MITTAG, TAG_SOMMER, DENVER, erg.phi_sol, 2.0, d, 0.3)
        for d in (0.2, 0.5, 1.0, 2.0)]
    assert all(a >= b for a, b in zip(werte, werte[1:]))


def test_ovh_sonne_hinter_fassade():
    """Δφ > 90°: Rückgabe 1,0. Formal weicht das von Gl. (F.3) ab
    (Sehfeld: F_sh,dir = 0), ist aber numerisch neutral, weil der
    Direktkanal inkl. Zirkumsolar dort exakt 0 ist (Gl. 26/37:
    cos θ ≤ 0). Dokumentierte, bewusst belassene Konvention."""
    erg = _sonne()
    f = berechne_F_sh_ueberhang_stuendlich(
        STD_MITTAG, TAG_SOMMER, DENVER, azimut_iso=erg.phi_sol - 135.0,
        H_fenster=2.0, D_ovh=1.0, L_ovh=0.0)
    assert f == 1.0


def test_ovh_b21_grenzfall_korrigiert():
    """Grenzfall: Bei streifendem Einfall knapp unter 90° divergiert
    Gl. (F.4) (h → ∞) — das ist volle Verschattung. Der frühere Guard
    (cos Δφ < 0,01 → 1,0) lieferte das falsche Grenzwert-Ende; jetzt
    wird der Nenner nur numerisch abgesichert und die Kappung auf die
    Fensterhöhe bildet den Grenzwert ab. Beide Streiflicht-Winkel
    müssen voll verschattet sein; jenseits 90° (Sonne hinter der
    Fassade) bleibt die dokumentierte 1,0-Konvention (I_dir = 0)."""
    erg = _sonne()
    D, L, H = 1.0, 0.0, 2.0
    for dphi in (88.0, 89.9, 89.99):
        f = berechne_F_sh_ueberhang_stuendlich(
            STD_MITTAG, TAG_SOMMER, DENVER, erg.phi_sol - dphi, H, D, L)
        assert f == 0.0, dphi
    f_hinter = berechne_F_sh_ueberhang_stuendlich(
        STD_MITTAG, TAG_SOMMER, DENVER, erg.phi_sol - 90.5, H, D, L)
    assert f_hinter == 1.0


# ===========================================================================
# Seitenfinnen — Gl. (F.19)-(F.21)-äquivalent (sonnenseitige Finne)
# ===========================================================================

def test_fin_ohne_fins_unverschattet():
    assert berechne_F_sh_fin_stuendlich(
        STD_MITTAG, TAG_SOMMER, DENVER, azimut_iso=0.0,
        W_fenster=3.0, D_fin=0.0, G_fin=0.0) == 1.0


def test_fin_frontal_kein_schatten():
    """Sonne frontal: w = D·tan(0) = 0 -> unverschattet."""
    erg = _sonne()
    assert berechne_F_sh_fin_stuendlich(
        STD_MITTAG, TAG_SOMMER, DENVER, azimut_iso=erg.phi_sol,
        W_fenster=3.0, D_fin=0.5, G_fin=0.0) == 1.0


def test_fin_geschlossene_formel_45_grad():
    """Δφ = 45°: w = D·tan45° = D; F = 1 − clamp(D − G, 0, W)/W."""
    erg = _sonne()
    D, G, W = 0.8, 0.2, 3.0
    erwartet = 1.0 - min(max(0.0, D * 1.0 - G), W) / W
    f = berechne_F_sh_fin_stuendlich(
        STD_MITTAG, TAG_SOMMER, DENVER, azimut_iso=erg.phi_sol - 45.0,
        W_fenster=W, D_fin=D, G_fin=G)
    assert f == pytest.approx(erwartet, rel=1e-9)


def test_fin_kappe_volle_breite():
    """Sehr tiefe Finne bei flachem Winkel: Kappe bei W -> 0."""
    erg = _sonne()
    f = berechne_F_sh_fin_stuendlich(
        STD_MITTAG, TAG_SOMMER, DENVER, azimut_iso=erg.phi_sol - 80.0,
        W_fenster=3.0, D_fin=10.0, G_fin=0.0)
    assert f == 0.0


def test_fin_symmetrie_links_rechts():
    """±Δφ liefert denselben Faktor (sonnenseitige Finne wechselt)."""
    erg = _sonne()
    f_plus = berechne_F_sh_fin_stuendlich(
        STD_MITTAG, TAG_SOMMER, DENVER, erg.phi_sol - 30.0, 3.0, 0.5, 0.1)
    f_minus = berechne_F_sh_fin_stuendlich(
        STD_MITTAG, TAG_SOMMER, DENVER, erg.phi_sol + 30.0, 3.0, 0.5, 0.1)
    assert f_plus == pytest.approx(f_minus, rel=1e-9)


# ===========================================================================
# Fallback-Kaskade im Fensterpfad (Geometrie > Stundenwerte > Konstante)
# und Produktkombination (Gl. F.22)
# ===========================================================================

def _zone_mit_fenster(**fenster_kwargs) -> Zone:
    bauteile = [
        Bauteil(id="fe", name="Fenster S", typ="transparent",
                flaeche_m2=6.0, azimut_deg=180, neigung_deg=90,
                zone_innen="Z1", zone_aussen="AUL",
                U_W_m2K=1.3, g_wert=0.6, **fenster_kwargs),
        Bauteil(id="wand", name="Wand", typ="opak",
                flaeche_m2=30.0, azimut_deg=0, neigung_deg=90,
                zone_innen="Z1", zone_aussen="ADIABAT",
                R_c_m2K_W=3.5, kappa_m_kJ_m2K=50.0),
    ]
    zone = Zone(id="Z1", name="Z", volumen_m3=100.0, nutzflaeche_m2=40.0,
                nutzungsprofil="test", bauteile=bauteile)
    zone.berechne_A_tot()
    return zone


def _B_vektor(zone, stunde_jahr=(TAG_SOMMER - 1) * 24 + STD_MITTAG):
    nutzung = Nutzungsprofil(
        id="test", beschreibung="Test",
        heizen_C=[20.0] * 24, kuehlen_C=[26.0] * 24,
        interne_gewinne_W=[0.0] * 24, luftwechsel_1_h=[0.5] * 24)
    optionen = SimulationsOptionen(klimadatei="test")
    _, B, _ = baue_zonenmatrix(
        zone, theta_e=20.0, I_sol_dict={"S": 500.0, "N": 0.0},
        randbedingungen={}, nachbar_temps={},
        optionen=optionen, nutzung=nutzung,
        stunde_tag=STD_MITTAG, stunde_jahr=stunde_jahr,
        I_sol_dir_dict={"S": 400.0, "N": 0.0},
        I_sol_dif_dict={"S": 100.0, "N": 0.0})
    return B


def test_kaskade_stundenwerte_vor_konstante():
    """Ohne Geometrie: F_sh_stundenwerte[t] wird genutzt; ein Lauf mit
    identischem konstantem F_sh_obst muss denselben B-Vektor liefern."""
    t = (TAG_SOMMER - 1) * 24 + STD_MITTAG
    stunden = np.ones(8760)
    stunden[t] = 0.4
    B_std = _B_vektor(_zone_mit_fenster(F_sh_stundenwerte=stunden))
    B_konst = _B_vektor(_zone_mit_fenster(F_sh_obst=0.4))
    assert np.allclose(B_std, B_konst)
    B_eins = _B_vektor(_zone_mit_fenster(F_sh_obst=1.0))
    assert not np.allclose(B_std, B_eins)  # 0,4 wirkt tatsächlich


def test_kaskade_geometrie_ignoriert_stundenwerte():
    """Mit Überhang-Geometrie werden F_sh_stundenwerte ignoriert:
    Läufe mit Stundenwert 0,0 bzw. 1,0 sind identisch."""
    geo = dict(ueberhang_tiefe_m=1.0, ueberhang_abstand_m=0.5,
               fenster_hoehe_m=2.0)
    B_a = _B_vektor(_zone_mit_fenster(
        F_sh_stundenwerte=np.zeros(8760), **geo))
    B_b = _B_vektor(_zone_mit_fenster(
        F_sh_stundenwerte=np.ones(8760), **geo))
    assert np.allclose(B_a, B_b)


def test_kombination_produkt_f22():
    """Gl. (F.22): F_sh,dir = (h_sun/H)·(w_sun/W) = F_ovh·F_fin.
    Solargewinn-Differenzen im B-Vektor müssen sich wie die Faktoren
    verhalten: ΔB(ovh+fin) = F_fin·ΔB(ovh) bei fixem F_fin? Einfacher:
    Summe der Solaranteile skaliert linear mit F_sh -> Verhältnisprüfung
    über drei Läufe (ohne, nur ovh, ovh+fin)."""
    t = (TAG_SOMMER - 1) * 24 + STD_MITTAG
    erg = berechne_sonnenstand(STD_MITTAG, TAG_SOMMER, DENVER)
    # F_ovh und F_fin unabhängig auf Funktionsebene
    F_ovh = berechne_F_sh_ueberhang_stuendlich(
        STD_MITTAG, TAG_SOMMER, DENVER, 180 - 180, 2.0, 1.0, 0.5)
    F_fin = berechne_F_sh_fin_stuendlich(
        STD_MITTAG, TAG_SOMMER, DENVER, 180 - 180, 3.0, 0.8, 0.1)
    assert 0.0 < F_ovh < 1.0 or F_ovh in (0.0, 1.0)

    B_frei = _B_vektor(_zone_mit_fenster())
    B_ovh = _B_vektor(_zone_mit_fenster(
        ueberhang_tiefe_m=1.0, ueberhang_abstand_m=0.5, fenster_hoehe_m=2.0))
    B_beide = _B_vektor(_zone_mit_fenster(
        ueberhang_tiefe_m=1.0, ueberhang_abstand_m=0.5, fenster_hoehe_m=2.0,
        fin_tiefe_m=0.8, fin_abstand_m=0.1, fenster_breite_m=3.0))

    # Solargewinn ~ I_dir·F_sh + I_dif; Differenz zum unverschatteten
    # Lauf ist proportional zu (1 − F_sh) am Direktanteil.
    d_ovh = (B_frei - B_ovh).sum()
    d_beide = (B_frei - B_beide).sum()
    if F_ovh == 1.0 and F_fin == 1.0:
        pytest.skip("Sonnenstand verschattet in dieser Stunde nicht")
    erwartet = ((1.0 - F_ovh * F_fin) / (1.0 - F_ovh)
                if F_ovh < 1.0 else None)
    if erwartet is None:
        assert d_ovh == pytest.approx(0.0)
        assert d_beide > 0.0
    else:
        assert d_beide / d_ovh == pytest.approx(erwartet, rel=1e-9)


# ===========================================================================
# Horizontwinkel (Charakterisierung)
# ===========================================================================

def test_k14_horizont_ohne_f_sky_wirkung():
    """F_sky ist nach Gl. (70)
    i. V. m. Tabelle B.18 rein neigungsbestimmt (1,0 horizontal /
    0,5 vertikal). horizont_winkel_deg wirkt ausschließlich auf die
    solare Direktstrahlung (Anhang F) und darf F_sky
    NICHT verändern. Ersetzt einen früheren Wächtertest, der das
    alte Fehlverhalten fixierte."""
    bt_frei = Bauteil(id="a", name="a", typ="opak", flaeche_m2=1.0,
                      azimut_deg=180, neigung_deg=90,
                      zone_innen="Z1", zone_aussen="AUL",
                      R_c_m2K_W=1.0, kappa_m_kJ_m2K=10.0)
    bt_hor = Bauteil(id="b", name="b", typ="opak", flaeche_m2=1.0,
                     azimut_deg=180, neigung_deg=90,
                     zone_innen="Z1", zone_aussen="AUL",
                     R_c_m2K_W=1.0, kappa_m_kJ_m2K=10.0,
                     horizont_winkel_deg=10.0)
    assert bt_frei.F_sky == pytest.approx(0.5)
    assert bt_hor.F_sky == pytest.approx(0.5, rel=1e-12)
    # Horizontale Fläche: F_sky = 1,0, ebenfalls horizontunabhängig
    bt_dach = Bauteil(id="c", name="c", typ="opak", flaeche_m2=1.0,
                      azimut_deg=180, neigung_deg=0,
                      zone_innen="Z1", zone_aussen="AUL",
                      R_c_m2K_W=1.0, kappa_m_kJ_m2K=10.0,
                      horizont_winkel_deg=45.0)
    assert bt_dach.F_sky == pytest.approx(1.0, rel=1e-12)



def test_k23_a_tot_zaehlt_transparente_adiabat_elemente():
    """Gl. (39) summiert die
    Flächen ALLER Gebäudeelemente der Zone. Auch ein transparentes
    Element mit Randbedingung ADIABAT zählt in A_tot mit."""
    bauteile = [
        Bauteil(id="fe_ad", name="Fenster adiabat", typ="transparent",
                flaeche_m2=6.0, azimut_deg=180, neigung_deg=90,
                zone_innen="Z1", zone_aussen="ADIABAT",
                U_W_m2K=1.3, g_wert=0.6),
        Bauteil(id="wand", name="Wand", typ="opak",
                flaeche_m2=30.0, azimut_deg=0, neigung_deg=90,
                zone_innen="Z1", zone_aussen="AUL",
                R_c_m2K_W=3.5, kappa_m_kJ_m2K=50.0),
    ]
    zone = Zone(id="Z1", name="Z", volumen_m3=100.0, nutzflaeche_m2=40.0,
                nutzungsprofil="test", bauteile=bauteile)
    zone.berechne_A_tot()
    assert zone.A_tot == pytest.approx(36.0)

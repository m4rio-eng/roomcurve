# Copyright (c) 2026 Mario Vukadinovic
# SPDX-License-Identifier: AGPL-3.0-only
"""
Unit-Tests für die ISO-52010-1-Kette in solar.py nach den Fixes 15-21
Prüfwerte direkt aus dem Normtext
DIN EN ISO 52010-1:2018-03 abgeleitet.
"""
import math
import pytest

from iso52016.solar import (
    I_SC, K_PEREZ, PEREZ_KOEFFIZIENTEN,
    berechne_luftmasse, berechne_sonnenazimut, berechne_sonnenhoehe,
    berechne_einfallswinkel, berechne_klarheitsparameter,
    berechne_helligkeitsparameter, berechne_diffusstrahlung_geneigt,
    berechne_bodenreflexion, berechne_strahlung_geneigte_flaeche,
    waehle_perez_koeffizienten,
)


class TestFix15Luftmasse:
    """Gl. (20)/(21): Fallunterscheidung bei alpha = 10 Grad (P1)."""

    def test_gl20_oberhalb_10_grad(self):
        for a in (10.0, 15.0, 30.0, 45.0, 90.0):
            assert berechne_luftmasse(a) == pytest.approx(
                1.0 / math.sin(math.radians(a)), rel=1e-12)

    def test_gl21_unterhalb_10_grad(self):
        for a in (0.0, 2.0, 5.0, 9.999):
            soll = 1.0 / (math.sin(math.radians(a))
                          + 0.15 * (a + 3.885) ** (-1.253))
            assert berechne_luftmasse(a) == pytest.approx(soll, rel=1e-12)

    def test_sprungstelle_10_grad(self):
        """Die Norm-Fallunterscheidung erzeugt einen Sprung von ~+3 %
        beim Übergang Gl. (21) -> Gl. (20); genau der Bereich, in dem
        die alte Kasten-Young-Formel abwich."""
        m_unter = berechne_luftmasse(9.999999)
        m_ab = berechne_luftmasse(10.0)
        assert m_ab / m_unter == pytest.approx(1.031, abs=0.002)

    def test_bei_null_endlich_keine_kappung(self):
        m0 = berechne_luftmasse(0.0)
        assert 36.0 < m0 < 37.0  # ~36,5; kein Nachtwert 40, keine Kappung


class TestFix16DaemmerungOhneGate:
    """Kein Tag-Gate: Gl. (26)-(39) auch bei alpha = 0 auswertbar (P2)."""

    def test_bodenreflexion_bei_alpha_null(self):
        # Gl. (35): (G_d + G_b*sin 0) * rho * (1-cos beta)/2
        erg = berechne_bodenreflexion(100.0, 50.0, 0.0, 90.0, 0.2)
        assert erg == pytest.approx(50.0 * 0.2 * 0.5, rel=1e-12)

    def test_kette_bei_alpha_null_liefert_diffus(self):
        r = berechne_strahlung_geneigte_flaeche(
            G_sol_b=0.0, G_sol_d=20.0, alpha_sol_deg=0.0,
            gamma_sol_deg=90.0, beta_deg=90.0, gamma_surf_deg=0.0, n_day=1)
        assert r.I_dif_tot > 0.0  # vorher: hartes 0-Gate
        assert r.I_dir == 0.0

    def test_echte_nacht_alles_null(self):
        r = berechne_strahlung_geneigte_flaeche(
            G_sol_b=0.0, G_sol_d=0.0, alpha_sol_deg=0.0,
            gamma_sol_deg=120.0, beta_deg=90.0, gamma_surf_deg=0.0, n_day=180)
        assert r.I_tot == 0.0 and r.I_dif == 0.0 and r.I_ground == 0.0

    def test_einfallswinkel_bei_alpha_null_normexakt(self):
        # cos(theta) = cos(0)*sin(90)*cos(0) = 1 -> theta = 0 (nicht 90!)
        assert berechne_einfallswinkel(0.0, 0.0, 90.0, 0.0) == pytest.approx(0.0, abs=1e-9)
        # Gegenrichtung: theta > 90 wird jetzt normexakt zurückgegeben
        assert berechne_einfallswinkel(0.0, 180.0, 90.0, 0.0) == pytest.approx(180.0, abs=1e-9)


class TestFix17AzimutOhneGate:
    """Gl. (13)-(16) ohne Höhenbedingung (P4)."""

    def test_flache_sonne_azimut_nicht_sued(self):
        # Sommermorgen, Sonne 0,3 Grad über Horizont im NO — vorher hart 0 (Süd).
        # Stundenwinkel zur Zielhöhe direkt aus Gl. (11) gelöst (deterministisch).
        delta, phi_w, a_ziel = 23.0, 48.0, 0.3
        d, p = math.radians(delta), math.radians(phi_w)
        cos_omega = ((math.sin(math.radians(a_ziel)) - math.sin(d) * math.sin(p))
                     / (math.cos(d) * math.cos(p)))
        omega = -math.degrees(math.acos(cos_omega))  # Vormittag: omega < 0
        a = berechne_sonnenhoehe(delta, phi_w, omega)
        assert 0.0 < a <= 0.5
        az = berechne_sonnenazimut(delta, phi_w, omega, a)
        assert abs(az) > 90.0  # deutlich östlich von Süd


class TestFix18Solarkonstante:
    def test_tabelle_9(self):
        assert I_SC == 1370.0
        assert K_PEREZ == 1.014


class TestFix19Schwellen:
    """epsilon-Sonderfall exakt G_d = 0; keine 0,1-Schwellen (P5)."""

    def test_epsilon_999_nur_bei_exakt_null(self):
        assert berechne_klarheitsparameter(500.0, 0.0, 30.0) == 999.0
        eps = berechne_klarheitsparameter(500.0, 0.05, 30.0)
        assert eps != 999.0 and eps > 1.0

    def test_delta_ohne_schwelle(self):
        d = berechne_helligkeitsparameter(0.05, 30.0, 172)
        soll = berechne_luftmasse(30.0) * 0.05 / (I_SC * (1 + 0.033 * math.cos(math.radians(360 * 172 / 365))))
        assert d == pytest.approx(soll, rel=1e-12)

    def test_diffus_ohne_schwelle(self):
        I_dif, I_circ = berechne_diffusstrahlung_geneigt(
            G_sol_d=0.05, F1=0.3, F2=0.1, a=0.5, b=0.5, beta_deg=90.0)
        assert I_dif > 0.0 and I_circ > 0.0


class TestFix20KeineIdifKappung:
    def test_negativer_horizontterm_bleibt(self):
        # Konstruierter Fall: F1 = 1 (Isotropanteil 0), F2 < 0, steile Fläche
        I_dif, _ = berechne_diffusstrahlung_geneigt(
            G_sol_d=100.0, F1=1.0, F2=-0.5, a=0.0, b=0.5, beta_deg=90.0)
        assert I_dif == pytest.approx(-50.0, rel=1e-12)  # vorher auf 0 gekappt


class TestZ1PerezBins:
    def test_bin1_untergrenze_norm(self):
        assert PEREZ_KOEFFIZIENTEN[1][0] == 1.000

    def test_float_unterschreitung_faellt_auf_klasse_1(self):
        k1 = PEREZ_KOEFFIZIENTEN[1][2:8]
        assert waehle_perez_koeffizienten(0.999999999) == k1
        assert waehle_perez_koeffizienten(1.0) == k1

    def test_sonderwert_999_klasse_8(self):
        assert waehle_perez_koeffizienten(999.0) == PEREZ_KOEFFIZIENTEN[8][2:8]

    def test_grenzwerte(self):
        assert waehle_perez_koeffizienten(1.065) == PEREZ_KOEFFIZIENTEN[2][2:8]
        assert waehle_perez_koeffizienten(6.2) == PEREZ_KOEFFIZIENTEN[8][2:8]


class TestSummengroessen:
    """Gl. (37)-(39): Zerlegung bleibt algebraisch normidentisch (P8)."""

    def test_gl37_38_39(self):
        r = berechne_strahlung_geneigte_flaeche(
            G_sol_b=800.0, G_sol_d=150.0, alpha_sol_deg=35.0,
            gamma_sol_deg=-20.0, beta_deg=90.0, gamma_surf_deg=0.0, n_day=172)
        assert r.I_dir_tot == pytest.approx(r.I_dir + r.I_circum, rel=1e-12)
        assert r.I_dif_tot == pytest.approx(r.I_dif + r.I_ground, rel=1e-12)
        assert r.I_tot == pytest.approx(r.I_dir_tot + r.I_dif_tot, rel=1e-12)

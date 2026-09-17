# Copyright (c) 2026 Mario Vukadinovic
# SPDX-License-Identifier: AGPL-3.0-only
"""
Unit-Tests für die 52010-1-Anbindung in climate.py.
Prüft Norm-Invarianten der Kanalzuordnung Gl. (37)/(38), nicht Zahlenwerte
einzelner Klimadatensätze (dafür: verifizierungen/tab26_verifizierung.md).
"""
import math
import numpy as np
import pytest

from iso52016.climate import compute_surface_irradiance, compute_solar_position, Location
from iso52016.solar import I_SC


@pytest.fixture
def strahlungsstunden():
    """Kleines synthetisches Profil: 6 Stunden mit Sonne, gemischte Lagen."""
    DNI = np.array([0.0, 200.0, 600.0, 850.0, 400.0, 0.0])
    DHI = np.array([20.0, 80.0, 120.0, 90.0, 150.0, 0.0])
    alpha = np.array([0.0, 8.0, 25.0, 45.0, 15.0, 0.0])
    phi = np.array([110.0, 75.0, 40.0, 0.0, -60.0, -110.0])
    return DNI, DHI, alpha, phi


class TestKanalinvarianten:
    def test_vertikale_diffus_orientierungsunabhaengig(self, strahlungsstunden):
        """Tab.-26-Eigenschaft: I_dif;tot (Gl. 38) ist für alle Vertikalen
        identisch (Isotrop-, Horizont- und Bodenterm azimutunabhängig,
        Zirkumsolar ausgegliedert)."""
        DNI, DHI, alpha, phi = strahlungsstunden
        ref = None
        for az in (180.0, 90.0, 0.0, -90.0, 37.5):
            _, I_dif = compute_surface_irradiance(DNI, DHI, alpha, phi, az, 90.0)
            if ref is None:
                ref = I_dif
            else:
                assert np.allclose(I_dif, ref, rtol=0, atol=1e-9)

    def test_horizontal_summenidentitaet(self, strahlungsstunden):
        """Horizontal gilt exakt I_dir;tot + I_dif;tot = G_b*sin(alpha) + G_d
        (für alpha > 5°, d. h. a/b = 1)."""
        DNI, DHI, alpha, phi = strahlungsstunden
        I_dir, I_dif = compute_surface_irradiance(DNI, DHI, alpha, phi, 0.0, 0.0)
        for h in range(len(DNI)):
            if alpha[h] <= 5.0:
                continue
            soll = DNI[h] * math.sin(math.radians(alpha[h])) + DHI[h]
            assert I_dir[h] + I_dif[h] == pytest.approx(soll, rel=1e-9)

    def test_daemmerungsstunde_nicht_verworfen(self, strahlungsstunden):
        """Fix-16-Verhalten am Anschluss: alpha = 0 mit G_d > 0 liefert
        Diffus- und Bodenanteil (vorher hartes 0-Gate im Isotropmodell)."""
        DNI, DHI, alpha, phi = strahlungsstunden
        _, I_dif = compute_surface_irradiance(DNI, DHI, alpha, phi, 0.0, 90.0)
        assert I_dif[0] > 0.0  # Stunde 0: alpha=0, DHI=20

    def test_zirkumsolar_im_direktkanal(self, strahlungsstunden):
        """Direktkanal = Gl. (37): Bei DNI = 0, aber DHI > 0 und Sonne
        über Horizont muss I_dir des zugewandten Vertikals > 0 sein
        (reiner Zirkumsolaranteil)."""
        DNI = np.array([0.0]); DHI = np.array([300.0])
        alpha = np.array([30.0]); phi = np.array([0.0])
        I_dir, _ = compute_surface_irradiance(DNI, DHI, alpha, phi, 0.0, 90.0)
        assert I_dir[0] > 0.0

    def test_bodenreflexion_wirkt(self):
        """rho = 0,2 hebt die Vertikale gegenüber rho = 0 messbar an."""
        DNI = np.array([800.0]); DHI = np.array([100.0])
        alpha = np.array([40.0]); phi = np.array([0.0])
        _, dif_mit = compute_surface_irradiance(DNI, DHI, alpha, phi, 0.0, 90.0, rho_ground=0.2)
        _, dif_ohne = compute_surface_irradiance(DNI, DHI, alpha, phi, 0.0, 90.0, rho_ground=0.0)
        G_hor = 800.0 * math.sin(math.radians(40.0)) + 100.0
        assert dif_mit[0] - dif_ohne[0] == pytest.approx(G_hor * 0.2 * 0.5, rel=1e-9)


class TestSonnenstandWrapper:
    def test_wrapper_konsistent_zu_solar(self):
        """compute_solar_position ist dünner Wrapper über berechne_sonnenstand."""
        from iso52016.solar import berechne_sonnenstand, Standort
        loc = Location(name="Stapleton", latitude=39.76, longitude=-104.86,
                       timezone=-7.0, elevation=1609.0)
        st = Standort("Stapleton", 39.76, -104.86, -7.0, 1609.0)
        for stunde, tag in ((11, 172), (7, 37), (17, 300)):
            a, p = compute_solar_position(stunde, tag, loc)
            e = berechne_sonnenstand(stunde, tag, st)
            assert a == e.alpha_sol and p == e.phi_sol

    def test_solarkonstante_einheitlich(self):
        """Keine lokale 1367-Doublette mehr in climate.py."""
        import iso52016.climate as c
        assert c.I_SC == 1370.0 == I_SC

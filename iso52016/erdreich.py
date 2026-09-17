#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Erdreich-Parameterableitung nach DIN EN ISO 13370:2018-03 für das
Knotenmodell der DIN EN ISO 52016-1 (Gl. 48–50). Alle verwendeten
Formeln wurden am 27.07.2026 im Zwei-Quellen-Verfahren (Textlayer +
OCR des Seitenbilds) verifiziert; das Wurzelzeichen in Gl. (H.2)
zusätzlich pixelforensisch (Belegkette im Modul- und Testcode
dokumentiert).

Lesart A (Anmerkung M4 im Normtext-Register, dort begründet): In der
Gl.-48-Knotenkette steht die REINE Konstruktion R_f; R_gr = 0,5/λ_g;
R_gr;vi nach Gl. (F.1). Gesamtwiderstand = 1/U (jahresmittel-treu).

Umfang: Bodenplatte auf Erdreich ohne Randdämmung (§7.1). Keller
(§7.3/7.4), aufgeständerte Platten (§7.2) und Randdämmung (Anhang D)
sind NICHT implementiert.
"""

import math
from dataclasses import dataclass, field
from typing import List, Optional, Sequence

# Tabelle 7 — wärmetechnische Eigenschaften des Erdreichs
# Kategorie: (λ_g in W/(m·K), ρc in J/(m³·K))
BODEN_KATEGORIEN = {
    1: (1.5, 3.0e6),   # Ton oder Schluff
    2: (2.0, 2.0e6),   # Sand oder Kies (Default bei unbekanntem Boden)
    3: (3.5, 2.0e6),   # homogener Felsen
}
BODEN_KATEGORIE_DEFAULT = 2  # 6.4.1: "Wenn die Art des Erdreichs
                             # unbekannt ist, sollte Kategorie 2
                             # verwendet werden."

SEKUNDEN_JAHR = 3.15e7       # H.1 Anmerkung


@dataclass
class ErdreichParameter:
    """Abgeleitete 13370-Größen für ein Bodenplatten-Element."""
    B_strich_m: float          # charakteristisches Maß, Gl. (2)
    d_f_m: float               # wirksame Gesamtdicke, Gl. (3)
    U_W_m2K: float             # U_fg;sog, Gl. (4)/(5)
    R_g_m2K_W: float           # 0,5-m-Erdreichschicht, F.1
    kappa_gr_J_m2K: float      # κ_gr = 0,5 m · ρc
    R_vi_m2K_W: float          # virtuelle Schicht, Gl. (F.1)
    delta_m: float             # periodische Eindringtiefe, Gl. (H.1)
    H_pi_W_K: float            # Gl. (H.2)
    H_pe_W_K: float            # Gl. (H.3)
    lambda_g: float
    rho_c_g: float
    quelle: str = "iso13370"   # "iso13370" oder "fallback_naeherung"
    hinweise: List[str] = field(default_factory=list)


def periodische_eindringtiefe(lambda_g: float, rho_c_g: float) -> float:
    """Gl. (H.1): δ = √(3,15·10⁷·λ_g / (π·ρ·c))."""
    return math.sqrt(SEKUNDEN_JAHR * lambda_g / (math.pi * rho_c_g))


def berechne_erdreich_parameter(
        flaeche_m2: float,
        perimeter_m: float,
        R_f_m2K_W: float,
        wanddicke_m: float,
        R_si_m2K_W: float,
        R_se_m2K_W: float,
        boden_kategorie: int = BODEN_KATEGORIE_DEFAULT,
        lambda_g: Optional[float] = None,
        rho_c_g: Optional[float] = None) -> ErdreichParameter:
    """Volle 13370-Kette: B' → d_f → U (Gl. 4/5) → R_g, κ_gr,
    R_vi (F.1), δ (H.1), H_pi (H.2), H_pe (H.3).

    Args:
        flaeche_m2: Bodenplattenfläche A.
        perimeter_m: exponierter Umfang P (6.7.1).
        R_f_m2K_W: Wärmedurchlasswiderstand der Bodenplatten-
            KONSTRUKTION (alle Schichten, ohne Übergänge) = R_f;sog.
        wanddicke_m: Gesamtdicke der Außenwände d_w;e (Gl. 3).
        R_si_m2K_W / R_se_m2K_W: Übergangswiderstände (ISO 6946;
            im Aufrufer aus den Tab.-25-Koeffizienten abgeleitet).
        boden_kategorie: Tabelle 7 (Default 2, s. 6.4.1).
        lambda_g / rho_c_g: expliziter Boden (überschreibt Kategorie).
    """
    if flaeche_m2 <= 0 or perimeter_m <= 0:
        raise ValueError(
            f"Erdreich: A = {flaeche_m2} m², P = {perimeter_m} m — "
            f"beide müssen > 0 sein (Gl. 2).")
    if boden_kategorie not in BODEN_KATEGORIEN:
        raise ValueError(
            f"Erdreich: unbekannte Bodenkategorie {boden_kategorie} "
            f"(Tabelle 7 kennt 1, 2, 3).")
    kat_lambda, kat_rhoc = BODEN_KATEGORIEN[boden_kategorie]
    lam = lambda_g if lambda_g is not None else kat_lambda
    rc = rho_c_g if rho_c_g is not None else kat_rhoc

    # Gl. (2): charakteristisches Bodenplattenmaß
    B = flaeche_m2 / (0.5 * perimeter_m)
    # Gl. (3): wirksame Gesamtdicke
    d_f = wanddicke_m + lam * (R_si_m2K_W + R_f_m2K_W + R_se_m2K_W)
    # Gl. (4)/(5): U der Bodenplatte inkl. Erdreich
    if d_f < B:
        U = 2.0 * lam / (math.pi * B + d_f) * math.log(
            math.pi * B / d_f + 1.0)
    else:
        U = lam / (0.457 * B + d_f)

    # F.1: R_g der 0,5-m-Schicht und virtuelle Schicht
    R_g = 0.5 / lam
    kappa_gr = 0.5 * rc
    R_vi = 1.0 / U - R_si_m2K_W - R_f_m2K_W - R_g
    hinweise = []
    if R_vi <= 0.0:
        # Bei Gl.-4-Platten mathematisch möglich für extreme
        # Geometrien; dann ist das Schichtmodell nicht anwendbar.
        raise ValueError(
            f"Erdreich: R_vi = {R_vi:.4f} m²K/W ≤ 0 aus Gl. (F.1) — "
            f"13370-Schichtmodell hier nicht anwendbar "
            f"(A = {flaeche_m2}, P = {perimeter_m}, R_f = {R_f_m2K_W}).")

    # H.1–H.3: periodische Größen
    delta = periodische_eindringtiefe(lam, rc)
    H_pi = flaeche_m2 * (lam / d_f) * math.sqrt(
        2.0 / ((1.0 + delta / d_f) ** 2 + 1.0))
    H_pe = 0.37 * perimeter_m * lam * math.log(delta / d_f + 1.0)

    return ErdreichParameter(
        B_strich_m=B, d_f_m=d_f, U_W_m2K=U, R_g_m2K_W=R_g,
        kappa_gr_J_m2K=kappa_gr, R_vi_m2K_W=R_vi, delta_m=delta,
        H_pi_W_K=H_pi, H_pe_W_K=H_pe, lambda_g=lam, rho_c_g=rc,
        hinweise=hinweise)


def berechne_theta_vi_monate(
        params: ErdreichParameter,
        flaeche_m2: float,
        perimeter_m: float,
        theta_e_monat: Sequence[float],
        theta_int_monat: Sequence[float],
        psi_wf_W_mK: float = 0.0) -> List[float]:
    """θ_gr;vi;m je Kalendermonat nach Gl. (C.4) + Gl. (F.2).

    C.4: Φ_m = U·A·(θ̄int − θ̄e) + P·Ψ_wf·(θ_int,m − θ_e,m)
              − H_pi·(θ̄int − θ_int,m) + H_pe·(θ̄e − θ_e,m)
    F.2: θ_vi,m = θ_int,m − (Φ_m − P·Ψ_wf·(θ̄int − θ̄e)) / (A·U)

    Monatsmittel der Außentemperatur kommen aus dem Klimadatensatz,
    die der Innentemperatur aus dem Aufrufer.
    """
    if len(theta_e_monat) != 12 or len(theta_int_monat) != 12:
        raise ValueError("theta_e_monat/theta_int_monat: je 12 Werte.")
    te_quer = sum(theta_e_monat) / 12.0
    ti_quer = sum(theta_int_monat) / 12.0
    UA = params.U_W_m2K * flaeche_m2
    PPsi = perimeter_m * psi_wf_W_mK
    theta_vi = []
    for m in range(12):
        te_m = theta_e_monat[m]
        ti_m = theta_int_monat[m]
        phi_m = (UA * (ti_quer - te_quer)
                 + PPsi * (ti_m - te_m)
                 - params.H_pi_W_K * (ti_quer - ti_m)
                 + params.H_pe_W_K * (te_quer - te_m))
        theta_vi.append(ti_m - (phi_m - PPsi * (ti_quer - te_quer)) / UA)
    return theta_vi


def theta_vi_fallback_sinus(
        theta_mittel_C: float,
        amplitude_K: float,
        phasenverschiebung_monate: float) -> List[float]:
    """FALLBACK-Näherung (bewusst nur Rückfallebene, nicht Default):
    Monatsmittel des Bestands-Sinus der ERD-Randbedingung. Kein
    13370-Bezug; der Aufrufer MUSS den Log-Hinweis ausgeben."""
    werte = []
    for m in range(12):
        stunde_mitte = (m + 0.5) * 730.0
        phase = phasenverschiebung_monate * 730.0
        werte.append(theta_mittel_C + amplitude_K * math.sin(
            2.0 * math.pi * (stunde_mitte - phase) / 8760.0))
    return werte

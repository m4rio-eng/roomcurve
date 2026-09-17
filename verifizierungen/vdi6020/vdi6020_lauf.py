#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VDI-6020-Testbeispiele 1–7: Simulationslauf (Harness abgeleitet aus VDI 6007-1 Anhang A)
=======================================================================

Fährt die sieben Testbeispiele mit dem ISO-52016-1-Kern gegen die aus
VDI 6007-1:2015-06 Anhang A abgeleiteten Configs (vdi6020_ableitung.py).

Randbedingungen (VDI 6020:2022-12, Kap. 8, S. 53):
  * 60 Tage, Quell-/Sollprofile täglich identisch
  * Anfangsbedingung: 22 °C stationär (alle Knoten, Luft, Flächen)
  * Fälle 1–4, 6, 7: Außentemperatur konstant 22 °C, keine Strahlung
  * Fall 5: Außentemperatur-Tagesgang und Fenstergewinne "im Raum"
    aus Tabelle A.5.3 (als zweites internes Quellprofil, a_kon = 0,09)

Ausgaben sind DATIERT (echtes Laufdatum) und überschreiben keine
Ausgaben: vdi6020_ergebnisse_<JJJJ_MM_TT>_hauptlauf_kappa_voll.json
bzw. …_sensitivitaet_kappa_13786.json
"""

import copy
import json
import sys
from datetime import date
from pathlib import Path

import numpy as np

# --- Reproduzierbarkeits-Schutz -------------------------------------
# Stellt sicher, dass IMMER der Repo-Kern rechnet und nie still eine
# anderweitig installierte iso52016-Version.
_REPO_WURZEL = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_WURZEL))
import iso52016 as _iso_kernpruefung
_KERNPFAD = Path(_iso_kernpruefung.__file__).resolve()
if not _KERNPFAD.is_relative_to(_REPO_WURZEL):
    raise RuntimeError(
        f"Fremder iso52016-Kern geladen: {_KERNPFAD} — erwartet wird "
        f"der Repo-Kern unter {_REPO_WURZEL}. Abbruch statt stiller "
        f"Fremdrechnung (Reproduzierbarkeits-Schutz).")
# --------------------------------------------------------------------


HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent.parent))

from iso52016 import (Klimadaten, lade_gebaeude, SimulationsOptionen,
                      simuliere, Schicht, berechne_kappa_m)

TAGE = 60
STUNDEN = TAGE * 24
AUSWERTETAGE = (1, 10, 60)


def konvertiere_schichten(cfg: dict, kappa_ansatz: str = "iso13786") -> dict:
    """Schichtaufbauten -> R_c (Summe d/λ) und κ_m.

    kappa_ansatz:
      'iso13786' (Hauptlauf): κ_m nach ISO 13786 Anhang C.2 (projekt-
        weite Konvention, 24-h-wirksame Kapazität); Klasse
        'massenklasse' (konsistent: erfasste Masse innen).
      'voll' (Sensitivität): κ_m = Σ ρ·c·d (gesamte Speichermasse,
        physikalisch angemessener für das 60-Tage-Einschwingen der
        VDI-Testbeispiele); Klasse 'massenklasse_kappa_voll'
        (aufbaubasierte Schwerpunktregel).
    """
    cfg = copy.deepcopy(cfg)
    for bt in cfg.get('bauteile', []):
        if 'schichten' not in bt:
            continue
        schichten = [Schicht(name=s['material'], dicke_m=s['dicke_m'],
                             lambda_W_mK=s['lambda_W_mK'],
                             rho_kg_m3=s['rho_kg_m3'], c_J_kgK=s['c_J_kgK'])
                     for s in bt['schichten']]
        bt['R_c_m2K_W'] = sum(s.dicke_m / s.lambda_W_mK for s in schichten)
        if kappa_ansatz == "voll":
            bt['kappa_m_kJ_m2K'] = sum(
                s.rho_kg_m3 * s.c_J_kgK * s.dicke_m for s in schichten) / 1000.0
            bt['massenklasse'] = bt.get('massenklasse_kappa_voll',
                                        bt.get('massenklasse', 'D'))
        else:
            bt['kappa_m_kJ_m2K'] = berechne_kappa_m(schichten) / 1000.0
        bt.pop('massenklasse_kappa_voll', None)
        del bt['schichten']
    return cfg


def klima_fuer_fall(fall_nr: int, referenz: dict) -> Klimadaten:
    f = referenz['faelle'][str(fall_nr)]
    theta_tag = f['theta_e_C']
    if fall_nr == 5:
        theta_e = np.tile(np.array(theta_tag), TAGE)
    else:
        assert all(t == 22.0 for t in theta_tag)
        theta_e = np.full(STUNDEN, 22.0)
    leer = {k: np.zeros(STUNDEN) for k in ['N', 'E', 'S', 'W', 'H']}
    return Klimadaten(
        n_hours=STUNDEN, theta_e=theta_e,
        I_sol={k: v.copy() for k, v in leer.items()},
        I_sol_dir={k: v.copy() for k, v in leer.items()},
        I_sol_dif={k: v.copy() for k, v in leer.items()})


def setze_stationaeren_start(gebaeude, theta=22.0):
    """VDI 6020 S. 53: Startzustand 22 °C stationär."""
    for zone in gebaeude.zonen.values():
        zone.theta_air = theta
        zone.theta_op = theta
        zone.theta_rad_mean = theta
        for bt in zone.bauteile:
            bt.theta_pl = np.ones(bt.n_knoten) * theta


def extrahiere_tag(stunden_liste, tag):
    a = (tag - 1) * 24
    return stunden_liste[a:a + 24]


def simuliere_fall(n: int, referenz: dict,
                   kappa_ansatz: str = 'iso13786') -> dict:
    cfg_dir = HIER / "configs"
    geb_cfg = konvertiere_schichten(
        json.loads((cfg_dir / f"gebaeude_fall{n}.json").read_text()),
        kappa_ansatz=kappa_ansatz)
    tmp = HIER / f"_tmp_gebaeude_fall{n}.json"
    tmp.write_text(json.dumps(geb_cfg))
    try:
        gebaeude = lade_gebaeude(str(tmp), str(cfg_dir / f"nutzung_fall{n}.json"))
    finally:
        tmp.unlink()

    setze_stationaeren_start(gebaeude)
    klima = klima_fuer_fall(n, referenz)
    optionen = SimulationsOptionen(klimadatei="vdi6020")
    optionen.f_HC_konv = geb_cfg.get('simulation', {}).get('f_HC_konv', 1.0)
    optionen.init_tage = 0

    erg = simuliere(gebaeude, klima, optionen)
    zone = erg['zonen']['RAUM']
    stunden = zone['stunden']
    out = {"fall": n, "tage": {}}
    for tag in AUSWERTETAGE:
        block = extrahiere_tag(stunden, tag)
        out["tage"][str(tag)] = {
            "luft": [round(h['theta_air'], 3) for h in block],
            "op": [round(h['theta_op'], 3) for h in block],
            "last": [round(h.get('Phi_H_W', 0.0) + h.get('Phi_C_W', 0.0), 2)
                     for h in block],
        }
    return out


def main():
    referenz = json.loads((HIER / "vdi6020_referenz_norm.json").read_text())
    heute = date.today().strftime("%Y_%m_%d")
    ergebnisse = {
        "meta": {
            "laufdatum": date.today().isoformat(),
            "harness": "vdi6020_lauf.py (abgeleitet aus VDI 6007-1 Anhang A)",
            "referenzdatei": "vdi6020_referenz_norm.json",
        },
        "faelle": {},
    }
    import argparse
    ap = argparse.ArgumentParser()
    # κ_voll = volle Schichtsumme ist der HAUPTLAUF (durch die
    # Normprüffalltabellen 23/24 der ISO 52016-1 gedeckt, z. B.
    # Holzboden 19 500 J/(m²K) = 0,025·650·1200); die
    # ISO-13786-Kappung ist die Sensitivität.
    ap.add_argument("--kappa", choices=("iso13786", "voll"),
                    default="voll")
    args = ap.parse_args()
    ergebnisse["meta"]["kappa_ansatz"] = args.kappa
    for n in range(1, 8):
        print(f"Fall {n} ...", flush=True)
        ergebnisse["faelle"][str(n)] = simuliere_fall(
            n, referenz, kappa_ansatz=args.kappa)
    suffix = ("_hauptlauf_kappa_voll" if args.kappa == "voll"
              else "_sensitivitaet_kappa_13786")
    out = HIER / f"vdi6020_ergebnisse_{heute}{suffix}.json"
    out.write_text(json.dumps(ergebnisse, indent=1))
    print(f"geschrieben: {out.name}")


if __name__ == "__main__":
    main()

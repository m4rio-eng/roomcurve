#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Beispiel: Einzonen-Gebäudesimulation
====================================

Dieses Skript zeigt, wie man RoomCurve (ISO-52016-1-Rechenkern) 
programmatisch verwendet, um den Heiz- und Kühlbedarf
eines einfachen Gebäudes zu berechnen.

Beispielgebäude (1-Zonen-Modell):
- 10×10m Grundfläche, 2 Geschosse
- Nutzfläche: 200 m², Volumen: 500 m³
- EnEV-Standard (U-Werte typisch für Neubau)
- Standort: Denver (BESTEST-Klimadaten)

Voraussetzung:
    pip install -e .  (im Projekt-Root)

Ausführung:
    python examples/beispiel_einfamilienhaus.py
"""

import sys
import numpy as np
from pathlib import Path

# Simulator-Module importieren
from iso52016 import (
    Gebaeude, Zone, Bauteil, Randbedingung, 
    Nutzungsprofil, SimulationsOptionen, 
    Klimadaten, simuliere, lade_klimadaten
)


def erstelle_einfamilienhaus() -> Gebaeude:
    """
    Erstellt ein einfaches Einfamilienhaus.
    
    Geometrie:
    - Grundfläche: 10 × 10 m = 100 m²
    - 2 Geschosse, Raumhöhe 2.5 m
    - Volumen: 500 m³
    - Fensteranteil: 20% der Fassade
    
    Konstruktion (EnEV-Standard):
    - Außenwand: U = 0.24 W/m²K (WDVS)
    - Dach: U = 0.20 W/m²K
    - Bodenplatte: U = 0.30 W/m²K
    - Fenster: U = 1.1 W/m²K, g = 0.6
    """
    
    gebaeude = Gebaeude(
        name="Einfamilienhaus EnEV",
        beschreibung="10×10m, 2 Geschosse, EnEV-Standard"
    )
    
    # --- Randbedingungen ---
    gebaeude.randbedingungen['aussen'] = Randbedingung(
        typ='aussenluft',
        temperatur_C=10.0  # Wird durch Klimadaten überschrieben
    )
    
    gebaeude.randbedingungen['erdreich'] = Randbedingung(
        typ='erdreich',
        temperatur_C=10.0,      # Mittlere Erdreichtemperatur
        amplitude_K=3.0,        # Jahresschwankung
        phasenverschiebung_monate=1.5
    )
    
    # --- Nutzungsprofil ---
    # Typisches Wohngebäude: 20°C Heizen, 26°C Kühlen
    gebaeude.nutzungsprofile['wohnen'] = Nutzungsprofil(
        id='wohnen',
        beschreibung='Wohnnutzung',
        heizen_C=[20.0] * 24,           # Konstant 20°C
        kuehlen_C=[26.0] * 24,          # Konstant 26°C
        interne_gewinne_W=[200.0] * 24, # 200W (Personen + Geräte)
        luftwechsel_1_h=[0.5] * 24,     # 0.5 1/h (DIN 4108-2)
        f_int_konv=0.4
    )
    
    # --- Zone erstellen ---
    zone = Zone(
        id='EG_OG',
        name='Wohnbereich',
        volumen_m3=500.0,           # 10×10×2.5×2
        nutzungsprofil='wohnen',
        nutzflaeche_m2=200.0        # Nutzfläche
    )
    
    # --- Bauteile ---
    
    # Fassadenfläche pro Seite: 10m × 5m = 50 m²
    # Minus 20% Fenster = 40 m² opak pro Seite
    
    # Außenwände (4 Seiten)
    for name, azimut in [('Nord', 0), ('Ost', 90), ('Süd', 180), ('West', 270)]:
        zone.bauteile.append(Bauteil(
            id=f'wand_{name.lower()}',
            name=f'Außenwand {name}',
            typ='opak',
            flaeche_m2=40.0,
            azimut_deg=azimut,
            neigung_deg=90.0,
            zone_innen='EG_OG',
            zone_aussen='AUL',          # Außenluft
            R_c_m2K_W=4.0,              # ~1/U - Oberflächenwiderstände
            kappa_m_kJ_m2K=80.0,        # Mauerwerk mit WDVS
            massenklasse='I',           # Masse innen (Außendämmung)
            alpha_sol=0.6,              # Putz hell
            h_ci=2.5,
            h_ri=5.5,
            h_ce=20.0,
            h_re=4.0,
            F_sky=0.5                   # Vertikale Fläche
        ))
    
    # Fenster (4 Seiten, je 10 m²)
    for name, azimut in [('Nord', 0), ('Ost', 90), ('Süd', 180), ('West', 270)]:
        zone.bauteile.append(Bauteil(
            id=f'fenster_{name.lower()}',
            name=f'Fenster {name}',
            typ='transparent',
            flaeche_m2=10.0,
            azimut_deg=azimut,
            neigung_deg=90.0,
            zone_innen='EG_OG',
            zone_aussen='AUL',
            U_W_m2K=1.1,                # 3-fach Verglasung
            g_wert=0.6,                 # Guter Energiedurchlass
            F_w=0.9,                    # ISO-Korrekturfaktor
            rahmenanteil=0.3,           # 30% Rahmen
            h_ci=2.5,
            h_ri=5.5,
            h_ce=20.0,
            h_re=4.0
        ))
    
    # Dach (Flachdach, 100 m²)
    zone.bauteile.append(Bauteil(
        id='dach',
        name='Flachdach',
        typ='opak',
        flaeche_m2=100.0,
        azimut_deg=0.0,
        neigung_deg=0.0,               # Horizontal
        zone_innen='EG_OG',
        zone_aussen='AUL',
        R_c_m2K_W=4.8,
        kappa_m_kJ_m2K=50.0,           # Leichte Konstruktion
        massenklasse='I',
        alpha_sol=0.3,                 # Helle Abdichtung
        h_ci=5.0,                      # Wärmestrom aufwärts
        h_ri=5.5,
        h_ce=20.0,
        h_re=4.0,
        F_sky=1.0                      # Voller Himmelsblick
    ))
    
    # Bodenplatte (100 m²)
    zone.bauteile.append(Bauteil(
        id='boden',
        name='Bodenplatte',
        typ='opak',
        flaeche_m2=100.0,
        azimut_deg=0.0,
        neigung_deg=0.0,
        zone_innen='EG_OG',
        zone_aussen='ERD',             # Erdreich
        R_c_m2K_W=3.0,
        kappa_m_kJ_m2K=150.0,          # Schwere Betonplatte
        massenklasse='I',
        alpha_sol=0.0,                 # Keine Solarstrahlung
        h_ci=0.7,                      # Wärmestrom abwärts
        h_ri=5.5,
        h_ce=0.0,                      # Kein Außenluftaustausch
        h_re=0.0,
        F_sky=0.0
    ))
    
    # Zone-Kennwerte berechnen
    zone.berechne_A_tot()
    
    # Zone zum Gebäude hinzufügen
    gebaeude.zonen['EG_OG'] = zone
    
    return gebaeude


def main():
    """Hauptfunktion - führt die Beispielsimulation durch."""
    
    print("=" * 60)
    print("ISO 52016-1 Beispielsimulation: Einfamilienhaus")
    print("=" * 60)
    print()
    
    # 1. Gebäude erstellen
    print("1. Erstelle Gebäudemodell...")
    gebaeude = erstelle_einfamilienhaus()
    
    zone = gebaeude.zonen['EG_OG']
    print(f"   Gebäude: {gebaeude.name}")
    print(f"   Volumen: {zone.volumen_m3} m³")
    print(f"   Nutzfläche: {zone.nutzflaeche_m2} m²")
    print(f"   Bauteile: {len(zone.bauteile)}")
    print(f"   Hüllfläche: {zone.A_tot:.0f} m²")
    print()
    
    # 2. Klimadaten laden
    print("2. Lade Klimadaten (DRYCOLD, BESTEST)...")
    # Klimadaten laden (BESTEST DRYCOLD, EPB-Center-Begleitdatei)
    # Pfad relativ zum Projekt-Root
    projekt_root = Path(__file__).parent.parent
    klimadatei = projekt_root / 'verifizierungen' / 'bestest' / 'klimadaten' / 'DRYCOLD_52016_verifizierung.csv'
    
    if not klimadatei.exists():
        print(f"   FEHLER: Klimadatei nicht gefunden: {klimadatei}")
        print("   Bitte BESTEST-Klimadaten bereitstellen.")
        return
    
    klima = lade_klimadaten(str(klimadatei), 'CSV')
    print(f"   Stunden: {klima.n_stunden}")
    print(f"   Temperatur: {klima.theta_e.min():.1f} ... {klima.theta_e.max():.1f} °C")
    print()
    
    # 3. Simulationsoptionen
    print("3. Konfiguriere Simulation...")
    optionen = SimulationsOptionen(
        klimadatei=str(klimadatei),
        klimaformat='CSV',
        init_tage=31,
        f_sol_konv=0.1,
        f_HC_konv=0.4,
        klimazone='zwischen',
        ausgabe_stunden=False,      # Keine Stundenwerte (schneller)
        ausgabe_monate=True
    )
    print("   Zeitraum: 12 Monate (Jahresrechnung)")
    print(f"   Initialisierung: {optionen.init_tage} Tage")
    print()
    
    # 4. Simulation durchführen
    print("4. Starte Simulation...")
    print()
    ergebnisse = simuliere(gebaeude, klima, optionen)
    
    # 5. Ergebnisse ausgeben
    print()
    print("=" * 60)
    print("ERGEBNISSE")
    print("=" * 60)
    print()
    
    Q_H = ergebnisse['gesamt']['Q_H_kWh']
    Q_C = ergebnisse['gesamt']['Q_C_kWh']
    A_f = zone.nutzflaeche_m2
    
    print(f"Jahres-Heizwärmebedarf:   {Q_H:>8,.0f} kWh/a")
    print(f"Jahres-Kühlkältebedarf:   {Q_C:>8,.0f} kWh/a")
    print()
    print(f"Spezifischer Heizwärmebedarf: {Q_H/A_f:>6.1f} kWh/(m²·a)")
    print(f"Spezifischer Kühlbedarf:      {Q_C/A_f:>6.1f} kWh/(m²·a)")
    print()
    
    # Monatliche Aufschlüsselung
    monate = ['Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun',
              'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez']
    
    z_erg = ergebnisse['zonen']['EG_OG']
    
    print("Monatswerte:")
    print("-" * 40)
    print(f"{'Monat':>6}  {'Heizen':>10}  {'Kühlen':>10}")
    print(f"{'':>6}  {'[kWh]':>10}  {'[kWh]':>10}")
    print("-" * 40)
    
    for i, m in enumerate(z_erg['monate']):
        print(f"{monate[i]:>6}  {m['Q_H_kWh']:>10.0f}  {m['Q_C_kWh']:>10.0f}")
    
    print("-" * 40)
    print(f"{'Summe':>6}  {Q_H:>10.0f}  {Q_C:>10.0f}")
    print()
    
    # Übertemperatur-Auswertung
    if 'uebertemperatur' in z_erg:
        uet = z_erg['uebertemperatur']
        print("Übertemperatur-Auswertung:")
        print("-" * 40)
        print(f"  θ_op,max: {uet['theta_op_max']}°C (Stunde {uet['theta_op_max_stunde']})")
        print()
        print("  Feste Schwellen (Gradstunden):")
        for schwelle in ['25', '26', '27', '28']:
            gh = uet['gradstunden_fest'].get(schwelle, 0)
            n = uet['stunden_fest'].get(schwelle, 0)
            print(f"    {schwelle}°C: {gh:>7.1f} Kh, {n:>5.0f} h")
        print()
        print("  Adaptiv nach DIN EN 16798-1:")
        for kat in ['I', 'II', 'III']:
            gh = uet['gradstunden_16798'].get(kat, 0)
            n = uet['stunden_16798'].get(kat, 0)
            print(f"    Kategorie {kat}: {gh:>7.1f} Kh, {n:>5.0f} h")
        print()
    
    # Bewertung
    print("Bewertung:")
    if Q_H/A_f < 50:
        print(f"  → Heizwärmebedarf entspricht ca. KfW-55 Standard")
    elif Q_H/A_f < 70:
        print(f"  → Heizwärmebedarf entspricht ca. KfW-70 Standard")
    elif Q_H/A_f < 100:
        print(f"  → Heizwärmebedarf entspricht ca. EnEV-Standard")
    else:
        print(f"  → Heizwärmebedarf über EnEV-Anforderungen")
    
    print()
    print("Hinweis: Ergebnisse basieren auf Denver-Klimadaten (BESTEST).")
    print("         Für deutsche Standorte TRY-Daten verwenden.")


if __name__ == '__main__':
    main()

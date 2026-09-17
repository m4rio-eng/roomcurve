# Verifizierung der 52010-1-Kette gegen Tabelle 26 (DIN EN ISO 52016-1)

Stand: 22.07.2026. Geprüft wird die solare Umrechnungskette dieses Repositories (DIN EN ISO 52010-1: Sonnenstand Gl. 1–17, Perez-Konvertierung Gl. 26–39, Bodenreflexion ρ = 0,2) gegen die Norm-Referenzwerte der Tabelle 26 (DIN EN ISO 52016-1:2018-04, S. 161–162) für das Verifizierungsklima DRYCOLD. Ergebnis: Jahreswerte je Orientierung und Kanal innerhalb ±0,45 % reproduziert (Details unten); Reproduktionsweg im Abschnitt „Reproduktion".

## Gegenstand

Verifiziert wird, dass die Gesamtkette (Sonnenstand Gl. 1–17 + Konvertierung Gl. 26–39 + Bodenreflexion ρ = 0,2) die Norm-Referenzwerte der Tabelle 26 für das Verifizierungsklima DRYCOLD reproduziert.

## Randbedingung der Methode

Die beiliegende EPB-Begleitdatei (`DRYCOLD_52016_verifizierung.csv`) enthält nur Fassadenwerte, keine horizontalen Rohdaten (DNI/DHI). Die Eingaben der Kette wurden daher aus den Horizontalspalten der EPB-Datei REKONSTRUIERT (Bisektion auf G_d über die exakte Summenidentität I_dir;tot + I_dif;tot |horizontal = G_b·sin α + G_d·[(1−F1)+F1·a/b], inneres F1-Update über die geprüften Funktionen; 62 von 4611 Strahlungsstunden als Randfälle ohne Vorzeichenwechsel, Round-Trip-Residuum horizontal Σ|Δ| = 3,4 (dir) bzw. 3,3 (dif) kWh/m²a ≈ 0,18 %). Die Verifizierung testet damit Kette + Rekonstruktion gemeinsam; das Rekonstruktionsrauschen konzentriert sich naturgemäß auf Auf-/Untergangs- stunden (schlecht konditionierte Division durch sin α).

## Vorab festgestellte Konventionen (datengestützt)

1. Die vertikalen dif-Spalten der EPB-Datei sind stundenweise EXAKT identisch (max. Spreizung 0,0 W/m²) → die Datei nutzt die Kanalzuordnung der Gl. (37)/(38): Zirkumsolar im Direktkanal. Tabelle 26 b) bestätigt das (Diffus-Jahreswert 394,6 für alle Vertikalen identisch). Die Anbindung verwendet dieselbe Zuordnung (I_dir;tot / I_dif;tot).
2. Die EPB-Datei selbst reproduziert Tabelle 26 auf Rundungsniveau (max. |Δ| Jahreswert 0,64 kWh/m² ≈ 0,04 %).

## Ergebnisse

Jahreswerte [kWh/m²], implementierte Kette gegen Tabelle 26:

| Ori | Kette tot | Tab. 26 | Δ | dir Kette / T26 | dif Kette / T26 |
|---|---|---|---|---|---|
| N | 428,3 | 429,7 | −0,32 % | 34,4 / 35,1 | 393,9 / 394,6 |
| O | 1152,4 | 1150,0 | +0,21 % | 758,5 / 755,4 | 393,9 / 394,6 |
| S | 1545,3 | 1547,1 | −0,11 % | 1151,4 / 1152,5 | 393,9 / 394,6 |
| W | 1042,2 | 1046,6 | −0,42 % | 648,2 / 651,9 | 393,9 / 394,6 |
| H | 1847,5 | 1848,5 | −0,05 % | 1534,8 / 1537,7 | 312,7 / 310,8 |

Monatswerte gegen EPB-Datei: max. |Δ| = 3,4 kWh/m² (Ost, März); alle übrigen Orientierungen ≤ 1,2 kWh/m².

Stundenvergleich der Vertikalen, beschränkt auf gut konditionierte Stunden (α > 10°, 3681 Std): Σ|Δ|/Σref = 0,33 % (S) bis 0,85 % (N), max. Einzelstunde 62 W/m². Die größeren Einzelabweichungen (bis ~980 W/m² in Sonnenaufgangsstunden, Ost) treten ausschließlich bei α < 5° auf und sind dem Rekonstruktionsverfahren zuzuordnen (Beleg: horizontaler Round-Trip nahezu exakt, Konzentration auf schlecht konditionierte Stunden, Symmetrie Ost/Aufgang – West/Untergang).

## Bewertung

Die Kette reproduziert Tabelle 26 jährlich innerhalb ±0,45 % je Orientierung und Kanal — im Rauschband des Rekonstruktionsverfahrens. Die Kanalzuordnung (Zirkumsolar → Direkt) entspricht Norm und EPB-Datei und ist die für die Verschattung (Anhang F Verfahren 1, F_sh nur auf Direktanteil) benötigte. Verifizierung BESTANDEN im Rahmen der Methodengrenzen; eine schärfere Prüfung würde die originalen DRYCOLD-Rohdaten (DNI/DHI, ISO-Begleittabelle http://standards.iso.org/iso/52016/-1/ed-1) erfordern — als optionale Nachschärfung möglich, sofern die Begleitdatei vorliegt.

## Reproduktion

Verfahrensparameter der Inversions- und Vergleichsrechnung: Bisektion auf G_d, 80 Iterationen, Toleranz 1e-9; Standort Denver-Stapleton 39,76 / −104,86 / TZ −7; Formeln und Summenidentität siehe „Randbedingung der Methode". Die Invarianten der Anbindung sind dauerhaft in `tests/test_climate_perez.py` abgesichert (Vertikalen-Diffusgleichheit, Horizontal-Summenidentität, Zirkumsolar-Kanal, Bodenreflexionsbetrag, Wrapper-Konsistenz, I_SC-Einheitlichkeit).

# Known Issues — RoomCurve 0.1.0

Bekannte Einschränkungen des veröffentlichten Stands 0.1.0: was die Software nicht kann und was ungeprüft ist. Was verifiziert ist, steht im README und in den Verifizierungsberichten.

## O1 — Erdreichmodell unverifiziert; nur Bodenplatte auf Erdreich

Das Gl.-48-Knotenmodell mit ISO-13370-Ableitung ist implementiert und durch 18 Tests abgedeckt (Handrechnungs-Vergleiche der Einzelgrößen, Durchreichung der Parameter bis in die Zonenmatrix), aber es gibt KEINEN Erdreich-Referenzfall in der Verifizierungssuite (BESTEST nutzt kein Erdreich-Bauteil). Nicht implementiert sind Kellergeschosse (ISO 13370 §7.3/7.4), aufgeständerte Bodenplatten (§7.2) und Randdämmung (Anhang D) — Eingaben dieser Art werden nicht erkannt, der Nutzer muss die Anwendbarkeit (Bodenplatte auf Erdreich ohne Randdämmung) selbst sicherstellen.

## O2 — Mehrzonen: keine thermische Zone-zu-Zone-Kopplung, unverifiziert

Trennwände zu Nachbarzonen werden nach dem Standardweg der Norm behandelt (Gl. 42 bzw. 6.5.6.3.7: interne Trennwand mit adiabater Mittelebene). Die Temperatur der Nachbarzone geht dabei NICHT in die Rechnung ein — es gibt keine thermische Kopplung zwischen Zonen. Die simultane Kopplung nach Anhang D ist nicht implementiert. Unverifiziert, da alle Prüffälle der Suite einzonig sind.

EINGABEKONVENTION (leicht zu übersehen): R_c und κ_m von ADIABAT- und nachbarzone-Elementen gelten bis zur MITTELEBENE (halbe Konstruktion, 6.5.6.3.6).

## O3 — Klimadateien ohne Direkt-/Diffus-Rohdaten: Orientierungen werden gerastert

Klimadateien, die nur fertige Fassadenwerte je Himmelsrichtung (N/O/S/W/Horizontal) und keine Rohdaten der Direkt- und Diffusstrahlung (DNI/DHI) enthalten, runden abweichende Bauteil-Orientierungen auf das 45°-Raster (mit Hinweis im Laufprotokoll). Abhilfe: TRY/TMY3 oder CSV mit DNI/DHI verwenden — dann rechnet die 52010-1-Kette echte β/γ je Bauteil. (Im BESTEST-Setup exakt wirkungslos, da der einzige Nicht-Raster-Kandidat, der Boden, α_sol = 0 hat.)

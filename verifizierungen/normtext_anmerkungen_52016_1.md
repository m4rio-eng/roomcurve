# Anmerkungen zum Normtext und gewählte Lesarten (DIN EN ISO 52016-1:2018-04)

Dieses Register legt die beim Umsetzen der DIN EN ISO 52016-1:2018-04 (deutsche Ausgabe) getroffenen Auslegungsentscheidungen offen. Es enthält dokumentierte Druckfehler, Widersprüche UND Auslegungsspielräume des Normtexts — je Eintrag mit Fundstelle, Beleg und der von RoomCurve gewählten, begründeten Lesart; keine Codebefunde. Gegenstück: `normtext_anmerkungen_52010_1.md`. Prüfgrundlage: Lesung am Seitenbild der genannten Ausgabe (07/2026, zwei unabhängige Durchgänge) sowie die BESTEST-Verifizierung.

## M1 — Zirkumsolar-Zuordnung: Gl. (41)/(69) widersprechen Anhang F.1

Die Variablendefinitionen zu Gl. (41) (6.5.6.3.5, opake Flächen) und Gl. (69) (Fenster) ordnen die zirkumsolare Bestrahlungsstärke dem DIFFUSkanal zu („I_sol;dir … ohne / I_sol;dif … mit zirkumsolarer Bestrahlungsstärke"). Anhang F.1 a) verlangt dagegen, dass die Verschattung die Direktstrahlung „einschließlich der zirkumsolaren Bestrahlungsstärke" blockiert — was nur möglich ist, wenn Zirkumsolar im DIREKTkanal geführt wird. Beide Aussagen stehen in derselben Norm.

Physikalisch kommt Zirkumsolar aus der Sonnenrichtung; ein Hindernis, das die Sonnenscheibe blockt, blockt den Schleier mit — die Anhang-F-Lesart ist die physikalisch richtige. Sie ist zudem konsistent mit der Gleichungskette der ISO 52010-1 (Gl. 36–38: Zirkumsolar wird dem Direktanteil auf der geneigten Fläche zugeschlagen) und mit den EPB-Referenzdaten (DRYCOLD-CSV, datengestützt geprüft).

**RoomCurve-Umsetzung:** Anhang-F-Lesart in beiden Datenpfaden — DNI/DHI-Kette nach 52010-1 (I_dir = Direkt + Zirkumsolar, Gl. 37; Kommentar in `climate.py`) wie auch bei vorgerechneten Flächenwerten (BESTEST-Direktspalten enthalten den Anteil). F_sh wirkt einheitlich auf den so definierten Direktkanal. Wirkung der Lesart-Wahl: nur in verschatteten Stunden, Größenordnung wenige Prozent der Diffusstrahlung.

## M2 — Gl. (F.3): Gültigkeitsbedingung im Druckbild unerfüllbar

Die gedruckte Bedingung „wenn −90 > (γ_k − φ_sol) > +90" ist als Ungleichungskette mathematisch unerfüllbar (nichts ist zugleich kleiner als −90 und größer als +90). Gemeint ist ersichtlich „außerhalb des Intervalls [−90°, +90°]" — das Sichtfeld der Fassade: Steht die Sonne mehr als 90° neben der Fassadennormalen, trifft keine Direktstrahlung auf die Fläche.

**RoomCurve-Umsetzung:** Sichtfeld-Prüfung |Δφ| ≥ 90° → Direktanteil geometrisch nicht vorhanden; F_sh-Rückgabe 1,0 als dokumentierte, numerisch neutrale Konvention (I_dir = 0 in diesen Stunden; siehe Kommentar in `simulation.py`).

## M3 — Tabelle 28: Spaltentausch der Monats-Referenzwerte (Fall 900)

In der gedruckten Tabelle 28 (BESTEST-Referenzergebnisse) sind für Fall 900 die Monats-Kühlwerte in der „Heiz"-Spalte abgedruckt (Spaltentausch-Druckfehler; Kontrollsumme 3360 kWh identifiziert die Kühlreihe). Bereits als EPB-Kommentar 28 bekannt; im BESTEST-Verifizierungsbericht entsprechend ausgewiesen.

**RoomCurve-Umsetzung:** Der BESTEST-Prüflauf vergleicht gegen die inhaltlich richtige Zuordnung (Kühlwerte als Kühlreferenz), mit Ausweis im Bericht.

## M4 — Gl.-48-Termliste: „R_c;fl;eff einschließlich der Auswirkungen des Erdreichs" führt auf Doppelzählung (27.07.2026)

Die Termliste zu Gl. (48) (S. 100/PDF 128) definiert R_c;eli des Erdgeschosselements als „Wärmedurchlasswiderstand R_c;fl;eff … (einschließlich der Auswirkungen des Erdreichs)", d. h. nach ISO 13370 §7.6 Gl. (20): R_fl;eff = 1/U − R_si. Gleichzeitig verlangt 6.5.8.2 zusätzlich R_gr (0,5-m-Erdreichschicht) und R_gr;vi (virtuelle Schicht), Letzteres nach ISO 13370 Anhang F Gl. (F.1): R_vi = 1/U − R_si − R_f − R_g.

Setzt man beides wörtlich zusammen, summiert die Knotenkette R_si + R_c;fl;eff + R_gr + R_gr;vi = R_si + (1/U − R_si) + R_g + (1/U − R_si − R_f − R_g) = 2/U − R_si − R_f ≠ 1/U — das Erdreich wird doppelt gezählt, der Jahresmittelwärmestrom wäre grob halbiert. Erzwänge man stattdessen Konsistenz bei festgehaltenem R_c;fl;eff, müsste R_gr;vi = −R_g < 0 werden (unphysikalisch).

ISO 13370 Anhang F beschreibt die Komponente dagegen explizit als „alle Schichten der Bodenplattenkonstruktion zuzüglich 0,5 m … zuzüglich einer virtuellen Schicht" — also KONSTRUKTION (R_f) in der Kette, nicht R_fl;eff. Nur diese Lesart summiert exakt auf 1/U (Jahresmittel-treu per Konstruktion von F.1).

**Quellen (2 unabhängige + 1 nicht vorliegend):** (1) algebraische Herleitung dieses Registers (27.07.2026); (2) zweite unabhängige Wortlaut-Lesung der Gl.-48-Termliste + 6.5.8.2 am Seitenbild (27.07.2026). (3) ISO/TR 52016-2 wird in 6.5.8.2 Anm. 1 als klärende Quelle referenziert und konnte nicht herangezogen werden.

**RoomCurve-Umsetzung (Lesart A — gewählt, weil sie als einzige den ISO-13370-Gesamtwiderstand 1/U exakt und damit das Jahresmittel verzerrungsfrei erhält):** In der Gl.-48-Knotenkette steht die reine Konstruktion R_f (= R_c_m2K_W des Bauteils); R_gr = 0,5/λ_g; R_gr;vi nach F.1. Damit Gesamtwiderstand = 1/U, Jahresmittel exakt.

---

*Hinweis Anschlussthema (kein Mangel, aber missverständlich):* Die 45°-Azimut-Rundung aus Anmerkung 3 zu Gl. (123) gilt ausschließlich für die monatsbezogenen Horizontsegmente des Anhangs F — sie ist KEINE Lizenz, stundenbezogene Flächenorientierungen zu rastern (Abgrenzung in im Code dokumentiert).
